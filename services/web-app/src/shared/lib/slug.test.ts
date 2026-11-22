import { describe, expect, it } from "vitest";
import { slugify, uniqueSlug } from "./slug";

describe("slugify", () => {
  it("переводит русское название в латиницу", () => {
    expect(slugify("Анкета студента")).toBe("anketa_studenta");
    expect(slugify("Декларация об использовании ИИ", "-")).toBe(
      "deklaratsiya-ob-ispolzovanii-ii",
    );
    expect(slugify("Щука, ёж и Юла")).toBe("schuka_ezh_i_yula");
  });
  it("оставляет латиницу и цифры, лишнее превращает в разделитель", () => {
    expect(slugify("  Report 2026 (final)! ")).toBe("report_2026_final");
  });
  it("пустое, если букв нет", () => {
    expect(slugify("???")).toBe("");
  });
});

describe("uniqueSlug", () => {
  it("добавляет номер, если имя занято", () => {
    expect(uniqueSlug("report", ["report"])).toBe("report_2");
    expect(uniqueSlug("report", ["report", "report_2"])).toBe("report_3");
    expect(uniqueSlug("report", ["other"], "-")).toBe("report");
  });
});
