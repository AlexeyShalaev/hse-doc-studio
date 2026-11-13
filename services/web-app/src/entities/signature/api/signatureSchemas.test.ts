import { describe, expect, it } from "vitest";
import {
  packDatesOf,
  packEntryOf,
  packHasMmPlace,
  packPlaceOf,
} from "../lib/packPlaces";
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

describe("места пака на якорях (15.17.14)", () => {
  const slot = {
    id: "supervisor",
    label: { ru: "Научный руководитель" },
    applies_to: ["topic_application", "project_proposal", "report"],
    default_placement: { page: 1, x_mm: 110, y_mm: 130, width_mm: 40 },
  };
  const parsed = RuntimeSignatureSlotSchema.parse({
    ...slot,
    default_placements: {
      topic_application: {
        source: "anchor",
        anchor: "supervisor",
        align: "right",
        dx_mm: 0,
        dy_mm: -10,
        width_mm: 28,
        fallback: null,
      },
      project_proposal: {
        source: "anchor",
        anchor: "supervisor",
        align: "left",
        dx_mm: 0,
        dy_mm: -14,
        width_mm: 40,
        fallback: { page: 1, x_mm: 80, y_mm: 139, width_mm: 40 },
      },
      report: { source: "mm", page: 1, x_mm: 110, y_mm: 130, width_mm: 40 },
    },
    default_dates: {
      project_proposal: [
        {
          source: "anchor",
          anchor: "supervisor.day",
          format: "day",
          align: "center",
          height_mm: 5,
          width_mm: null,
          dx_mm: 0,
          dy_mm: null,
          fallback: null,
        },
        {
          source: "anchor",
          anchor: "supervisor.month_word",
          format: "month_word",
          align: "center",
          height_mm: 5,
          width_mm: 24,
          dx_mm: 0,
          dy_mm: null,
          fallback: {
            page: 1,
            x_mm: 90,
            y_mm: 148,
            width_mm: 24,
            height_mm: 5,
          },
        },
        {
          source: "mm",
          page: 1,
          x_mm: 150,
          y_mm: 148,
          width_mm: 6,
          height_mm: 5,
          format: "year_short",
          align: "left",
        },
      ],
    },
  });

  it("записи по документам остаются как есть, по дискриминатору source", () => {
    expect(parsed.default_placements.topic_application).toMatchObject({
      source: "anchor",
      anchor: "supervisor",
      fallback: null,
    });
    expect(parsed.default_placements.report).toEqual({
      source: "mm",
      page: 1,
      x_mm: 110,
      y_mm: 130,
      width_mm: 40,
    });
    expect(parsed.default_dates.project_proposal).toHaveLength(3);
  });

  it("запись без source и с чужим source отвергается", () => {
    expect(
      RuntimeSignatureSlotSchema.safeParse({
        ...slot,
        default_placements: {
          report: { page: 1, x_mm: 110, y_mm: 130, width_mm: 40 },
        },
      }).success,
    ).toBe(false);
    expect(
      RuntimeSignatureSlotSchema.safeParse({
        ...slot,
        default_placements: {
          report: { source: "px", page: 1, x_mm: 1, y_mm: 1, width_mm: 40 },
        },
      }).success,
    ).toBe(false);
  });

  it("место в мм: запись в мм, запасное место записи на якоре, иначе общее место слота", () => {
    expect(packPlaceOf(parsed, "report")).toEqual({
      page: 1,
      x_mm: 110,
      y_mm: 130,
      width_mm: 40,
    });
    expect(packPlaceOf(parsed, "project_proposal")).toEqual({
      page: 1,
      x_mm: 80,
      y_mm: 139,
      width_mm: 40,
    });
    expect(packPlaceOf(parsed, "topic_application")).toEqual(
      slot.default_placement,
    );
    expect(packHasMmPlace(parsed, "topic_application")).toBe(false);
    expect(packHasMmPlace(parsed, "project_proposal")).toBe(true);
    expect(packHasMmPlace(parsed, "report")).toBe(true);
    expect(packEntryOf(parsed, "other")).toBeUndefined();
  });

  it("метки даты в мм: метка на якоре берёт запасное место, без него пропускается", () => {
    expect(packDatesOf(parsed, "project_proposal")).toEqual([
      {
        page: 1,
        x_mm: 90,
        y_mm: 148,
        width_mm: 24,
        height_mm: 5,
        format: "month_word",
        align: "center",
      },
      {
        page: 1,
        x_mm: 150,
        y_mm: 148,
        width_mm: 6,
        height_mm: 5,
        format: "year_short",
        align: "left",
      },
    ]);
  });

  it("состояние подписей несёт якоря сборки; без поля якорей нет", () => {
    const state = SignaturesStateSchema.parse({
      slots: {},
      placements: {},
      anchors: {
        topic_application: {
          build: "5f0c2b8e1d7a4c3b",
          items: [
            {
              id: "supervisor",
              kind: "sign",
              page: 1,
              x_mm: 169.5,
              y_mm: 186.8,
              width_mm: 25.5,
            },
          ],
          problems: [],
        },
        report: null,
      },
    });
    expect(state.anchors.topic_application?.items[0]?.id).toBe("supervisor");
    expect(state.anchors.report).toBeNull();
    expect(
      SignaturesStateSchema.parse({ slots: {}, placements: {} }).anchors,
    ).toEqual({});
  });
});
