import { z } from "zod";
import { adminClient, listPageOf, parseResp } from "@shared/api";
import type { ListPage, ListRequestParams } from "@shared/lib";
import {
  AdminAuthSettingsSchema,
  AdminOidcProviderSchema,
  AdminRegistrationSettingsSchema,
  AdminSmtpSettingsSchema,
  AdminSmtpTestResultSchema,
  type AdminAuthSettings,
  type AdminOidcProvider,
  type AdminRegistrationSettings,
  type AdminSmtpSettings,
  type AdminSmtpTestResult,
  type CreateAdminOidcProviderRequest,
  type UpdateAdminOidcProviderRequest,
  type UpdateAdminRegistrationRequest,
  type UpdateAdminSmtpRequest,
} from "@entities/session";

// Провайдеры входа приходят страницей (единый контракт списков). Сервер до
// перехода на контракт отдавал весь список массивом: он читается как одна страница.
const OidcPageSchema = z.union([
  listPageOf(AdminOidcProviderSchema),
  z.array(AdminOidcProviderSchema).transform((items) => ({
    items,
    total: items.length,
    limit: items.length,
    offset: 0,
  })),
]);

// Ошибки форм показывают сами карточки: тост не нужен.
const quiet = { silentError: true } as const;

export const adminSettingsApi = {
  registration: (): Promise<AdminRegistrationSettings> =>
    adminClient
      .get("/settings/registration", quiet)
      .then(parseResp(AdminRegistrationSettingsSchema)),
  updateRegistration: (
    body: UpdateAdminRegistrationRequest,
  ): Promise<AdminRegistrationSettings> =>
    adminClient
      .put("/settings/registration", body, quiet)
      .then(parseResp(AdminRegistrationSettingsSchema)),

  auth: (): Promise<AdminAuthSettings> =>
    adminClient
      .get("/settings/auth", quiet)
      .then(parseResp(AdminAuthSettingsSchema)),
  updateAuth: (passwordEnabled: boolean): Promise<AdminAuthSettings> =>
    adminClient
      .put("/settings/auth", { password_enabled: passwordEnabled }, quiet)
      .then(parseResp(AdminAuthSettingsSchema)),

  smtp: (): Promise<AdminSmtpSettings> =>
    adminClient
      .get("/settings/smtp", quiet)
      .then(parseResp(AdminSmtpSettingsSchema)),
  updateSmtp: (body: UpdateAdminSmtpRequest): Promise<AdminSmtpSettings> =>
    adminClient
      .put("/settings/smtp", body, quiet)
      .then(parseResp(AdminSmtpSettingsSchema)),
  testSmtp: (to: string | null): Promise<AdminSmtpTestResult> =>
    adminClient
      .post("/settings/smtp/test", { to }, quiet)
      .then(parseResp(AdminSmtpTestResultSchema)),

  providers: (
    params: ListRequestParams,
    signal: AbortSignal,
  ): Promise<ListPage<AdminOidcProvider>> =>
    adminClient
      .get("/oidc-providers", { ...quiet, signal, params })
      .then(parseResp(OidcPageSchema)),
  createProvider: (
    body: CreateAdminOidcProviderRequest,
  ): Promise<AdminOidcProvider> =>
    adminClient
      .post("/oidc-providers", body, quiet)
      .then(parseResp(AdminOidcProviderSchema)),
  updateProvider: (
    id: string,
    body: UpdateAdminOidcProviderRequest,
  ): Promise<AdminOidcProvider> =>
    adminClient
      .patch(`/oidc-providers/${id}`, body, quiet)
      .then(parseResp(AdminOidcProviderSchema)),
  deleteProvider: async (id: string): Promise<void> => {
    await adminClient.delete(`/oidc-providers/${id}`, quiet);
  },
};
