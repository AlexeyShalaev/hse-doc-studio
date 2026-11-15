import { beforeAll, describe, expect, it } from "vitest";
import { ApiError } from "@shared/api";
import { i18n } from "@shared/lib";
import {
  catalogErrorText,
  isRevisionMoved,
  isSourceBusy,
  planBlockers,
  sourceErrorText,
} from "./errorText";

describe("тексты отказов каталогов паков", () => {
  beforeAll(async () => {
    await i18n.changeLanguage("ru");
  });

  it("код каталога переводится, незнакомый код даёт текст сервера", () => {
    expect(
      catalogErrorText(new ApiError("x", "revision_moved", 409, null)),
    ).toBe("Источник изменился после проверки. Проверьте его снова.");
    expect(
      catalogErrorText(new ApiError("Текст сервера", "from_the_future", 400)),
    ).toBe("Текст сервера");
  });

  it("коды git-синхронизации берутся из общих текстов", () => {
    expect(catalogErrorText(new ApiError("x", "auth_failed", 401))).toBe(
      i18n.t("errors:code.auth_failed"),
    );
  });

  it("ошибка последней проверки источника: перевод кода или текст сервера", () => {
    expect(
      sourceErrorText({ code: "archive_unsafe", detail: "detail" }),
    ).toContain("В архиве есть ссылки");
    expect(sourceErrorText({ code: "strange", detail: "как есть" })).toBe(
      "как есть",
    );
  });

  it("различает revision_moved, source_busy и препятствия плана", () => {
    const moved = new ApiError("x", "revision_moved", 409, {
      expected: "a",
      actual: "b",
    });
    expect(isRevisionMoved(moved)).toBe(true);
    expect(isSourceBusy(moved)).toBe(false);
    expect(isSourceBusy(new ApiError("x", "source_busy", 409))).toBe(true);
    expect(planBlockers(moved)).toBeNull();
    expect(
      planBlockers(
        new ApiError("x", "plan_blocked", 409, {
          blockers: ["version_changed", "nonsense", 3],
        }),
      ),
    ).toEqual(["version_changed"]);
    expect(planBlockers(new ApiError("x", "plan_blocked", 409))).toEqual([]);
  });
});
