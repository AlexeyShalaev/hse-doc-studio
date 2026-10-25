import { describe, expect, it } from "vitest";
import {
  AttachDetachedResponseSchema,
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
