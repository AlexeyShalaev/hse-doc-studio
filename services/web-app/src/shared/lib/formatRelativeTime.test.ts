import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { i18n } from "./i18n";
import { formatPastTime, formatRelativeTime } from "./formatRelativeTime";

const NOW = new Date("2026-10-26T12:00:00Z");
const ago = (seconds: number): Date => new Date(NOW.getTime() - seconds * 1000);

describe("formatRelativeTime (ru)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });
  afterAll(async () => {
    await i18n.changeLanguage("ru");
  });

  it("says «сейчас» for a few seconds", () => {
    expect(formatRelativeTime(ago(3), NOW)).toBe("сейчас");
    expect(formatRelativeTime(ago(0), NOW)).toBe("сейчас");
  });

  it("uses the right plural forms", () => {
    expect(formatRelativeTime(ago(40), NOW)).toBe("40 секунд назад");
    expect(formatRelativeTime(ago(60), NOW)).toBe("1 минуту назад");
    expect(formatRelativeTime(ago(3 * 60), NOW)).toBe("3 минуты назад");
    expect(formatRelativeTime(ago(5 * 60), NOW)).toBe("5 минут назад");
    expect(formatRelativeTime(ago(2 * 3600), NOW)).toBe("2 часа назад");
  });

  it("names yesterday and counts days, months, years", () => {
    expect(formatRelativeTime(ago(24 * 3600), NOW)).toBe("вчера");
    expect(formatRelativeTime(ago(3 * 86400), NOW)).toBe("3 дня назад");
    expect(formatRelativeTime(ago(65 * 86400), NOW)).toBe("2 месяца назад");
    expect(formatRelativeTime(ago(800 * 86400), NOW)).toBe("2 года назад");
  });

  it("handles the future (next fetch)", () => {
    expect(formatRelativeTime(new Date(NOW.getTime() + 5 * 60000), NOW)).toBe(
      "через 5 минут",
    );
  });

  it("accepts ISO strings and epoch milliseconds", () => {
    expect(formatRelativeTime("2026-10-26T11:57:00Z", NOW)).toBe(
      "3 минуты назад",
    );
    expect(formatRelativeTime(NOW.getTime() - 5 * 60000, NOW)).toBe(
      "5 минут назад",
    );
  });

  it("returns an empty string for missing or invalid input", () => {
    expect(formatRelativeTime(null, NOW)).toBe("");
    expect(formatRelativeTime(undefined, NOW)).toBe("");
    expect(formatRelativeTime("", NOW)).toBe("");
    expect(formatRelativeTime("not a date", NOW)).toBe("");
  });
});

describe("formatRelativeTime (en)", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("en");
  });
  afterAll(async () => {
    await i18n.changeLanguage("ru");
  });

  it("formats in English", () => {
    expect(formatRelativeTime(ago(2), NOW)).toBe("now");
    expect(formatRelativeTime(ago(3 * 60), NOW)).toBe("3 minutes ago");
    expect(formatRelativeTime(ago(60), NOW)).toBe("1 minute ago");
    expect(formatRelativeTime(ago(24 * 3600), NOW)).toBe("yesterday");
    expect(formatRelativeTime(new Date(NOW.getTime() + 2 * 3600000), NOW)).toBe(
      "in 2 hours",
    );
  });
});

describe("formatPastTime", () => {
  beforeEach(async () => {
    await i18n.changeLanguage("ru");
  });

  it("never talks about the future for an event that already happened", () => {
    // «Сейчас» страницы отстало от события на 20 секунд (тик раз в 30 секунд).
    const event = new Date(NOW.getTime() + 20_000);
    expect(formatRelativeTime(event, NOW)).toBe("через 20 секунд");
    expect(formatPastTime(event, NOW)).toBe("сейчас");
  });

  it("counts the age as usual otherwise and ignores empty values", () => {
    expect(formatPastTime(ago(3 * 60), NOW)).toBe("3 минуты назад");
    expect(formatPastTime(null, NOW)).toBe("");
    expect(formatPastTime("не дата", NOW)).toBe("");
  });
});
