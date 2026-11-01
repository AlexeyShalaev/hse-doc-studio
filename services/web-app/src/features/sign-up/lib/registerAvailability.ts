import type { AuthOptions } from "@entities/session";

export type RegisterAvailability =
  "form" | "invite_required" | "smtp_required" | "closed";

/**
 * Что показывает /register: форму, просьбу прислать приглашение или «закрыто».
 * Без паролей (только SSO) своего аккаунта не создать, поэтому тоже «закрыто».
 * В открытом режиме без SMTP почту некому подтвердить: форма недоступна, нужно приглашение.
 * В режиме по доменам без SMTP форма остаётся: аккаунт просто ждёт одобрения админа.
 */
export const registerAvailability = (
  auth: AuthOptions,
  hasInvitation: boolean,
): RegisterAvailability => {
  if (!auth.password_enabled) return "closed";
  if (hasInvitation) return "form";
  switch (auth.registration_mode) {
    case "open":
      return auth.smtp_enabled ? "form" : "smtp_required";
    case "domains":
      return "form";
    case "invite":
      return "invite_required";
    case "closed":
      return "closed";
  }
};
