import type { PackDiagnostic } from "@entities/pack-studio";

/** Замечания одного файла: сначала ошибки, затем по строкам; без строки (файл целиком) в конце. */
export const findingsOfFile = (
  findings: readonly PackDiagnostic[] | undefined,
  path: string,
): PackDiagnostic[] =>
  (findings ?? [])
    .filter((item) => item.path === path)
    .sort(
      (a, b) =>
        Number(b.severity === "error") - Number(a.severity === "error") ||
        (a.line ?? Number.MAX_SAFE_INTEGER) -
          (b.line ?? Number.MAX_SAFE_INTEGER),
    );
