import { describe, expect, it } from "vitest";
import { GIT_ERROR_CODES } from "@entities/git-sync";
import { i18n } from "@shared/lib/i18n";
import {
  HAS_OWN_COPY,
  SAVE_FAILED_CODE,
  bundleFailureTarget,
} from "./bundleFailure";

describe("адресат отказа импорта", () => {
  it.each([
    ["bundle_password_required", "password"],
    ["bundle_password_wrong", "password"],
    ["bundle_invalid", "file"],
    ["bundle_prerequisites_missing", "file"],
    ["unrelated_histories", "file"],
    ["not_a_studio_project", "file"],
    ["remote_schema_newer", "file"],
    ["profile_required", "profile"],
    ["sync_busy", "state"],
    ["off_branch", "state"],
    ["store_untrusted", "state"],
    [SAVE_FAILED_CODE, "state"],
    ["timeout", "other"],
    ["git_error", "other"],
  ])("%s ложится на %s", (code, target) => {
    expect(bundleFailureTarget(code)).toBe(target);
  });

  it("каждый код сервера из списка получает какого-то адресата", () => {
    const targets = ["password", "file", "profile", "state", "other"];
    for (const code of GIT_ERROR_CODES) {
      expect(targets).toContain(bundleFailureTarget(code));
    }
  });

  it("у каждого кода со своей формулировкой есть текст и подсказка на обоих языках", async () => {
    for (const lng of ["ru", "en"]) {
      await i18n.changeLanguage(lng);
      for (const code of HAS_OWN_COPY) {
        expect(i18n.exists(`gitExchange:failure.${code}.text`)).toBe(true);
        expect(i18n.exists(`gitExchange:failure.${code}.hint`)).toBe(true);
      }
    }
    await i18n.changeLanguage("ru");
  });
});
