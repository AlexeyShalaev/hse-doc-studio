import { describe, expect, it } from "vitest";
import { ApiError } from "@shared/api";
import type { Probe } from "@entities/git-remote";
import {
  deriveRows,
  outcomeFromError,
  outcomeFromProbe,
  rowOfCode,
} from "./probeOutcome";
import { issueCopyOf } from "./issueCopy";

const probe = (overrides: Partial<Probe> = {}): Probe => ({
  ok: true,
  error: null,
  url: {
    display_url: "https://github.com/hse/paper",
    kind: "https",
    host: "github.com",
    provider: "github",
    owner: "hse",
    repo: "paper",
    token_stripped: false,
  },
  reachable: true,
  auth_ok: true,
  empty: false,
  default_branch: "main",
  branches: ["main"],
  relation: "same_project",
  project: null,
  schema_access: "full",
  required_studio: null,
  template_available: true,
  ...overrides,
});

describe("outcomeFromProbe", () => {
  it("пустой репозиторий", () => {
    expect(outcomeFromProbe(probe({ relation: "empty", empty: true }))).toEqual(
      { kind: "ready", variant: "empty", warnings: [] },
    );
  });

  it("тот же проект и проект Студии без сравнения", () => {
    expect(outcomeFromProbe(probe())).toMatchObject({
      kind: "ready",
      variant: "same",
    });
    expect(
      outcomeFromProbe(probe({ relation: "studio_project" })),
    ).toMatchObject({ variant: "same" });
    expect(outcomeFromProbe(probe({ relation: "unknown" }))).toMatchObject({
      variant: "new",
    });
  });

  it("отдельная история, другой проект, не проект Студии", () => {
    expect(
      outcomeFromProbe(probe({ relation: "same_project_unrelated_history" })),
    ).toEqual({ kind: "unrelated" });
    expect(outcomeFromProbe(probe({ relation: "other_project" }))).toEqual({
      kind: "other_project",
    });
    expect(outcomeFromProbe(probe({ relation: "not_studio_project" }))).toEqual(
      { kind: "not_studio" },
    );
  });

  it("предупреждения: проект новее Студии и нет шаблона", () => {
    expect(
      outcomeFromProbe(
        probe({
          schema_access: "read_only",
          required_studio: "0.4.0",
          template_available: false,
        }),
      ),
    ).toEqual({
      kind: "ready",
      variant: "same",
      warnings: ["schema_newer", "template_missing"],
    });
  });

  it("отказ несёт код, подробности и ключи сервера", () => {
    const keys = [{ type: "ssh-ed25519", fingerprint_sha256: "SHA256:abc" }];
    expect(
      outcomeFromProbe(
        probe({
          ok: false,
          error: { code: "host_key_unknown", detail: "d", host_keys: keys },
        }),
      ),
    ).toEqual({
      kind: "error",
      issue: {
        code: "host_key_unknown",
        detail: "d",
        hostKeys: keys,
        requiredStudio: null,
        canAdopt: null,
        certificate: null,
        expectedFingerprint: null,
        actualFingerprint: null,
        missing: [],
      },
    });
  });

  it("сертификат сервера и недостающие права доходят до карточки отказа", () => {
    const certificate = {
      fingerprint_sha256: "SHA256:abc",
      subject: "CN=gitlab.hse.local",
      issuer: "CN=HSE Internal CA",
      not_before: "2026-01-10T00:00:00Z",
      not_after: "2027-01-10T00:00:00Z",
      self_signed: false,
    };
    const tls = outcomeFromProbe(
      probe({
        ok: false,
        error: { code: "tls_untrusted_ca", detail: "d", certificate },
      }),
    );
    expect(tls).toMatchObject({
      kind: "error",
      issue: { code: "tls_untrusted_ca", certificate },
    });
    expect(rowOfCode("tls_untrusted_ca")).toBe("reachable");

    const mismatch = outcomeFromProbe(
      probe({
        ok: false,
        error: {
          code: "tls_pin_mismatch",
          detail: "d",
          expected: "SHA256:old",
          actual: "SHA256:new",
        },
      }),
    );
    expect(mismatch).toMatchObject({
      kind: "error",
      issue: {
        code: "tls_pin_mismatch",
        expectedFingerprint: "SHA256:old",
        actualFingerprint: "SHA256:new",
      },
    });

    const narrow = outcomeFromProbe(
      probe({
        ok: false,
        error: { code: "token_insufficient_scope", detail: "d" },
        token_info: {
          login: "anna",
          scopes: ["read_repository"],
          expires_at: null,
          sufficiency: "too_narrow",
          missing: ["write_repository"],
        },
      }),
    );
    expect(narrow).toMatchObject({
      kind: "error",
      issue: { missing: ["write_repository"] },
    });
    expect(rowOfCode("token_insufficient_scope")).toBe("auth");
    expect(rowOfCode("token_expired")).toBe("auth");
  });
});

describe("outcomeFromError", () => {
  it("разбирает плоское тело ошибки подключения", () => {
    const error = new ApiError("Другая история", "unrelated_histories", 409, {
      can_adopt: true,
    });
    expect(outcomeFromError(error)).toEqual({ kind: "unrelated" });
    expect(
      outcomeFromError(
        new ApiError("Другая история", "unrelated_histories", 409, {
          can_adopt: false,
        }),
      ),
    ).toEqual({ kind: "other_project" });
    expect(
      outcomeFromError(new ApiError("Не Студия", "not_a_studio_project", 409)),
    ).toEqual({ kind: "not_studio" });
  });

  it("обычная ошибка и сетевой сбой дают понятный отказ", () => {
    expect(
      outcomeFromError(new ApiError("Нужен токен", "credentials_missing", 409)),
    ).toMatchObject({ kind: "error", issue: { code: "credentials_missing" } });
    expect(outcomeFromError(new Error("Network Error"))).toMatchObject({
      kind: "error",
      issue: { code: "git_error", detail: "Network Error" },
    });
  });
});

describe("чек-лист", () => {
  it("пока идёт проверка, работает первая строка", () => {
    expect(deriveRows("running", null)).toEqual({
      reachable: "running",
      auth: "pending",
      found: "pending",
      compatible: "pending",
    });
  });

  it("успех закрывает все строки", () => {
    expect(
      deriveRows("done", { kind: "ready", variant: "same", warnings: [] }),
    ).toEqual({
      reachable: "ok",
      auth: "ok",
      found: "ok",
      compatible: "ok",
    });
  });

  it("отказ доступа: до него хорошо, после него пропущено", () => {
    const outcome = outcomeFromError(new ApiError("нет", "auth_failed", 502));
    expect(deriveRows("done", outcome)).toEqual({
      reachable: "ok",
      auth: "fail",
      found: "skipped",
      compatible: "skipped",
    });
  });

  it("несовместимая история ломает последнюю строку", () => {
    expect(deriveRows("done", { kind: "other_project" })).toEqual({
      reachable: "ok",
      auth: "ok",
      found: "ok",
      compatible: "fail",
    });
  });

  it("каждый код отнесён к своей строке", () => {
    expect(rowOfCode("offline")).toBe("reachable");
    expect(rowOfCode("host_key_changed")).toBe("auth");
    expect(rowOfCode("branch_missing")).toBe("found");
    expect(rowOfCode("something_new")).toBe("reachable");
  });
});

describe("тон и действия отказов", () => {
  it("у известных кодов есть своя подача, у неизвестных общая", () => {
    expect(issueCopyOf("auth_failed").actions[0]).toBe("back_to_access");
    expect(issueCopyOf("offline").tone).toBe("info");
    expect(issueCopyOf("weird").actions).toContain("retry");
  });
});
