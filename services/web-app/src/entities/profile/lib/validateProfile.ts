// Проверка профиля автора на клиенте. Правила те же, что у сервера (core/vcs/author),
// и сверяются общими векторами contracts/git-sync/profile_cases.json: форма
// подсказывает ошибку до запроса, а сервер всё равно проверяет заново.

export const PROFILE_NAME_MAX = 128;
export const PROFILE_EMAIL_MAX = 254;

export type ProfileField = "name" | "email";

export const PROFILE_ISSUE_CODES = [
  "name_required",
  "name_too_long",
  "name_invalid",
  "email_required",
  "email_too_long",
  "email_invalid",
] as const;

export type ProfileIssueCode = (typeof PROFILE_ISSUE_CODES)[number];

const ISSUE_CODE_SET: ReadonlySet<string> = new Set(PROFILE_ISSUE_CODES);

export const isProfileIssueCode = (code: string): code is ProfileIssueCode =>
  ISSUE_CODE_SET.has(code);

// git обрезает эти символы по краям имени и отказывается от имени, где ничего больше нет.
const GIT_CRUD = new Set(Array.from(" \t.,:;<>\"'\\"));
const EMAIL_SHAPE = /^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$/;

const hasControl = (value: string): boolean => {
  for (const ch of value) {
    const code = ch.codePointAt(0) ?? 0;
    if (code < 0x20 || code === 0x7f) return true;
  }
  return false;
};

// Длина в символах, а не в единицах UTF-16: так считает и сервер.
const lengthOf = (value: string): number => Array.from(value).length;

export const normalizeName = (raw: string): string =>
  raw.normalize("NFC").replace(/\s+/g, " ").trim();

export const normalizeEmail = (raw: string): string => {
  const email = raw.trim();
  const at = email.indexOf("@");
  if (at < 0 || email.includes("@", at + 1)) return email;
  return `${email.slice(0, at + 1)}${email.slice(at + 1).toLowerCase()}`;
};

export const validateName = (raw: string): ProfileIssueCode | null => {
  const name = normalizeName(raw);
  if (name === "") return "name_required";
  if (lengthOf(name) > PROFILE_NAME_MAX) return "name_too_long";
  if (/[<>]/.test(name) || hasControl(name)) return "name_invalid";
  if (Array.from(name).every((ch) => GIT_CRUD.has(ch))) return "name_invalid";
  return null;
};

export const validateEmail = (raw: string): ProfileIssueCode | null => {
  const email = normalizeEmail(raw);
  if (email === "") return "email_required";
  if (lengthOf(email) > PROFILE_EMAIL_MAX) return "email_too_long";
  if (hasControl(email) || !EMAIL_SHAPE.test(email)) return "email_invalid";
  return null;
};

export type ProfileIssues = Partial<Record<ProfileField, ProfileIssueCode>>;

export type ProfileCheck = {
  name: string;
  email: string;
  issues: ProfileIssues;
  isValid: boolean;
};

export const validateProfile = (raw: {
  name: string;
  email: string;
}): ProfileCheck => {
  const issues: ProfileIssues = {};
  const nameIssue = validateName(raw.name);
  const emailIssue = validateEmail(raw.email);
  if (nameIssue) issues.name = nameIssue;
  if (emailIssue) issues.email = emailIssue;
  return {
    name: normalizeName(raw.name),
    email: normalizeEmail(raw.email),
    issues,
    isValid: !nameIssue && !emailIssue,
  };
};

// Так подписывается версия: «Имя <почта>». Пустые части не придумываем.
export const formatCommitAuthor = (name: string, email: string): string => {
  const n = name.trim();
  const e = email.trim();
  if (n && e) return `${n} <${e}>`;
  return n || (e ? `<${e}>` : "");
};
