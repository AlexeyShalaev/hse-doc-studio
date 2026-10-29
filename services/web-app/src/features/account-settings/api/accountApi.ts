import { z } from "zod";
import { ApiError, apiClient, parseResp } from "@shared/api";
import {
  AccountIdentitySchema,
  AccountProfileSchema,
  AccountSessionSchema,
  ApiTokenSchema,
  ChangeEmailResponseSchema,
  CreateApiTokenResponseSchema,
  LinkIdentityResponseSchema,
  type AccountIdentity,
  type AccountProfile,
  type AccountSession,
  type ApiToken,
  type ChangeEmailResponse,
  type CreateApiTokenRequest,
  type CreateApiTokenResponse,
  type LinkIdentityResponse,
} from "@entities/session";

// Ошибки формы показывает сама форма: тост не нужен.
const quiet = { silentError: true } as const;

export type AccountPatch = {
  name?: string;
  commit_name?: string;
  commit_email?: string;
  commit_use_account_email?: boolean;
};

export type AccountIssue = { field: string; message: string };

/** 422 на PATCH /account: список полей с сообщением сервера на языке человека. */
export class AccountValidationFailed extends Error {
  readonly issues: AccountIssue[];

  constructor(issues: AccountIssue[]) {
    super("account validation failed");
    this.name = "AccountValidationFailed";
    this.issues = issues;
  }
}

const IssueListSchema = z.array(
  z.object({
    loc: z.array(z.union([z.string(), z.number()])),
    msg: z.string(),
  }),
);

const toValidationFailure = (error: unknown): unknown => {
  if (error instanceof ApiError && error.status === 422) {
    const parsed = IssueListSchema.safeParse(error.data);
    if (parsed.success) {
      return new AccountValidationFailed(
        parsed.data.map((issue) => ({
          field: String(issue.loc[issue.loc.length - 1] ?? ""),
          message: issue.msg,
        })),
      );
    }
  }
  return error;
};

export const accountApi = {
  get: (): Promise<AccountProfile> =>
    apiClient.get("/account").then(parseResp(AccountProfileSchema)),

  update: (patch: AccountPatch): Promise<AccountProfile> =>
    apiClient
      .patch("/account", patch, quiet)
      .then(parseResp(AccountProfileSchema))
      .catch((error: unknown) => {
        throw toValidationFailure(error);
      }),

  changePassword: async (params: {
    current_password: string;
    new_password: string;
    sign_out_other_sessions: boolean;
  }): Promise<void> => {
    await apiClient.post("/account/password", params, quiet);
  },

  changeEmail: (params: {
    email: string;
    password: string;
  }): Promise<ChangeEmailResponse> =>
    apiClient
      .post("/account/email", params, quiet)
      .then(parseResp(ChangeEmailResponseSchema)),

  sessions: (): Promise<AccountSession[]> =>
    apiClient
      .get("/account/sessions")
      .then(parseResp(z.array(AccountSessionSchema))),

  revokeSession: async (id: string): Promise<void> => {
    await apiClient.delete(
      `/account/sessions/${encodeURIComponent(id)}`,
      quiet,
    );
  },

  revokeOtherSessions: async (): Promise<void> => {
    await apiClient.delete("/account/sessions", quiet);
  },

  tokens: (): Promise<ApiToken[]> =>
    apiClient.get("/account/tokens").then(parseResp(z.array(ApiTokenSchema))),

  createToken: (body: CreateApiTokenRequest): Promise<CreateApiTokenResponse> =>
    apiClient
      .post("/account/tokens", body, quiet)
      .then(parseResp(CreateApiTokenResponseSchema)),

  revokeToken: async (id: string): Promise<void> => {
    await apiClient.delete(`/account/tokens/${encodeURIComponent(id)}`, quiet);
  },

  identities: (): Promise<AccountIdentity[]> =>
    apiClient
      .get("/account/identities")
      .then(parseResp(z.array(AccountIdentitySchema))),

  unlinkIdentity: async (id: string): Promise<void> => {
    await apiClient.delete(
      `/account/identities/${encodeURIComponent(id)}`,
      quiet,
    );
  },

  startLink: (providerId: string): Promise<LinkIdentityResponse> =>
    apiClient
      .post(
        "/account/identities/link/start",
        { provider_id: providerId },
        quiet,
      )
      .then(parseResp(LinkIdentityResponseSchema)),
};
