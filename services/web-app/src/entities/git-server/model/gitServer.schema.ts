import { z } from "zod";

// Сервер Студии как git-remote: служебные вызовы /git/-/*, вход устройства по коду
// (device flow), адрес клонирования проекта и вход локальной Студии на сервер.
// Зеркало api/schemas/git_remote.py; эталоны в contracts/server/fixtures (раздел 9.3
// спецификации). strictObject повторяет extra=forbid бэкенда.

const iso = z.string().min(1);

export const GIT_SCOPES = ["git:read", "git:write"] as const;
export const GitScopeSchema = z.enum(GIT_SCOPES);
export type GitScope = z.infer<typeof GitScopeSchema>;

export const DeviceClientKindSchema = z.enum(["desktop", "cli"]);
export type DeviceClientKind = z.infer<typeof DeviceClientKindSchema>;

const ProjectRoleSchema = z.enum(["reader", "reviewer", "editor", "owner"]);

export const GitServerInfoSchema = z.strictObject({
  server: z.literal("hse-doc-studio"),
  version: z.string(),
  device_flow: z.boolean(),
  api: z.string(),
});

export const GitWhoamiSchema = z.strictObject({
  user: z.strictObject({ id: z.string(), name: z.string(), email: z.string() }),
  scopes: z.array(GitScopeSchema),
  token: z.strictObject({
    id: z.string(),
    name: z.string(),
    expires_at: iso.nullable(),
  }),
});

export const GitProjectSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  owner_name: z.string(),
  role: ProjectRoleSchema,
  can_push: z.boolean(),
  clone_url: z.string(),
  updated_at: iso.nullable(),
});
export type GitProject = z.infer<typeof GitProjectSchema>;

export const GitProjectPageSchema = z.strictObject({
  items: z.array(GitProjectSchema),
  total: z.number().int(),
  limit: z.number().int(),
  offset: z.number().int(),
});
export type GitProjectPage = z.infer<typeof GitProjectPageSchema>;

export const DeviceCodeRequestSchema = z.strictObject({
  client_name: z.string(),
  client_kind: DeviceClientKindSchema,
  scopes: z.array(GitScopeSchema),
});
export const DeviceCodeResponseSchema = z.strictObject({
  device_code: z.string(),
  user_code: z.string(),
  verification_uri: z.string(),
  verification_uri_complete: z.string(),
  expires_in: z.number().int(),
  interval: z.number().int(),
});
export const DeviceTokenRequestSchema = z.strictObject({
  device_code: z.string(),
});
export const DeviceTokenResponseSchema = z.strictObject({
  access_token: z.string(),
  token_type: z.literal("bearer"),
  expires_in: z.number().int(),
  scope: z.string(),
});
export const DeviceTokenErrorSchema = z.strictObject({
  error: z.enum([
    "authorization_pending",
    "slow_down",
    "access_denied",
    "expired_token",
  ]),
});

export const DEVICE_STATUSES = [
  "pending",
  "approved",
  "denied",
  "expired",
  "delivered",
] as const;
export const DeviceStatusSchema = z.enum(DEVICE_STATUSES);
export type DeviceStatus = z.infer<typeof DeviceStatusSchema>;

export const DeviceAuthorizationInfoSchema = z.strictObject({
  user_code: z.string(),
  client_name: z.string(),
  client_kind: DeviceClientKindSchema,
  requested_scopes: z.array(GitScopeSchema),
  granted_scopes: z.array(GitScopeSchema).nullable(),
  client_ip: z.string().nullable(),
  requested_at: iso,
  expires_at: iso,
  status: DeviceStatusSchema,
});
export type DeviceAuthorizationInfo = z.infer<
  typeof DeviceAuthorizationInfoSchema
>;

export const DeviceDecisionRequestSchema = z.strictObject({
  decision: z.enum(["approve", "deny"]),
  scopes: z.array(GitScopeSchema),
});
export type DeviceDecisionRequest = z.infer<typeof DeviceDecisionRequestSchema>;

export const ProjectGitRemoteSchema = z.strictObject({
  enabled: z.boolean(),
  clone_url: z.string().nullable(),
  can_push: z.boolean(),
  branch: z.string().nullable(),
});
export type ProjectGitRemote = z.infer<typeof ProjectGitRemoteSchema>;

export const GitServerLoginRequestSchema = z.strictObject({
  server_url: z.string(),
  client_name: z.string(),
});
export type GitServerLoginRequest = z.infer<typeof GitServerLoginRequestSchema>;

export const GIT_SERVER_LOGIN_STATES = [
  "pending",
  "approved",
  "denied",
  "expired",
  "error",
] as const;
export const GitServerLoginSchema = z.strictObject({
  login_id: z.string(),
  server_url: z.string(),
  state: z.enum(GIT_SERVER_LOGIN_STATES),
  user_code: z.string().nullable(),
  verification_uri_complete: z.string().nullable(),
  expires_at: iso.nullable(),
  credential_id: z.string().nullable(),
  code: z.string().nullable(),
});
export type GitServerLogin = z.infer<typeof GitServerLoginSchema>;

export const GIT_SERVER_STATES = [
  "ok",
  "expired",
  "revoked",
  "unreachable",
] as const;
export type GitServerState = (typeof GIT_SERVER_STATES)[number];
export const GitServerItemSchema = z.strictObject({
  credential_id: z.string(),
  server_url: z.string(),
  host: z.string(),
  account_name: z.string().nullable(),
  scopes: z.array(GitScopeSchema),
  expires_at: iso.nullable(),
  state: z.enum(GIT_SERVER_STATES),
});
export type GitServerItem = z.infer<typeof GitServerItemSchema>;
export const GitServerListSchema = z.strictObject({
  items: z.array(GitServerItemSchema),
});
export type GitServerList = z.infer<typeof GitServerListSchema>;
