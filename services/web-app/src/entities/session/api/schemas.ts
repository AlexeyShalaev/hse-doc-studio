import { z } from "zod";

// Зеркало services/api/hse_doc_studio/api/schemas/session.py. Эталоны лежат в contracts/server;
// strictObject повторяет extra=forbid на стороне бэкенда: лишнее поле значит расхождение сторон.

const iso = z.string().min(1);

export const STUDIO_MODES = ["local", "server"] as const;
export const StudioModeSchema = z.enum(STUDIO_MODES);
export type StudioModeName = z.infer<typeof StudioModeSchema>;

export const SetupStateSchema = z.enum(["needs_admin", "ready"]);
export const RegistrationModeSchema = z.enum([
  "open",
  "domains",
  "invite",
  "closed",
]);
export type RegistrationMode = z.infer<typeof RegistrationModeSchema>;
export const OrgRoleNameSchema = z.enum(["owner", "admin", "member"]);
export const AccountStatusSchema = z.enum([
  "active",
  "pending_verification",
  "pending_approval",
  "disabled",
]);
export const TokenScopeSchema = z.enum(["api", "git:read", "git:write"]);
export const ProjectRoleSchema = z.enum([
  "reader",
  "reviewer",
  "editor",
  "owner",
]);
export type ProjectRole = z.infer<typeof ProjectRoleSchema>;
const LocaleSchema = z.enum(["ru", "en"]);

export const CapabilitiesSchema = z.strictObject({
  fs_browse: z.boolean(),
  connect_folder: z.boolean(),
  open_in_editor: z.boolean(),
  move_project: z.boolean(),
  docker_ui: z.boolean(),
  self_update: z.boolean(),
  local_services_ui: z.boolean(),
  admin: z.boolean(),
  personal_signing_keys: z.boolean(),
});
export type Capabilities = z.infer<typeof CapabilitiesSchema>;

export const AuthOptionsSchema = z.strictObject({
  registration_mode: RegistrationModeSchema,
  password_enabled: z.boolean(),
  oidc_providers: z.array(
    z.strictObject({ id: z.string(), label: z.string() }),
  ),
  smtp_enabled: z.boolean(),
  password_min_length: z.number().int(),
});
export type AuthOptions = z.infer<typeof AuthOptionsSchema>;

export const SessionUserSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  email: z.string(),
  avatar_initials: z.string(),
  is_instance_admin: z.boolean(),
  email_verified: z.boolean(),
  locale: LocaleSchema.nullable(),
  org_roles: z.array(
    z.strictObject({
      slug: z.string(),
      name: z.string(),
      role: OrgRoleNameSchema,
    }),
  ),
});
export type SessionUser = z.infer<typeof SessionUserSchema>;

export const BootstrapSchema = z.strictObject({
  mode: StudioModeSchema,
  version: z.string(),
  setup_state: SetupStateSchema,
  auth: AuthOptionsSchema,
  user: SessionUserSchema.nullable(),
  capabilities: CapabilitiesSchema,
  csrf_token: z.string().nullable(),
});
export type Bootstrap = z.infer<typeof BootstrapSchema>;

export const AuthErrorBodySchema = z.strictObject({
  detail: z.string(),
  code: z.string(),
});

export const LoginRequestSchema = z.strictObject({
  email: z.string(),
  password: z.string(),
});
export const LoginResponseSchema = z.strictObject({
  user: SessionUserSchema,
  csrf_token: z.string(),
});
export type LoginResponse = z.infer<typeof LoginResponseSchema>;
export const RegisterRequestSchema = z.strictObject({
  email: z.string(),
  name: z.string(),
  password: z.string(),
  invitation_token: z.string().nullable(),
});
export const VerifyEmailRequestSchema = z.strictObject({ token: z.string() });
export const RegisterResponseSchema = z.strictObject({
  status: z.enum(["check_email", "pending_approval"]),
  link: z.string().nullable(),
});
export const InvitationInfoSchema = z.strictObject({
  email: z.string(),
  invited_by: z.string(),
  org_name: z.string().nullable(),
});
export type InvitationInfo = z.infer<typeof InvitationInfoSchema>;
export const ResendVerificationRequestSchema = z.strictObject({
  email: z.string(),
});
export const ForgotRequestSchema = z.strictObject({ email: z.string() });
export type RegisterResponse = z.infer<typeof RegisterResponseSchema>;
export const ForgotResponseSchema = z.strictObject({
  status: z.literal("check_email"),
  link: z.string().nullable(),
});
export type ForgotResponse = z.infer<typeof ForgotResponseSchema>;
export const ResetRequestSchema = z.strictObject({
  token: z.string(),
  password: z.string(),
});

export const ServerSetupStatusSchema = z.strictObject({
  state: SetupStateSchema,
  token_required: z.boolean(),
  steps_done: z.array(z.enum(["admin", "settings"])),
});
export const ServerSetupAdminRequestSchema = z.strictObject({
  setup_token: z.string().nullable(),
  name: z.string(),
  email: z.string(),
  password: z.string(),
});
export const ServerSetupSettingsRequestSchema = z
  .strictObject({
    registration_mode: RegistrationModeSchema,
    // Домены почты для режима domains (для него нужен хотя бы один).
    registration_domains: z.array(z.string()),
    require_approval: z.boolean(),
    password_enabled: z.boolean(),
  })
  .refine(
    (value) =>
      value.registration_mode !== "domains" ||
      value.registration_domains.some((d) => d.trim().replace(/^@/, "") !== ""),
    { path: ["registration_domains"] },
  );
export const ServerSetupCheckSchema = z.strictObject({
  id: z.enum(["database", "storage", "runner"]),
  status: z.enum(["ok", "fail", "not_configured"]),
  reason: z.string().nullable(),
});
export const ServerSetupEnvironmentSchema = z.strictObject({
  checks: z.array(ServerSetupCheckSchema),
});
export type ServerSetupEnvironment = z.infer<
  typeof ServerSetupEnvironmentSchema
>;

export const UpdateAccountRequestSchema = z.strictObject({
  name: z.string().nullish(),
  locale: LocaleSchema.nullish(),
});
export const ChangePasswordRequestSchema = z.strictObject({
  current_password: z.string(),
  new_password: z.string(),
  sign_out_other_sessions: z.boolean(),
});
export const AccountSessionSchema = z.strictObject({
  id: z.string(),
  created_at: iso,
  last_seen_at: iso,
  ip: z.string().nullable(),
  user_agent: z.string(),
  current: z.boolean(),
});
export const ApiTokenSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  prefix: z.string(),
  scopes: z.array(TokenScopeSchema),
  created_at: iso,
  expires_at: iso.nullable(),
  last_used_at: iso.nullable(),
});
export const CreateApiTokenRequestSchema = z.strictObject({
  name: z.string(),
  scopes: z.array(TokenScopeSchema),
  expires_in_days: z.number().int().nullable(),
});
export const CreateApiTokenResponseSchema = z.strictObject({
  token: z.string(),
  item: ApiTokenSchema,
});

export const ProjectSummarySchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  kind: z.enum(["research", "project"]),
  staffing: z.enum(["solo", "team"]),
  lang: LocaleSchema,
  owner: z.strictObject({
    kind: z.enum(["user", "org"]),
    id: z.string(),
    name: z.string(),
    slug: z.string().nullable(),
  }),
  my_role: ProjectRoleSchema,
  updated_at: iso,
  pinned: z.boolean(),
  archived: z.boolean(),
  shared_enabled: z.boolean(),
});
export type ProjectSummary = z.infer<typeof ProjectSummarySchema>;

export const CreateServerProjectRequestSchema = z.strictObject({
  name: z.string(),
  pack_id: z.string(),
  template_id: z.string(),
  version: z.string(),
  engine: z.enum(["xelatex", "pdflatex", "lualatex"]),
  kind: z.enum(["research", "project"]),
  staffing: z.enum(["solo", "team"]),
  lang: LocaleSchema,
  owner_org_slug: z.string().nullable(),
  shared_enabled: z.boolean(),
});

export const AdminUserSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  email: z.string(),
  status: AccountStatusSchema,
  is_instance_admin: z.boolean(),
  created_at: iso,
  last_login_at: iso.nullable(),
  project_count: z.number().int(),
});
export const AdminOrgSchema = z.strictObject({
  slug: z.string(),
  name: z.string(),
  member_count: z.number().int(),
  project_count: z.number().int(),
});
export const AdminRunnerSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  status: z.enum(["online", "offline", "draining"]),
  tags: z.array(z.string()),
  version: z.string(),
  last_seen_at: iso.nullable(),
  running_jobs: z.number().int(),
});
export const AdminSettingsSchema = z.strictObject({
  registration_mode: RegistrationModeSchema,
  require_approval: z.boolean(),
  password_enabled: z.boolean(),
  allowed_domains: z.array(z.string()),
  smtp_enabled: z.boolean(),
  public_url: z.string(),
});
