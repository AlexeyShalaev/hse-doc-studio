import type { AccountProfile } from "@entities/session";
import type { AccountPatch } from "../api/accountApi";

// Откуда берётся адрес в коммитах. noreply: сгенерированный адрес, настоящий не
// уходит наружу. account: e-mail аккаунта. own: отдельный адрес для коммитов.
export type CommitMode = "noreply" | "account" | "own";

export const modeOf = (profile: AccountProfile): CommitMode =>
  profile.commit_email !== null
    ? "own"
    : profile.commit_use_account_email
      ? "account"
      : "noreply";

/**
 * Тело PATCH для выбранного режима. Пустая строка сбрасывает свой адрес или
 * имя к умолчанию, поэтому поля всегда отправляются явно.
 */
export const patchFor = (
  mode: CommitMode,
  commitName: string,
  ownEmail: string,
): AccountPatch => ({
  commit_name: commitName.trim(),
  commit_email: mode === "own" ? ownEmail.trim() : "",
  commit_use_account_email: mode === "account",
});

export const previewOf = (
  mode: CommitMode,
  profile: AccountProfile,
  commitName: string,
  ownEmail: string,
): string => {
  const name = commitName.trim() || profile.name;
  const email =
    mode === "own"
      ? ownEmail.trim() || "…"
      : mode === "account"
        ? profile.email
        : noreplyOf(profile);
  return `${name} <${email}>`;
};

/** Сгенерированный адрес приходит с сервера, пока свой адрес не включён. */
const noreplyOf = (profile: AccountProfile): string =>
  profile.commit_email_is_noreply
    ? profile.effective_commit_email
    : `${profile.id}@noreply.…`;

export const isDirty = (
  profile: AccountProfile,
  mode: CommitMode,
  commitName: string,
  ownEmail: string,
): boolean =>
  mode !== modeOf(profile) ||
  commitName.trim() !== (profile.commit_name ?? "") ||
  (mode === "own" && ownEmail.trim() !== (profile.commit_email ?? ""));
