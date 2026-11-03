import { adminClient, parseResp } from "@shared/api";
import type { ListPage, ListRequestParams } from "@shared/lib";
import {
  AdminAuthSettingsSchema,
  AdminOidcProviderPageSchema,
  AdminOidcProviderSchema,
  AdminRegistrationSettingsSchema,
  AdminMailPreviewSchema,
  AdminSmtpSettingsSchema,
  AdminSmtpTestResultSchema,
  type AdminAuthSettings,
  type UpdateAdminAuthRequest,
  type AdminOidcProvider,
  type AdminRegistrationSettings,
  type AdminMailPreview,
  type AdminSmtpSettings,
  type AdminSmtpTestResult,
  type CreateAdminOidcProviderRequest,
  type UpdateAdminOidcProviderRequest,
  type UpdateAdminRegistrationRequest,
  type UpdateAdminSmtpRequest,
} from "@entities/session";

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
  updateAuth: (patch: UpdateAdminAuthRequest): Promise<AdminAuthSettings> =>
    adminClient
      .put("/settings/auth", patch, quiet)
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

  mailPreview: (
    template: string | null,
    lang: string,
  ): Promise<AdminMailPreview> =>
    adminClient
      .get("/settings/smtp/preview", {
        ...quiet,
        params: { ...(template ? { template } : {}), lang },
      })
      .then(parseResp(AdminMailPreviewSchema)),

  providers: (
    params: ListRequestParams,
    signal: AbortSignal,
  ): Promise<ListPage<AdminOidcProvider>> =>
    adminClient
      .get("/oidc-providers", { ...quiet, signal, params })
      .then(parseResp(AdminOidcProviderPageSchema)),
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
