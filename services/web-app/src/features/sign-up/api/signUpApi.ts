import { apiClient, parseResp } from "@shared/api";
import {
  InvitationInfoSchema,
  LoginResponseSchema,
  PasskeyOptionsSchema,
  RegisterResponseSchema,
  type LoginResponse,
  type PasskeyOptions,
  type PasskeySignupRequest,
  type InvitationInfo,
  type RegisterResponse,
} from "@entities/session";

// Отказы формы показывает сама форма, тост не нужен.
export const signUpApi = {
  register: (body: {
    email: string;
    name: string;
    password: string;
    invitation_token: string | null;
  }): Promise<RegisterResponse> =>
    apiClient
      .post("/auth/register", body, { silentError: true })
      .then(parseResp(RegisterResponseSchema)),

  /** Вызов для регистрации с passkey по приглашению на конкретный адрес. */
  passkeyOptions: (body: {
    invitation_token: string;
    name: string;
  }): Promise<PasskeyOptions> =>
    apiClient
      .post("/auth/register/passkey/options", body, { silentError: true })
      .then(parseResp(PasskeyOptionsSchema)),

  /** Аккаунт без пароля с первым ключом; ответ как у входа, сервер ставит cookie сессии. */
  passkeyRegister: (body: PasskeySignupRequest): Promise<LoginResponse> =>
    apiClient
      .post("/auth/register/passkey", body, { silentError: true })
      .then(parseResp(LoginResponseSchema)),

  invitation: (token: string): Promise<InvitationInfo> =>
    apiClient
      .get(`/auth/invitations/${encodeURIComponent(token)}`, {
        silentError: true,
      })
      .then(parseResp(InvitationInfoSchema)),
};
