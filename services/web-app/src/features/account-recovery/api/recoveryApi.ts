import { apiClient, parseResp } from "@shared/api";
import { ForgotResponseSchema, type ForgotResponse } from "@entities/session";

// Отказы показывают сами экраны: тост не нужен.
const quiet = { silentError: true } as const;

export const recoveryApi = {
  forgot: (email: string): Promise<ForgotResponse> =>
    apiClient
      .post("/auth/forgot", { email }, quiet)
      .then(parseResp(ForgotResponseSchema)),

  reset: async (token: string, password: string): Promise<void> => {
    await apiClient.post("/auth/reset", { token, password }, quiet);
  },

  verify: async (token: string): Promise<void> => {
    await apiClient.post("/auth/verify", { token }, quiet);
  },

  resendVerification: (email: string): Promise<ForgotResponse> =>
    apiClient
      .post("/auth/verify/resend", { email }, quiet)
      .then(parseResp(ForgotResponseSchema)),
};
