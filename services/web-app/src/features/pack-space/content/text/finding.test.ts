import { describe, expect, it } from "vitest";
import type { PackDiagnostic } from "@entities/pack-studio";
import { nearField, pickFinding, suggestFix } from "./finding";

const PATH = "p/templates/t/versions/v/files/doc/main.tex";
const item = (patch: Partial<PackDiagnostic>): PackDiagnostic => ({
  severity: "warning",
  check: "lint",
  message: "m",
  path: PATH,
  line: 1,
  pointer: null,
  ...patch,
});

describe("pickFinding", () => {
  it("берёт ближайшее к курсору, чужие файлы пропускает", () => {
    const list = [
      item({ line: 3, message: "a" }),
      item({ line: 40, message: "b" }),
      item({ line: 41, path: "other.tex", message: "c" }),
    ];
    expect(pickFinding(list, PATH, 38)?.message).toBe("b");
    expect(pickFinding(list, PATH, 1)?.message).toBe("a");
    expect(pickFinding([], PATH, 1)).toBeNull();
    expect(pickFinding(undefined, PATH, 1)).toBeNull();
  });

  it("при равном расстоянии ошибка раньше предупреждения, без строки в конце", () => {
    const list = [
      item({ line: null, message: "no-line" }),
      item({ line: 5, severity: "warning", message: "w" }),
      item({ line: 7, severity: "error", message: "e" }),
    ];
    expect(pickFinding(list, PATH, 6)?.message).toBe("e");
    expect(pickFinding([list[0] as PackDiagnostic], PATH, 6)?.message).toBe(
      "no-line",
    );
  });
});

describe("nearField", () => {
  const fields = ["name_short", "name_full", "topic"];
  it.each([
    ["name_shrt", "name_short"],
    ["Topic", "topic"],
    ["topik", "topic"],
    ["zzzzzz", null],
    ["name_short", null],
  ])("%s -> %s", (key, expected) => {
    expect(nearField(key, fields)).toBe(expected);
  });

  it("два равных кандидата не угадываются", () => {
    expect(nearField("name_x", ["name_a", "name_b"])).toBeNull();
  });
});

describe("suggestFix", () => {
  const text =
    "a\nКраткое: {{ meta.name_shrt }} и {{ project.meta.name_shrt }}\n";
  const finding = item({
    line: null,
    message:
      "Шаблон files/doc/main.tex читает project.meta.name_shrt, а такого поля нет в meta_fields версии.",
  });

  it("находит строку и исправляет все вхождения поля", () => {
    const fix = suggestFix(finding, text, ["name_short"]);
    expect(fix).toMatchObject({
      wrong: "name_shrt",
      right: "name_short",
      line: 2,
    });
    expect(fix?.apply(text)).toBe(
      "a\nКраткое: {{ meta.name_short }} и {{ project.meta.name_short }}\n",
    );
  });

  it("без похожего поля, без поля в замечании или в тексте исправления нет", () => {
    expect(suggestFix(finding, text, ["topic"])).toBeNull();
    expect(
      suggestFix(item({ message: "нет места" }), text, ["name_short"]),
    ).toBeNull();
    expect(suggestFix(finding, "ничего", ["name_short"])).toBeNull();
  });

  it("не трогает поле с продолжением имени", () => {
    const fix = suggestFix(finding, "{{ meta.name_shrt_long }}", [
      "name_short",
    ]);
    expect(fix).toBeNull();
  });
});
