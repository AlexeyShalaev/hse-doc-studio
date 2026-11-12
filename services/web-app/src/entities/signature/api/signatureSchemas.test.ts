import { describe, expect, it } from "vitest";
import {
  AttachDetachedResponseSchema,
  RuntimeSignatureSlotSchema,
  SignaturePlanSchema,
  SignaturesStateSchema,
} from "./signatureSchemas";

const detached = {
  format: "cms",
  origin: "uploaded",
  verdict: "valid",
  signer: "Иванов Иван Иванович",
  signer_id: "ab".repeat(32),
  issuer: "УЦ",
  algorithm: "1.2.643.7.1.1.3.2 / 1.2.643.7.1.1.2.2",
  signed_at: "2026-10-01T12:00:00+00:00",
  not_before: null,
  not_after: null,
  chain: "untrusted_root",
  notes: ["chain_untrusted_root", "no_revocation_check"],
  added_at: "2026-10-01T12:05:00+00:00",
  file_name: "supervisor.p7s",
  current: true,
};

describe("SignaturesStateSchema", () => {
  it("parses a state written before detached signatures existed", () => {
    const parsed = SignaturesStateSchema.parse({
      slots: {},
      placements: {},
    });
    expect(parsed.frozen).toEqual({});
    expect(parsed.detached).toEqual({});
    expect(parsed.withheld).toEqual({});
  });

  it("parses slots held back by a signing route", () => {
    const parsed = SignaturesStateSchema.parse({
      slots: {},
      placements: {},
      withheld: { topic_application: ["supervisor"] },
    });
    expect(parsed.withheld).toEqual({ topic_application: ["supervisor"] });
  });

  it("parses frozen PDFs and detached signatures", () => {
    const parsed = SignaturesStateSchema.parse({
      slots: {
        supervisor: {
          png_path: null,
          natural_width_px: null,
          natural_height_px: null,
          sign_mode: "detached_text",
        },
      },
      placements: {},
      frozen: {
        annotation: {
          sha256: "a".repeat(64),
          size: 10,
          frozen_at: "2026-10-01T12:00:00+00:00",
          stale: false,
        },
      },
      detached: { annotation: { supervisor: detached } },
    });
    expect(parsed.slots.supervisor?.sign_mode).toBe("detached_text");
    expect(parsed.detached.annotation?.supervisor?.verdict).toBe("valid");
  });

  it("rejects an unknown verdict", () => {
    expect(() =>
      AttachDetachedResponseSchema.parse({
        signature: { ...detached, verdict: "maybe" },
      }),
    ).toThrow();
  });

  it("defaults a missing key id to null", () => {
    expect(
      AttachDetachedResponseSchema.parse({ signature: detached })
        .missing_key_id,
    ).toBeNull();
  });
});

// Необязательные подписи и пропуск (docs/design/signing-route.md, 13.6): поля по умолчанию пусты,
// как у состояния, записанного до них.
describe("необязательные подписи", () => {
  it("состояние без `optional` и `skipped` читается пустым", () => {
    const parsed = SignaturesStateSchema.parse({ slots: {}, placements: {} });
    expect(parsed.optional).toEqual({});
    expect(parsed.skipped).toEqual({});
  });

  it("отметка и пропуск по документу", () => {
    const parsed = SignaturesStateSchema.parse({
      slots: {},
      placements: {},
      optional: {
        topic_application: { "topic-approval": ["academic_supervisor"] },
      },
      skipped: {
        topic_application: {
          academic_supervisor: {
            profile_id: "topic-approval",
            route_id: "sr_1",
            round: 1,
            at: "2026-11-13T10:00:00Z",
            keep_mark: false,
          },
        },
      },
    });
    expect(parsed.optional.topic_application?.["topic-approval"]).toEqual([
      "academic_supervisor",
    ]);
    expect(
      parsed.skipped.topic_application?.academic_supervisor?.route_id,
    ).toBe("sr_1");
  });

  it("рантайм-слот без `required` и `extra_by`: отметить можно, сверх точки нигде", () => {
    const parsed = RuntimeSignatureSlotSchema.parse({
      id: "author",
      label: { ru: "Студент" },
      applies_to: ["topic_application"],
      default_placement: { page: 1, x_mm: 0, y_mm: 0, width_mm: 40 },
    });
    expect(parsed.required).toBe(false);
    expect(parsed.extra_by).toEqual({});
  });

  it("план: пропущенный слот и счётчик необязательных", () => {
    const parsed = SignaturePlanSchema.parse({
      total: 1,
      signed: 1,
      crypto_total: 0,
      crypto_signed: 0,
      optional_pending: 1,
      docs: [
        {
          doc_id: "topic_application",
          built: true,
          slots: [
            {
              slot_id: "academic_supervisor",
              label: { ru: "Академрук" },
              signer: { persona: "academic_supervisor", name: "" },
              mode: "image",
              method: "image",
              crypto: false,
              mark: "png",
              status: "skipped",
              optional: true,
              skipped: { at: "2026-11-13T10:00:00Z", route_id: "sr_1" },
            },
          ],
        },
      ],
    });
    expect(parsed.optional_pending).toBe(1);
    expect(parsed.docs[0]?.slots[0]?.status).toBe("skipped");
    expect(parsed.docs[0]?.slots[0]?.optional).toBe(true);
  });
});
