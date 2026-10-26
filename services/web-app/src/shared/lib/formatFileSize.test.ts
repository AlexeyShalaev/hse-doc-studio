import { afterEach, describe, expect, it } from "vitest";
import { i18n } from "@shared/lib/i18n";
import { formatFileSize } from "./formatFileSize";

describe("formatFileSize", () => {
  afterEach(async () => {
    await i18n.changeLanguage("ru");
  });

  it("выбирает единицу по порядку величины, степени 1024", async () => {
    await i18n.changeLanguage("en");
    expect(formatFileSize(0)).toBe("0 byte");
    expect(formatFileSize(512)).toBe("512 byte");
    expect(formatFileSize(2048)).toBe("2 kB");
    expect(formatFileSize(1_500_000)).toBe("1.4 MB");
    expect(formatFileSize(5 * 1024 ** 3)).toBe("5 GB");
  });

  it("пишет единицы по-русски", async () => {
    await i18n.changeLanguage("ru");
    expect(formatFileSize(14_800_000)).toMatch(/^14\s?МБ$/);
  });

  it("отрицательный размер считает нулём", () => {
    expect(formatFileSize(-5)).toMatch(/^0/);
  });
});
