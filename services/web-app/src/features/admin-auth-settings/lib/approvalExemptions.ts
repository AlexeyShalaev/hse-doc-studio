import type { RegistrationMode } from "@entities/session";

// Исключения из одобрения, как на сервере (core/identity/approval_exemptions.py):
// `hse.ru` ровно домен, `*.hse.ru` любой поддомен без самого hse.ru,
// `name@example.com` один адрес. Регулярных выражений нет намеренно.

export const MAX_EXEMPTIONS = 100;
const MAX_LENGTH = 254;
const WILDCARD = "*.";
const LABEL = /^(?!-)[\p{L}\p{N}\p{M}-]{1,63}(?<!-)$/u;
const LOCAL = /^[^\s@*]{1,64}$/u;

export type ExemptionIssue = "too_long" | "wildcard" | "domain" | "address";

export type ExemptionProblem = {
  /** Номер строки с единицы, пустые строки тоже считаются. */
  line: number;
  value: string;
  issue: ExemptionIssue;
};

export type ParsedExemptions = {
  rules: string[];
  problems: ExemptionProblem[];
  tooMany: boolean;
};

const norm = (value: string): string =>
  value.normalize("NFC").trim().toLowerCase();

const validDomain = (domain: string): boolean => {
  const labels = domain.split(".");
  return (
    domain.length <= MAX_LENGTH &&
    labels.length >= 2 &&
    labels.every((label) => LABEL.test(label))
  );
};

/** Правило или причина, по которой строка им не стала. */
export type ParsedExemption = { rule: string } | { issue: ExemptionIssue };

const domainRule = (value: string, prefix = ""): ParsedExemption => {
  const domain = norm(value).replace(/^@+/, "");
  if (domain.includes("*")) return { issue: "wildcard" };
  return validDomain(domain) ? { rule: prefix + domain } : { issue: "domain" };
};

export const parseExemption = (raw: string): ParsedExemption => {
  const value = raw.trim();
  if (value.length > MAX_LENGTH) return { issue: "too_long" };
  // `@hse.ru` читается как домен, как и в списке разрешённых доменов.
  if (value.replace(/^@+/, "").includes("@")) {
    const address = norm(value);
    if (address.includes("*")) return { issue: "wildcard" };
    const at = address.lastIndexOf("@");
    const valid =
      LOCAL.test(address.slice(0, at)) && validDomain(address.slice(at + 1));
    return valid ? { rule: address } : { issue: "address" };
  }
  if (value.startsWith(WILDCARD)) {
    return domainRule(value.slice(WILDCARD.length), WILDCARD);
  }
  return domainRule(value);
};

/** Строки поля: по одной на правило, пустые пропускаются, повторы схлопываются. */
export const parseExemptions = (text: string): ParsedExemptions => {
  const seen = new Set<string>();
  const problems: ExemptionProblem[] = [];
  text.split(/\r?\n/).forEach((raw, index) => {
    if (raw.trim() === "") return;
    const parsed = parseExemption(raw);
    if ("issue" in parsed) {
      problems.push({
        line: index + 1,
        value: raw.trim(),
        issue: parsed.issue,
      });
    } else {
      seen.add(parsed.rule);
    }
  });
  return {
    rules: [...seen],
    problems,
    tooMany: seen.size > MAX_EXEMPTIONS,
  };
};

export const ruleMatches = (rule: string, email: string): boolean => {
  const address = norm(email);
  if (rule.includes("@")) return address === rule;
  const domain = address.slice(address.lastIndexOf("@") + 1);
  // Хвост с точкой: `*.hse.ru` не совпадает ни с `hse.ru`, ни с `nothse.ru`.
  if (rule.startsWith(WILDCARD)) return domain.endsWith(rule.slice(1));
  return domain === rule;
};

export const matchingExemption = (
  email: string,
  rules: readonly string[],
): string | null => rules.find((rule) => ruleMatches(rule, email)) ?? null;

export type ApprovalCheck =
  | { kind: "invalid" }
  | { kind: "inviteOnly" }
  | { kind: "domain" }
  | { kind: "noApproval" }
  | { kind: "approval" }
  | { kind: "exempt"; rule: string }
  | { kind: "exemptNoSmtp"; rule: string };

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/u;

/**
 * Что будет с самостоятельной регистрацией адреса при настройках формы
 * (ещё не сохранённых). Приглашения и внешний вход сюда не входят.
 */
export const checkAddress = (
  email: string,
  options: {
    mode: RegistrationMode;
    domains: readonly string[];
    approval: boolean;
    rules: readonly string[];
    smtpEnabled: boolean;
  },
): ApprovalCheck => {
  const address = norm(email);
  if (!EMAIL.test(address)) return { kind: "invalid" };
  if (options.mode === "closed" || options.mode === "invite") {
    return { kind: "inviteOnly" };
  }
  const domain = address.slice(address.lastIndexOf("@") + 1);
  if (options.mode === "domains" && !options.domains.includes(domain)) {
    return { kind: "domain" };
  }
  if (!options.approval) {
    if (options.smtpEnabled) return { kind: "noApproval" };
    // Без почты открытая регистрация ждёт приглашения, по доменам ждёт одобрения.
    return options.mode === "open"
      ? { kind: "inviteOnly" }
      : { kind: "approval" };
  }
  const rule = matchingExemption(address, options.rules);
  if (rule === null) return { kind: "approval" };
  return options.smtpEnabled
    ? { kind: "exempt", rule }
    : { kind: "exemptNoSmtp", rule };
};
