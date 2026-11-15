import { describe, expect, it } from "vitest";
import { ApiError } from "@shared/api";
import {
  CI_POLL_MS,
  PREVIEW_POLL_MS,
  ciPollInterval,
  previewPollInterval,
} from "../api/queries";
import type { PackCiStatus, PackPreviewBuild } from "../api/schemas";
import {
  errorNumber,
  forkRequired,
  lintFailure,
  mergeConflictFiles,
} from "./gitErrors";
import { findingTarget, versionRefOf } from "./packPaths";

const V = "hse-cs-sse/templates/coursework/versions/2026.1.7";

describe("поля отказов git Студии шаблонов", () => {
  it("merge_conflict отдаёт файлы, чужой код null", () => {
    const error = new ApiError("x", "merge_conflict", 409, {
      files: [`${V}/version.yaml`, 3],
    });
    expect(mergeConflictFiles(error)).toEqual([`${V}/version.yaml`]);
    expect(mergeConflictFiles(new ApiError("x", "workspace_dirty", 409))).toBe(
      null,
    );
  });

  it("lint_failed: находки по схеме, счётчики из тела", () => {
    const error = new ApiError("x", "lint_failed", 409, {
      errors: 2,
      warnings: 1,
      findings: [
        { severity: "error", check: "lint", path: V, message: "a" },
        { broken: true },
      ],
    });
    expect(lintFailure(error)).toEqual({
      errors: 2,
      warnings: 1,
      findings: [{ severity: "error", check: "lint", path: V, message: "a" }],
    });
    expect(lintFailure(new Error("x"))).toBe(null);
  });

  it("fork_required: can_create и причина повтора", () => {
    expect(
      forkRequired(
        new ApiError("x", "fork_required", 409, { can_create: true }),
      ),
    ).toEqual({ canCreate: true, reason: null });
    expect(
      forkRequired(
        new ApiError("x", "fork_required", 409, {
          reason: "fork_host_mismatch",
        }),
      ),
    ).toEqual({ canCreate: false, reason: "fork_host_mismatch" });
  });

  it("число из тела ошибки", () => {
    const error = new ApiError("x", "preview_quota", 429, { limit: 2 });
    expect(errorNumber(error, "limit")).toBe(2);
    expect(errorNumber(error, "other")).toBe(null);
  });
});

describe("опрос", () => {
  it("статус проверок опрашивается только пока pending", () => {
    const status = (state: PackCiStatus["state"]) =>
      ({ state }) as PackCiStatus;
    expect(ciPollInterval(status("pending"))).toBe(CI_POLL_MS);
    expect(CI_POLL_MS).toBe(30_000);
    expect(ciPollInterval(status("success"))).toBe(false);
    expect(ciPollInterval(status("failure"))).toBe(false);
    expect(ciPollInterval(undefined)).toBe(false);
  });

  it("сборка предпросмотра опрашивается в очереди и в работе", () => {
    const build = (status: PackPreviewBuild["status"]) =>
      ({ status }) as PackPreviewBuild;
    expect(previewPollInterval(build("queued"))).toBe(PREVIEW_POLL_MS);
    expect(previewPollInterval(build("running"))).toBe(PREVIEW_POLL_MS);
    expect(previewPollInterval(build("succeeded"))).toBe(false);
    expect(previewPollInterval(build("cancelled"))).toBe(false);
  });
});

describe("пути находок и версий", () => {
  it("версия шаблона в адресе предпросмотра", () => {
    expect(versionRefOf(`${V}/files/report/main.tex`)).toEqual({
      pack: "hse-cs-sse",
      template: "coursework",
      version: "2026.1.7",
    });
    expect(versionRefOf("hse-cs-sse/pack.yaml")).toBe(null);
  });

  it("находка каталога версии ведёт в файл и строку из сообщения или в манифест", () => {
    expect(findingTarget(V, "common/meta.tex.j2:2: Jinja")).toEqual({
      path: `${V}/files/common/meta.tex.j2`,
      line: 2,
    });
    expect(findingTarget(V, "version.yaml:5: bad")).toEqual({
      path: `${V}/version.yaml`,
      line: 5,
    });
    expect(findingTarget(V, "documents[0].id: обязательное поле")).toEqual({
      path: `${V}/version.yaml`,
      line: null,
    });
    expect(findingTarget(`${V}/files/a.tex`, "x")).toEqual({
      path: `${V}/files/a.tex`,
      line: null,
    });
    expect(findingTarget("hse-cs-sse/templates/coursework", "x")).toEqual({
      path: "hse-cs-sse/templates/coursework/template.yaml",
      line: null,
    });
    expect(findingTarget("hse-cs-sse", "x")).toEqual({
      path: "hse-cs-sse/pack.yaml",
      line: null,
    });
    expect(findingTarget(".", "база не прочиталась")).toBe(null);
  });
});
