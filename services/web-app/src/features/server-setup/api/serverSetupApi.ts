import { apiClient, parseResp } from "@shared/api";
import {
  LoginResponseSchema,
  ServerSetupEnvironmentSchema,
  ServerSetupSettingsSchema,
  ServerSetupStatusSchema,
  type LoginResponse,
  type RegistrationMode,
  type ServerSetupEnvironment,
  type ServerSetupSettings,
  type ServerSetupStatus,
} from "@entities/session";

export type SetupSettingsBody = {
  registration_mode: RegistrationMode;
  registration_domains: string[];
  require_approval: boolean;
  password_enabled: boolean;
};

// Отказы шагов экран показывает сам: тост не нужен.
const quiet = { silentError: true } as const;

/** Шаговые ручки мастера первого запуска: /api/v1/server-setup/*. */
export const serverSetupApi = {
  status: (): Promise<ServerSetupStatus> =>
    apiClient
      .get("/server-setup/status", quiet)
      .then(parseResp(ServerSetupStatusSchema)),

  createAdmin: (body: {
    setup_token: string | null;
    name: string;
    email: string;
    password: string;
  }): Promise<LoginResponse> =>
    apiClient
      .post("/server-setup/admin", body, quiet)
      .then(parseResp(LoginResponseSchema)),

  settings: (): Promise<ServerSetupSettings> =>
    apiClient
      .get("/server-setup/settings", quiet)
      .then(parseResp(ServerSetupSettingsSchema)),

  applySettings: (body: SetupSettingsBody): Promise<ServerSetupStatus> =>
    apiClient
      .post("/server-setup/settings", body, quiet)
      .then(parseResp(ServerSetupStatusSchema)),

  environment: (): Promise<ServerSetupEnvironment> =>
    apiClient
      .get("/server-setup/environment", quiet)
      .then(parseResp(ServerSetupEnvironmentSchema)),

  complete: (): Promise<ServerSetupStatus> =>
    apiClient
      .post("/server-setup/complete", undefined, quiet)
      .then(parseResp(ServerSetupStatusSchema)),
};
