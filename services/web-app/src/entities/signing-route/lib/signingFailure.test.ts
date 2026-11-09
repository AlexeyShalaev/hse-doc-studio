import { describe, expect, it } from "vitest";
import { ApiError } from "@shared/api";
import en from "@shared/lib/i18n/locales/en/signing/signing.json";
import ru from "@shared/lib/i18n/locales/ru/signing/signing.json";
import { SIGNING_TASK_FAILURE_CODES, signingFailureOf } from "./signingFailure";

describe("отказы страницы подписанта", () => {
  it("у каждого известного кода есть текст на обоих языках", () => {
    for (const code of [...SIGNING_TASK_FAILURE_CODES, "unknown"]) {
      expect(ru.failure, code).toHaveProperty(code);
      expect(en.failure, code).toHaveProperty(code);
    }
  });

  it("известный код остаётся кодом, недоступный сервер это network", () => {
    expect(
      signingFailureOf(new ApiError("Wrong", "passphrase_invalid", 409)),
    ).toEqual({ code: "passphrase_invalid", detail: null });
    expect(signingFailureOf(new ApiError("Network Error", "x", 0))).toEqual({
      code: "network",
      detail: null,
    });
  });

  it("отказ без своего текста несёт пояснение сервера, кроме 5xx", () => {
    expect(
      signingFailureOf(
        new ApiError("Неверный пароль контейнера", "unknown_error", 400),
      ),
    ).toEqual({ code: "unknown", detail: "Неверный пароль контейнера" });
    expect(
      signingFailureOf(new ApiError("Internal Server Error", "x", 500)),
    ).toEqual({ code: "unknown", detail: null });
    expect(signingFailureOf(new Error("boom"))).toEqual({
      code: "unknown",
      detail: null,
    });
  });
});
