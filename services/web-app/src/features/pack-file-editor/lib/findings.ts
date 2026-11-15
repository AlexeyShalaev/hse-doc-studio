import type { PackDiagnostic } from "@entities/pack-studio";
import type { EditorDiagnostic } from "@shared/ui";

/** Находки открытого файла со строкой: в строку редактора (схема и линтер подписаны источником). */
export const findingsToDiagnostics = (
  findings: readonly PackDiagnostic[],
  path: string,
): EditorDiagnostic[] =>
  findings
    .filter((f) => f.path === path && f.line !== null)
    .map((f) => ({
      line: f.line ?? 1,
      severity: f.severity,
      message: f.message,
      source: f.check,
    }));

export type GroupedFindings = {
  /** Находки открытого файла. */
  here: PackDiagnostic[];
  /** Другие файлы той же версии: путь и его находки, в порядке путей. */
  others: [string, PackDiagnostic[]][];
  /** Версия целиком: файл не определён. */
  version: PackDiagnostic[];
};

const bySeverity = (a: PackDiagnostic, b: PackDiagnostic): number =>
  a.severity === b.severity
    ? (a.line ?? 0) - (b.line ?? 0)
    : a.severity === "error"
      ? -1
      : 1;

/** Раскладка находок для панели «Проблемы»: этот файл, другие файлы, версия целиком. */
export const groupFindings = (
  findings: readonly PackDiagnostic[],
  path: string,
): GroupedFindings => {
  const here: PackDiagnostic[] = [];
  const version: PackDiagnostic[] = [];
  const others = new Map<string, PackDiagnostic[]>();
  for (const finding of findings) {
    if (finding.path === null) version.push(finding);
    else if (finding.path === path) here.push(finding);
    else {
      const list = others.get(finding.path) ?? [];
      list.push(finding);
      others.set(finding.path, list);
    }
  }
  return {
    here: here.sort(bySeverity),
    others: [...others.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([file, list]) => [file, list.sort(bySeverity)]),
    version: version.sort(bySeverity),
  };
};

/** Путь от каталога версии (короче в списке): `files/report/main.tex`. */
export const relativeTo = (path: string, base: string | null): string =>
  base && path.toLowerCase().startsWith(`${base.toLowerCase()}/`)
    ? path.slice(base.length + 1)
    : path;
