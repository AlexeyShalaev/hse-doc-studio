import { describe, expect, it } from "vitest";
import {
  DATE_MARK_FORMATS,
  dateMarkFits,
  formatDateMark,
  longestDateText,
  todayInDisplayZone,
} from "./dateMarks";

// Текст метки даты (docs/design/signing-route.md, 14.3): тот же, что печатает сервер.

describe("formatDateMark", () => {
  const moment = "2026-11-13T07:30:00+00:00";

  it.each([
    ["day", "13", "13"],
    ["month_word", "ноября", "November"],
    ["month_number", "11", "11"],
    ["year", "2026", "2026"],
    ["year_short", "26", "26"],
    ["date_numeric", "13.11.2026", "13.11.2026"],
    ["date_long", "13 ноября 2026 г.", "13 November 2026"],
  ] as const)("%s: ru %s, en %s", (format, ru, en) => {
    expect(formatDateMark(moment, format, "ru")).toBe(ru);
    expect(formatDateMark(moment, format, "en")).toBe(en);
  });

  it("день без ведущего нуля, месяц числом с ним", () => {
    expect(formatDateMark("2026-03-03", "day", "ru")).toBe("3");
    expect(formatDateMark("2026-03-03", "month_number", "ru")).toBe("03");
    expect(formatDateMark("2009-03-03", "year_short", "ru")).toBe("09");
  });

  it("месяц словом в родительном падеже", () => {
    const months = Array.from({ length: 12 }, (_, i) =>
      formatDateMark(
        `2026-${String(i + 1).padStart(2, "0")}-01`,
        "month_word",
        "ru",
      ),
    );
    expect(months).toEqual([
      "января",
      "февраля",
      "марта",
      "апреля",
      "мая",
      "июня",
      "июля",
      "августа",
      "сентября",
      "октября",
      "ноября",
      "декабря",
    ]);
  });

  it("момент переводится в московское время: 23:30 UTC это следующий день", () => {
    expect(formatDateMark("2026-11-12T23:30:00Z", "date_numeric", "ru")).toBe(
      "13.11.2026",
    );
    expect(todayInDisplayZone(Date.parse("2026-12-31T22:00:00Z"))).toBe(
      "2027-01-01",
    );
  });

  it("ручная дата это день без пояса", () => {
    expect(formatDateMark("2026-11-13", "date_long", "ru")).toBe(
      "13 ноября 2026 г.",
    );
  });

  it("неразборчивый момент даёт пустой текст", () => {
    expect(formatDateMark("вчера", "day", "ru")).toBe("");
  });
});

describe("рамка метки", () => {
  it("самый длинный текст формата за год", () => {
    expect(longestDateText("month_word", "ru")).toBe("сентября");
    expect(longestDateText("date_long", "en")).toBe("28 September 2026");
    expect(DATE_MARK_FORMATS).toHaveLength(7);
  });

  it("текст не влезает шестым кеглем в узкую или низкую рамку", () => {
    expect(dateMarkFits("13", 8, 5)).toBe(true);
    expect(dateMarkFits("сентября", 22, 5)).toBe(true);
    expect(dateMarkFits("13 ноября 2026 г.", 10, 5)).toBe(false);
    expect(dateMarkFits("13", 8, 2)).toBe(false);
  });
});
