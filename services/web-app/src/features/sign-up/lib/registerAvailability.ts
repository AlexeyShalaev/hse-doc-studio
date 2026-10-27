import type { AuthOptions } from "@entities/session";

export type RegisterAvailability = "form" | "invite_required" | "closed";

/**
 * Что показывает /register: форму, просьбу прислать приглашение или «закрыто».
 * Без паролей (только SSO) своего аккаунта не создать, поэтому тоже «закрыто».
 */
export const registerAvailability = (
  auth: AuthOptions,
  hasInvitation: boolean,
): RegisterAvailability => {
  if (!auth.password_enabled) return "closed";
  if (hasInvitation) return "form";
  switch (auth.registration_mode) {
    case "open":
    case "domains":
      return "form";
    case "invite":
      return "invite_required";
    case "closed":
      return "closed";
  }
};
