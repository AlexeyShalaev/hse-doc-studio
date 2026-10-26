import { beforeEach, describe, expect, it } from "vitest";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib/i18n";
import { describeGitError, gitErrorMessage } from "./gitErrorMessage";

describe("gitErrorMessage", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });

  it("translates a known code and ignores the server text", () => {
    expect(gitErrorMessage("auth_failed", "denied")).toBe(
      "Сервер не принял доступ. Проверь токен или ключ.",
    );
  });

  it("follows the interface language", async () => {
    await i18n.changeLanguage("en");
    expect(gitErrorMessage("auth_failed", "denied")).not.toBe("denied");
    expect(gitErrorMessage("auth_failed", "denied")).not.toMatch(/[а-я]/i);
  });

  it("falls back to the server text for an unknown code", () => {
    expect(gitErrorMessage("from_the_future", "Текст сервера")).toBe(
      "Текст сервера",
    );
  });

  it("describes a caught request error by its code and extra fields", () => {
    const error = new ApiError("x", "sync_busy", 409, { operation_id: "op-1" });
    expect(describeGitError(error)).toBe("Синхронизация уже идёт.");
  });

  it("uses the server detail of an error without a translation", () => {
    expect(describeGitError(new ApiError("Что-то своё", "weird", 500))).toBe(
      "Что-то своё",
    );
  });

  it("falls back to the message of a plain error and then to the fallback", () => {
    expect(describeGitError(new Error("network down"))).toBe("network down");
    expect(describeGitError("???", "Запасной текст")).toBe("Запасной текст");
  });
});
