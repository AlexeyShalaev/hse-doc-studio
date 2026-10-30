import { z } from "zod";
import { adminClient, parseResp } from "@shared/api";
import {
  AdminAiProviderSchema,
  AdminBuildSettingsSchema,
  AdminInstanceSettingsSchema,
  AdminSigningPolicySchema,
  type AdminBuildSettings,
  type AdminInstanceSettings,
  type AdminSigningPolicy,
  type SigningServerKeys,
  type UpdateAdminBuildRequest,
  type UpdateAdminInstanceRequest,
} from "@entities/session";

// Ошибки форм показывают сами карточки: тост не нужен.
const quiet = { silentError: true } as const;

export const installApi = {
  instance: (): Promise<AdminInstanceSettings> =>
    adminClient
      .get("/settings/instance", quiet)
      .then(parseResp(AdminInstanceSettingsSchema)),
  updateInstance: (
    body: UpdateAdminInstanceRequest,
  ): Promise<AdminInstanceSettings> =>
    adminClient
      .put("/settings/instance", body, quiet)
      .then(parseResp(AdminInstanceSettingsSchema)),

  build: (): Promise<AdminBuildSettings> =>
    adminClient
      .get("/settings/build", quiet)
      .then(parseResp(AdminBuildSettingsSchema)),
  updateBuild: (body: UpdateAdminBuildRequest): Promise<AdminBuildSettings> =>
    adminClient
      .put("/settings/build", body, quiet)
      .then(parseResp(AdminBuildSettingsSchema)),

  signing: (): Promise<AdminSigningPolicy> =>
    adminClient
      .get("/settings/signing", quiet)
      .then(parseResp(AdminSigningPolicySchema)),
  updateSigning: (serverKeys: SigningServerKeys): Promise<AdminSigningPolicy> =>
    adminClient
      .put("/settings/signing", { server_keys: serverKeys }, quiet)
      .then(parseResp(AdminSigningPolicySchema)),

  sharedProviders: () =>
    adminClient
      .get("/ai-providers", quiet)
      .then(parseResp(z.array(AdminAiProviderSchema))),
};
