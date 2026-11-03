// Подтверждение личности новым входом через провайдера: новая сессия сразу считается свежей,
// после возврата человек снова на странице аккаунта.
export const REAUTH_NEXT = "/settings/account#account-passkeys";

export const ssoReauthUrl = (providerId: string): string =>
  `/api/v1/auth/oidc/${encodeURIComponent(providerId)}/start?next=${encodeURIComponent(REAUTH_NEXT)}`;
