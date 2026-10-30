import type { AccountIdentity } from "@entities/session";

/** Строка карточки «Способы входа»: пароль или привязанный внешний провайдер. */
export type IdentityRow = {
  id: string;
  kind: "password" | "oidc";
  provider_id: string | null;
  provider_label: string;
  email: string | null;
  email_verified: boolean | null;
  can_unlink: boolean;
};

export const PASSWORD_ROW_ID = "idn_password";

/**
 * Список способов входа из ответа сервера. Сервер отдаёт только привязанные внешние входы;
 * пароль добавляется, когда он включён на установке. Отвязать вход можно, пока остаётся другой
 * способ, окончательно это решает сервер (409 last_login_method).
 */
export const identityRows = (
  linked: AccountIdentity[],
  passwordEnabled: boolean,
  accountEmail: string | null,
): IdentityRow[] => {
  const canUnlink = passwordEnabled || linked.length > 1;
  const rows: IdentityRow[] = [];
  if (passwordEnabled) {
    rows.push({
      id: PASSWORD_ROW_ID,
      kind: "password",
      provider_id: null,
      provider_label: "",
      email: accountEmail,
      email_verified: null,
      can_unlink: false,
    });
  }
  for (const item of linked) {
    rows.push({
      id: `idn_${item.provider}`,
      kind: "oidc",
      provider_id: item.provider,
      provider_label: item.label ?? item.provider,
      email: item.email,
      email_verified: item.email_verified,
      can_unlink: canUnlink,
    });
  }
  return rows;
};
