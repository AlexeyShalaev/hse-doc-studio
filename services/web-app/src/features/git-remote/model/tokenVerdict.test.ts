import { describe, expect, it } from "vitest";
import { ApiError } from "@shared/api";
import { extraScopes, verdictOfCheck, verdictOfError } from "./tokenVerdict";

const info = (sufficiency: string) => ({
  login: "anna",
  scopes: ["read_repository"],
  expires_at: null,
  sufficiency,
  missing: [],
});

describe("verdictOfCheck", () => {
  it("права: достаточно, мало, слишком много, неизвестно", () => {
    for (const kind of ["sufficient", "too_narrow", "too_broad", "unknown"]) {
      expect(verdictOfCheck({ token_info: info(kind) }).kind).toBe(kind);
    }
  });

  it("незнакомое значение и отсутствие данных дают «неизвестно»", () => {
    expect(verdictOfCheck({ token_info: info("from_future") }).kind).toBe(
      "unknown",
    );
    expect(verdictOfCheck({ token_info: null })).toEqual({
      kind: "unknown",
      info: null,
    });
  });
});

describe("verdictOfError и extraScopes", () => {
  it("ошибка запроса сводится к отказу с кодом", () => {
    expect(
      verdictOfError(new ApiError("нет сети", "offline", 502)),
    ).toMatchObject({ kind: "error", code: "offline" });
    expect(verdictOfError(new Error("boom"))).toMatchObject({
      kind: "error",
      code: "git_error",
      detail: "boom",
    });
  });

  it("срок истёк и отказ сервера отличаются", () => {
    const expired = verdictOfError(
      new ApiError("d", "token_expired", 502),
      "2026-10-01T00:00:00Z",
    );
    expect(expired).toMatchObject({
      kind: "expired",
      info: { expires_at: "2026-10-01T00:00:00Z" },
    });
    expect(verdictOfError(new ApiError("d", "token_expired", 502))).toEqual({
      kind: "expired",
      info: null,
    });
    const certificate = {
      fingerprint_sha256: "SHA256:a",
      subject: "s",
      issuer: "i",
      not_before: "2026-01-01T00:00:00Z",
      not_after: "2027-01-01T00:00:00Z",
      self_signed: false,
    };
    expect(
      verdictOfError(
        new ApiError("d", "tls_untrusted_ca", 502, { certificate }),
      ),
    ).toMatchObject({ kind: "error", code: "tls_untrusted_ca", certificate });
  });

  it("лишние права берутся из списка слишком широких", () => {
    expect(extraScopes(info("too_broad"), ["api"])).toEqual([]);
    expect(
      extraScopes(
        { ...info("too_broad"), scopes: ["api", "read_repository"] },
        ["api", "sudo"],
      ),
    ).toEqual(["api"]);
    expect(extraScopes(null, ["api"])).toEqual([]);
  });
});
