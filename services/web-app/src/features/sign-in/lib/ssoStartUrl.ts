// Внешний вход: полная навигация, провайдер вернёт на /auth/error при отказе.
export const ssoStartUrl = (providerId: string, next: string): string =>
  `/api/v1/auth/oidc/${encodeURIComponent(providerId)}/start?next=${encodeURIComponent(next)}`;
