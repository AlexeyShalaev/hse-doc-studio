// Как подать причину отказа: тон карточки и что можно сделать. Тексты лежат в
// переводах (gitRemote:issue.<код>.title и .hint); для кодов без своих слов
// берётся общий заголовок и текст из errors:code.<код>.

export type IssueTone = "err" | "warn" | "info";

export type IssueAction =
  | "retry"
  | "back_to_repo"
  | "back_to_access"
  | "review_host_key"
  | "review_certificate"
  | "close";

export type IssueCopy = {
  tone: IssueTone;
  /** Первое действие главное, остальные второстепенные. */
  actions: IssueAction[];
};

const COPY: Record<string, IssueCopy> = {
  auth_failed: { tone: "err", actions: ["back_to_access", "retry"] },
  forbidden_write: { tone: "err", actions: ["back_to_access", "retry"] },
  sso_required: { tone: "warn", actions: ["retry", "back_to_access"] },
  credentials_missing: { tone: "warn", actions: ["back_to_access"] },
  credential_host_mismatch: { tone: "err", actions: ["back_to_access"] },
  not_found_or_no_access: {
    tone: "err",
    actions: ["back_to_repo", "back_to_access", "retry"],
  },
  branch_missing: { tone: "warn", actions: ["back_to_repo", "retry"] },
  offline: { tone: "info", actions: ["retry", "back_to_repo"] },
  timeout: { tone: "info", actions: ["retry", "back_to_repo"] },
  rate_limited: { tone: "info", actions: ["retry"] },
  tls_error: { tone: "err", actions: ["back_to_repo", "retry"] },
  tls_untrusted_ca: { tone: "warn", actions: ["review_certificate", "retry"] },
  tls_pin_mismatch: { tone: "err", actions: ["review_certificate"] },
  token_expired: { tone: "err", actions: ["back_to_access", "retry"] },
  token_insufficient_scope: {
    tone: "err",
    actions: ["back_to_access", "retry"],
  },
  provider_unknown: { tone: "warn", actions: ["back_to_repo", "retry"] },
  host_key_unknown: { tone: "warn", actions: ["review_host_key"] },
  host_key_changed: { tone: "err", actions: ["review_host_key"] },
  ssh_unavailable: { tone: "err", actions: ["back_to_repo", "back_to_access"] },
  git_unavailable: { tone: "err", actions: ["retry"] },
  git_disabled: { tone: "err", actions: ["close"] },
  secrets_unavailable: { tone: "err", actions: ["retry"] },
  store_untrusted: { tone: "err", actions: ["retry"] },
  remote_exists: { tone: "info", actions: ["close"] },
  url_invalid: { tone: "err", actions: ["back_to_repo"] },
  url_scheme_forbidden: { tone: "err", actions: ["back_to_repo"] },
};

const FALLBACK: IssueCopy = { tone: "err", actions: ["retry", "back_to_repo"] };

export const issueCopyOf = (code: string): IssueCopy => COPY[code] ?? FALLBACK;

/** Коды, у которых в переводах есть свои заголовок и подсказка (gitRemote:issue.<код>). */
export const COPIED_ISSUE_CODES: readonly string[] = Object.keys(COPY);
