import { ApiError } from "@shared/api";
import {
  readGitError,
  type GitErrorBody,
  type GitHostKey,
  type GitTlsCertificate,
} from "@entities/git-sync";
import type { Probe } from "@entities/git-remote";

// Что показать после проверки адреса: чистые функции, без интерфейса. Ответ
// проверки (Probe) и ошибки подключения (PUT /remote) сводятся к одному исходу,
// по нему рисуется чек-лист и карточка результата.

export type CheckRowId = "reachable" | "auth" | "found" | "compatible";

export const CHECK_ROWS: readonly CheckRowId[] = [
  "reachable",
  "auth",
  "found",
  "compatible",
];

export type CheckRowState = "pending" | "running" | "ok" | "fail" | "skipped";

export type CheckIssue = {
  code: string;
  detail: string;
  hostKeys: GitHostKey[];
  /** Для remote_schema_newer и подобных: какая версия Студии нужна. */
  requiredStudio: string | null;
  /** Для unrelated_histories: можно ли объединить истории. */
  canAdopt: boolean | null;
  /** Для tls_untrusted_ca и tls_pin_mismatch: сертификат, который предъявил сервер. */
  certificate: GitTlsCertificate | null;
  /** Для tls_pin_mismatch: отпечаток, закреплённый раньше. */
  expectedFingerprint: string | null;
  /** Для tls_pin_mismatch: отпечаток, который сервер предъявил сейчас. */
  actualFingerprint: string | null;
  /** Для token_insufficient_scope: каких прав токену не хватает. */
  missing: string[];
};

export type ReadyWarning = "schema_newer" | "template_missing";

export type CheckOutcome =
  | {
      kind: "ready";
      variant: "empty" | "same" | "new";
      warnings: ReadyWarning[];
    }
  | { kind: "unrelated" }
  | { kind: "other_project" }
  | { kind: "not_studio" }
  | { kind: "error"; issue: CheckIssue };

const issueOf = (
  code: string,
  detail: string,
  extra: Partial<CheckIssue> = {},
): CheckIssue => ({
  code,
  detail,
  hostKeys: [],
  requiredStudio: null,
  canAdopt: null,
  certificate: null,
  expectedFingerprint: null,
  actualFingerprint: null,
  missing: [],
  ...extra,
});

/** Исход по ответу проверки адреса. */
export const outcomeFromProbe = (probe: Probe): CheckOutcome => {
  if (!probe.ok || probe.error) {
    const error = probe.error;
    return {
      kind: "error",
      issue: issueOf(error?.code ?? "git_error", error?.detail ?? "", {
        hostKeys: error?.host_keys ?? [],
        certificate: error?.certificate ?? null,
        expectedFingerprint: error?.expected ?? null,
        actualFingerprint: error?.actual ?? null,
        missing: probe.token_info?.missing ?? [],
      }),
    };
  }
  switch (probe.relation) {
    case "same_project_unrelated_history":
      return { kind: "unrelated" };
    case "other_project":
      return { kind: "other_project" };
    case "not_studio_project":
      return { kind: "not_studio" };
    default:
      break;
  }
  const warnings: ReadyWarning[] = [];
  if (probe.schema_access && probe.schema_access !== "full")
    warnings.push("schema_newer");
  if (probe.template_available === false) warnings.push("template_missing");
  const variant =
    probe.relation === "empty" || probe.empty
      ? "empty"
      : probe.relation === "same_project" || probe.relation === "studio_project"
        ? "same"
        : "new";
  return { kind: "ready", variant, warnings };
};

/** Исход по ошибке запроса: проверки (400, сеть) или подключения (409, 502). */
export const outcomeFromError = (error: unknown): CheckOutcome => {
  const body = readGitError(error);
  if (body) return outcomeFromBody(body);
  const detail =
    error instanceof ApiError
      ? error.detail
      : error instanceof Error
        ? error.message
        : "";
  return {
    kind: "error",
    issue: issueOf(
      error instanceof ApiError ? error.code : "git_error",
      detail,
    ),
  };
};

const outcomeFromBody = (body: GitErrorBody): CheckOutcome => {
  if (body.code === "not_a_studio_project") return { kind: "not_studio" };
  if (body.code === "unrelated_histories") {
    return body.can_adopt ? { kind: "unrelated" } : { kind: "other_project" };
  }
  return {
    kind: "error",
    issue: issueOf(body.code, body.detail, {
      hostKeys: body.host_keys ?? [],
      requiredStudio: body.required_studio ?? null,
      canAdopt: body.can_adopt ?? null,
      certificate: body.certificate ?? null,
      expectedFingerprint: body.expected ?? null,
      actualFingerprint: body.actual ?? null,
      missing: body.missing ?? [],
    }),
  };
};

// --- чек-лист --------------------------------------------------------------------

const REACHABILITY_CODES = new Set([
  "offline",
  "tls_error",
  "timeout",
  "ssh_unavailable",
  "git_unavailable",
  "url_invalid",
  "url_scheme_forbidden",
  "store_untrusted",
  "tls_untrusted_ca",
  "tls_pin_mismatch",
  "provider_unknown",
  "git_error",
]);

const AUTH_CODES = new Set([
  "auth_failed",
  "forbidden_write",
  "sso_required",
  "credentials_missing",
  "credential_host_mismatch",
  "secrets_unavailable",
  "host_key_unknown",
  "host_key_changed",
  "rate_limited",
  "email_privacy",
  "profile_required",
  "token_expired",
  "token_insufficient_scope",
]);

const FOUND_CODES = new Set(["not_found_or_no_access", "branch_missing"]);

export const rowOfCode = (code: string): CheckRowId => {
  if (AUTH_CODES.has(code)) return "auth";
  if (FOUND_CODES.has(code)) return "found";
  if (REACHABILITY_CODES.has(code)) return "reachable";
  return "reachable";
};

export type CheckPhase = "running" | "done";

/** Состояние каждой строки чек-листа. */
export const deriveRows = (
  phase: CheckPhase,
  outcome: CheckOutcome | null,
): Record<CheckRowId, CheckRowState> => {
  const rows: Record<CheckRowId, CheckRowState> = {
    reachable: "pending",
    auth: "pending",
    found: "pending",
    compatible: "pending",
  };
  if (phase === "running" || !outcome) {
    rows.reachable = "running";
    return rows;
  }
  const failing: CheckRowId | null =
    outcome.kind === "ready"
      ? null
      : outcome.kind === "error"
        ? rowOfCode(outcome.issue.code)
        : "compatible";
  const failIndex = failing ? CHECK_ROWS.indexOf(failing) : CHECK_ROWS.length;
  CHECK_ROWS.forEach((id, index) => {
    rows[id] =
      index < failIndex ? "ok" : index === failIndex ? "fail" : "skipped";
  });
  return rows;
};
