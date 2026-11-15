import { describe, expect, it } from "vitest";
import type { PackDiagnostic } from "@entities/pack-studio";
import { findingsToDiagnostics, groupFindings, relativeTo } from "./findings";

const V = "p/templates/t/versions/2026.1.0";
const at = (patch: Partial<PackDiagnostic>): PackDiagnostic => ({
  severity: "error",
  check: "lint",
  message: "m",
  path: null,
  line: null,
  pointer: null,
  ...patch,
});

const FINDINGS: PackDiagnostic[] = [
  at({ message: "версия", severity: "warning" }),
  at({
    message: "манифест",
    path: `${V}/version.yaml`,
    line: 12,
    check: "schema",
  }),
  at({ message: "без строки", path: `${V}/version.yaml`, severity: "warning" }),
  at({ message: "шаблон", path: `${V}/files/common/meta.tex.j2`, line: 3 }),
];

describe("находки для редактора и «Проблем»", () => {
  it("в строку редактора только находки открытого файла со строкой", () => {
    expect(findingsToDiagnostics(FINDINGS, `${V}/version.yaml`)).toEqual([
      { line: 12, severity: "error", message: "манифест", source: "schema" },
    ]);
  });

  it("раскладка: этот файл (ошибки первыми), другие файлы, версия целиком", () => {
    const groups = groupFindings(FINDINGS, `${V}/version.yaml`);
    expect(groups.here.map((f) => f.message)).toEqual([
      "манифест",
      "без строки",
    ]);
    expect(groups.others.map(([file]) => file)).toEqual([
      `${V}/files/common/meta.tex.j2`,
    ]);
    expect(groups.version.map((f) => f.message)).toEqual(["версия"]);
  });

  it("путь от каталога версии", () => {
    expect(relativeTo(`${V}/files/a.tex`, V)).toBe("files/a.tex");
    expect(relativeTo("other/a.tex", V)).toBe("other/a.tex");
    expect(relativeTo("other/a.tex", null)).toBe("other/a.tex");
  });
});
