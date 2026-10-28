import { apiClient, parseResp } from "@shared/api";
import {
  InvitationInfoSchema,
  RegisterResponseSchema,
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

  invitation: (token: string): Promise<InvitationInfo> =>
    apiClient
      .get(`/auth/invitations/${encodeURIComponent(token)}`, {
        silentError: true,
      })
      .then(parseResp(InvitationInfoSchema)),
};
