import type { z } from "zod";
import type { CheckResultsResponseSchema } from "@entities/document";
import { toPosixPath } from "@shared/lib";
import type { CheckSeverity } from "@shared/api/types";
import type { EditorDiagnostic } from "@shared/ui";

export type CheckResult = z.infer<
  typeof CheckResultsResponseSchema
>["results"][number];

/** Per-rule severity overrides (checks_override.severity_override). */
export type SeverityOverride = Record<string, CheckSeverity>;

const SEVERITY_MAP: Record<
  CheckResult["severity"],
  EditorDiagnostic["severity"]
> = {
  info: "info",
  warn: "warning",
  err: "error",
};

/**
 * Map one finding to an editor diagnostic, or null if it has no concrete line
 * (file-level checks, LaTeX errors without an `l.NNN` marker — can't be placed).
 *
 * `severityOverride` is applied optimistically so a severity change reflects
 * instantly (and for any rule id, incl. LanguageTool `lt:*`), without waiting
 * for the backend to re-resolve on the next read.
 */
export const resultToDiagnostic = (
  result: CheckResult,
  severityOverride?: SeverityOverride,
): EditorDiagnostic | null => {
  const line = result.location?.line;
  if (typeof line !== "number") return null;
  const severity = severityOverride?.[result.rule_id] ?? result.severity;
  return {
    line,
    severity: SEVERITY_MAP[severity],
    message: result.message,
    source: result.rule_id,
    ...(result.fix
      ? {
          fix: {
            search: result.fix.search,
            replace: result.fix.replace,
            line: result.fix.line ?? null,
            title: result.fix.title ?? null,
          },
        }
      : {}),
  };
};

/**
 * Gutter/inline diagnostics for one open file: findings located in
 * `relativePath` that carry a concrete line.
 */
export const findingsToDiagnostics = (
  results: readonly CheckResult[] | undefined,
  relativePath: string,
  severityOverride?: SeverityOverride,
): EditorDiagnostic[] => {
  if (!results) return [];
  const target = toPosixPath(relativePath);
  const out: EditorDiagnostic[] = [];
  for (const result of results) {
    const file = result.location?.file;
    if (file == null || toPosixPath(file) !== target) continue;
    const diagnostic = resultToDiagnostic(result, severityOverride);
    if (diagnostic) out.push(diagnostic);
  }
  return out;
};
