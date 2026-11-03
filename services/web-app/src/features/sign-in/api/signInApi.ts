import { ApiError, apiClient, parseResp } from "@shared/api";
import {
  LoginResponseSchema,
  PasskeyOptionsSchema,
  type LoginResponse,
  type PasskeyOptions,
} from "@entities/session";
import { DEFAULT_RETRY_AFTER, type LoginFailure } from "../lib/loginErrors";

export const signInApi = {
  // Отказ входа форма показывает сама: тост не нужен.
  login: (email: string, password: string): Promise<LoginResponse> =>
    apiClient
      .post("/auth/login", { email, password }, { silentError: true })
      .then(parseResp(LoginResponseSchema)),

  passkeyOptions: (): Promise<PasskeyOptions> =>
    apiClient
      .post("/auth/passkey/options", {}, { silentError: true })
      .then(parseResp(PasskeyOptionsSchema)),

  passkeyLogin: (credential: Record<string, unknown>): Promise<LoginResponse> =>
    apiClient
      .post("/auth/passkey/login", { credential }, { silentError: true })
      .then(parseResp(LoginResponseSchema)),
};

export const toLoginFailure = (error: unknown): LoginFailure => {
  if (error instanceof ApiError) {
    if (error.status === 0) return { code: "network" };
    if (error.code === "rate_limited") {
      const raw = error.data?.retry_after;
      const retryAfter =
        typeof raw === "number" && raw > 0 ? raw : DEFAULT_RETRY_AFTER;
      return { code: "rate_limited", retryAfter };
    }
    return { code: error.code };
  }
  return { code: "unknown" };
};
