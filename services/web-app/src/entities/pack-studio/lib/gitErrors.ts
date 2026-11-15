import { ApiError } from "@shared/api";
import { PackCheckFindingSchema, type PackCheckFinding } from "../api/schemas";

// Поля отказов git Студии шаблонов (contracts/pack-studio/README.md): тело ошибки
// {detail, code, ...} разбирает ApiError, поля по коду лежат в `data`.

const codeOf = (error: unknown): string | null =>
  error instanceof ApiError ? error.code : null;

/** merge_conflict: файлы конфликта от папки паков; иначе null. */
export const mergeConflictFiles = (error: unknown): string[] | null => {
  if (codeOf(error) !== "merge_conflict") return null;
  const files = (error as ApiError).data?.files;
  return Array.isArray(files)
    ? files.filter((f): f is string => typeof f === "string")
    : [];
};

export type LintFailure = {
  errors: number;
  warnings: number;
  findings: PackCheckFinding[];
};

/** lint_failed: находки проверки пака перед отправкой; иначе null. */
export const lintFailure = (error: unknown): LintFailure | null => {
  if (codeOf(error) !== "lint_failed") return null;
  const data = (error as ApiError).data ?? {};
  const raw = Array.isArray(data.findings) ? data.findings : [];
  const findings = raw.flatMap((item: unknown) => {
    const parsed = PackCheckFindingSchema.safeParse(item);
    return parsed.success ? [parsed.data] : [];
  });
  const count = (value: unknown, fallback: number): number =>
    typeof value === "number" ? value : fallback;
  return {
    errors: count(
      data.errors,
      findings.filter((f) => f.severity === "error").length,
    ),
    warnings: count(data.warnings, 0),
    findings,
  };
};

export type ForkRequired = {
  /** Форк можно создать токеном (только GitHub). */
  canCreate: boolean;
  /** fork_host_mismatch или fork_unavailable у повтора с форком. */
  reason: string | null;
};

/** fork_required: нужен форк; иначе null. */
export const forkRequired = (error: unknown): ForkRequired | null => {
  if (codeOf(error) !== "fork_required") return null;
  const data = (error as ApiError).data ?? {};
  return {
    canCreate: data.can_create === true,
    reason: typeof data.reason === "string" ? data.reason : null,
  };
};

/** Число из тела ошибки (limit у preview_quota и другие); иначе null. */
export const errorNumber = (error: unknown, field: string): number | null => {
  if (!(error instanceof ApiError)) return null;
  const value = error.data?.[field];
  return typeof value === "number" ? value : null;
};
