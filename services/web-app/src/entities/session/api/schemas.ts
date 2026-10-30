import { z } from "zod";
import {
  PickerItemSchema,
  PickerPageSchema,
  cursorPageOf,
  listPageOf,
} from "@shared/api";

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
export type ServerSetupStatus = z.infer<typeof ServerSetupStatusSchema>;
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
export const SetupSettingKeySchema = z.enum([
  "registration_mode",
  "registration_domains",
  "require_approval",
  "password_enabled",
]);
export type SetupSettingKey = z.infer<typeof SetupSettingKeySchema>;
// Действующие настройки входа для шага мастера. Ключи из locked_by_env заданы
// окружением: экран показывает их только для чтения, запись их пропускает.
export const ServerSetupSettingsSchema = z.strictObject({
  registration_mode: RegistrationModeSchema,
  registration_domains: z.array(z.string()),
  require_approval: z.boolean(),
  password_enabled: z.boolean(),
  locked_by_env: z.array(SetupSettingKeySchema),
});
export type ServerSetupSettings = z.infer<typeof ServerSetupSettingsSchema>;
export const ServerSetupCheckSchema = z.strictObject({
  id: z.enum(["database", "storage", "runner"]),
  status: z.enum(["ok", "fail", "not_configured"]),
  reason: z.string().nullable(),
});
export const ServerSetupEnvironmentSchema = z.strictObject({
  checks: z.array(ServerSetupCheckSchema),
});
export type ServerSetupCheck = z.infer<typeof ServerSetupCheckSchema>;
export type ServerSetupEnvironment = z.infer<
  typeof ServerSetupEnvironmentSchema
>;

export const UpdateAccountRequestSchema = z.strictObject({
  name: z.string().nullish(),
  locale: LocaleSchema.nullish(),
  commit_name: z.string().nullish(),
  commit_email: z.string().nullish(),
  commit_use_account_email: z.boolean().nullish(),
});
export const AccountProfileSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  email: z.string(),
  locale: LocaleSchema.nullable(),
  commit_name: z.string().nullable(),
  commit_email: z.string().nullable(),
  commit_use_account_email: z.boolean(),
  effective_commit_name: z.string(),
  effective_commit_email: z.string(),
  commit_email_is_noreply: z.boolean(),
});
export type AccountProfile = z.infer<typeof AccountProfileSchema>;
export const ChangePasswordRequestSchema = z.strictObject({
  current_password: z.string(),
  new_password: z.string(),
  sign_out_other_sessions: z.boolean(),
});
export const ChangeEmailRequestSchema = z.strictObject({
  email: z.string(),
  password: z.string(),
});
export const ChangeEmailResponseSchema = z.strictObject({
  status: z.literal("check_email"),
  link: z.string().nullable(),
});
export type ChangeEmailResponse = z.infer<typeof ChangeEmailResponseSchema>;
export const AccountSessionSchema = z.strictObject({
  id: z.string(),
  created_at: iso,
  last_seen_at: iso,
  ip: z.string().nullable(),
  user_agent: z.string(),
  current: z.boolean(),
});
export const AccountIdentitySchema = z.strictObject({
  provider: z.string(),
  label: z.string().nullable(),
  email: z.string().nullable(),
  email_verified: z.boolean(),
});
export type AccountIdentity = z.infer<typeof AccountIdentitySchema>;
export type AccountSession = z.infer<typeof AccountSessionSchema>;
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

export type ApiToken = z.infer<typeof ApiTokenSchema>;
export type TokenScope = z.infer<typeof TokenScopeSchema>;
export type CreateApiTokenRequest = z.infer<typeof CreateApiTokenRequestSchema>;
export type CreateApiTokenResponse = z.infer<
  typeof CreateApiTokenResponseSchema
>;

// Страница списка сервера: {items, total, limit, offset} под теми же фильтрами.
export const pageOf = listPageOf;
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
// Серверный режим отдаёт список проектов страницей; локальный по-прежнему массивом.
export const ProjectSummaryPageSchema = pageOf(ProjectSummarySchema);
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

export const ProjectImportWarningSchema = z.strictObject({
  code: z.enum([
    "remote_needs_access",
    "records_skipped",
    "store_hardened",
    "junk_skipped",
    "chats_unreadable",
  ]),
  detail: z.string(),
});
export type ProjectImportWarning = z.infer<typeof ProjectImportWarningSchema>;

export const ProjectImportResultSchema = z.strictObject({
  project_id: z.string(),
  name: z.string(),
  id_regenerated: z.boolean(),
  files: z.number(),
  bytes: z.number(),
  chats: z.number(),
  warnings: z.array(ProjectImportWarningSchema),
});
export type ProjectImportResult = z.infer<typeof ProjectImportResultSchema>;

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
export const AdminUserPageSchema = pageOf(AdminUserSchema);
// Счётчики на чипах списка людей под тем же поиском (GET /api/admin/users/facets).
export const AdminUserFacetsSchema = z.strictObject({
  status: z.record(AccountStatusSchema, z.number().int()),
  admins: z.number().int(),
});
// Организация в карточке человека (GET /api/admin/users/{id}/orgs).
export const AdminUserOrgSchema = z.strictObject({
  slug: z.string(),
  name: z.string(),
  role: OrgRoleNameSchema,
  joined_at: iso,
});
export const AdminUserOrgPageSchema = pageOf(AdminUserOrgSchema);
// Пикер: первые подходящие; has_more значит «уточните поиск», пикер не листается.
export { PickerItemSchema };
export const PickerListSchema = PickerPageSchema;
export const UpdateAdminUserRequestSchema = z.strictObject({
  is_instance_admin: z.boolean(),
});
export const AdminResetLinkRequestSchema = z.strictObject({
  confirm: z.boolean(),
});
export const AdminResetLinkSchema = z.strictObject({
  link: z.string(),
  expires_at: iso,
  user_notified: z.boolean(),
});
export const AdminSessionsRevokedSchema = z.strictObject({
  revoked: z.number().int(),
});
export const AdminRetentionSettingsSchema = z.strictObject({
  audit_days: z.number().int(),
  deleted_projects_days: z.number().int(),
  unused_blobs_days: z.number().int(),
});
export const AdminInvitationSchema = z.strictObject({
  id: z.string(),
  email: z.string().nullable(),
  status: z.enum(["pending", "used", "expired"]),
  expires_at: iso,
  used_at: iso.nullable(),
});
export const AdminInvitationPageSchema = pageOf(AdminInvitationSchema);
// Кто действовал; у удалённого человека имя это псевдоним из журнала, почты нет.
export const AdminAuditActorSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  email: z.string().nullable(),
});
export const AdminAuditEventSchema = z.strictObject({
  id: z.number().int(),
  at: iso,
  action: z.string(),
  actor_id: z.string().nullable(),
  // Имя действовавшего и подпись цели сервер подставляет сам: справочник людей на клиенте не нужен.
  actor: AdminAuditActorSchema.nullable(),
  target: z.string().nullable(),
  target_label: z.string().nullable(),
  details: z.record(z.string(), z.unknown()),
});
// Курсор непрозрачный; total_estimate есть только без фильтров, иначе «из N» не показывается.
// Оценка числа записей; только без фильтров, иначе null.
export const AdminAuditPageSchema = cursorPageOf(AdminAuditEventSchema);
export const CreateAdminInvitationRequestSchema = z.strictObject({
  email: z.string().nullable(),
  ttl_days: z.number().int().nullable(),
});
export const AdminInvitationCreatedSchema = z.strictObject({
  invitation: AdminInvitationSchema,
  link: z.string().nullable(),
});
export const AdminOrgSchema = z.strictObject({
  slug: z.string(),
  name: z.string(),
  member_count: z.number().int(),
  project_count: z.number().int(),
  // Последнего владельца понизить или убрать нельзя (409 last_owner).
  owner_count: z.number().int(),
  my_role: OrgRoleNameSchema.nullable(),
});
export const AdminOrgPageSchema = pageOf(AdminOrgSchema);
export const OrgSchema = z.strictObject({
  slug: z.string(),
  name: z.string(),
  my_role: OrgRoleNameSchema,
  member_count: z.number().int(),
  group_count: z.number().int(),
  project_count: z.number().int(),
  created_at: iso,
});
export const CreateOrgRequestSchema = z.strictObject({
  slug: z.string(),
  name: z.string(),
  owner_email: z.string().nullable(),
});
export const UpdateOrgRequestSchema = z.strictObject({ name: z.string() });
export const OrgMemberSchema = z.strictObject({
  user_id: z.string(),
  name: z.string(),
  email: z.string(),
  role: OrgRoleNameSchema,
  joined_at: iso,
});
export const AddOrgMemberRequestSchema = z.strictObject({
  email: z.string(),
  role: OrgRoleNameSchema,
});
export const ChangeOrgMemberRoleRequestSchema = z.strictObject({
  role: OrgRoleNameSchema,
});
export const GroupSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  member_count: z.number().int(),
  created_at: iso,
});
export const CreateGroupRequestSchema = z.strictObject({ name: z.string() });
export const UpdateGroupRequestSchema = z.strictObject({ name: z.string() });
export const GroupMemberSchema = z.strictObject({
  user_id: z.string(),
  name: z.string(),
  email: z.string(),
  added_at: iso,
});
export const AddGroupMemberRequestSchema = z.strictObject({
  user_id: z.string(),
});
export const ProjectMemberRoleSchema = z.enum(["reader", "reviewer", "editor"]);
export const ProjectMemberSchema = z.strictObject({
  kind: z.enum(["user", "group"]),
  principal_id: z.string(),
  name: z.string(),
  role: ProjectMemberRoleSchema,
  persona: z.string().nullable(),
  can_share: z.boolean(),
  show_sources: z.boolean(),
  can_edit_all: z.boolean(),
});
export const SetProjectMemberRequestSchema = z.strictObject({
  role: ProjectMemberRoleSchema,
  persona: z.string().nullable(),
  can_share: z.boolean(),
  show_sources: z.boolean(),
  can_edit_all: z.boolean(),
});
export const AdminOrgMemberSchema = OrgMemberSchema;
export const AdminOrgMemberPageSchema = pageOf(AdminOrgMemberSchema);
// Счётчики ролей на чипах под тем же поиском (GET /api/admin/orgs/{slug}/members/facets).
export const AdminOrgMemberFacetsSchema = z.strictObject({
  role: z.record(OrgRoleNameSchema, z.number().int()),
});
// Человека выбирают пикером (user_id); почта остаётся запасным путём. Задаётся ровно одно из двух.
export const AddAdminOrgMemberRequestSchema = z
  .strictObject({
    user_id: z.string().nullable().optional(),
    email: z.string().nullable().optional(),
    role: OrgRoleNameSchema,
  })
  .refine((body) => (body.user_id == null) !== (body.email == null), {
    message: "user_id или email",
  });
export const UpdateAdminOrgMemberRequestSchema = z.strictObject({
  role: OrgRoleNameSchema,
});
export const CreateAdminOrgRequestSchema = z.strictObject({
  name: z.string(),
  slug: z.string(),
});
// Группа в админке: число участников и первые пять по имени; полный состав листается отдельно.
export const AdminGroupPreviewSchema = z.strictObject({
  user_id: z.string(),
  name: z.string(),
});
export const AdminGroupSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  member_count: z.number().int(),
  preview: z.array(AdminGroupPreviewSchema),
});
export const AdminGroupPageSchema = pageOf(AdminGroupSchema);
export const AdminGroupMemberSchema = GroupMemberSchema;
export const AdminGroupMemberPageSchema = pageOf(AdminGroupMemberSchema);
export const CreateAdminGroupRequestSchema = z.strictObject({
  name: z.string(),
  member_ids: z.array(z.string()),
});
export const UpdateAdminGroupRequestSchema = z.strictObject({
  name: z.string().nullable(),
  member_ids: z.array(z.string()).nullable(),
});
export type OrgRoleName = z.infer<typeof OrgRoleNameSchema>;
export type AccountStatus = z.infer<typeof AccountStatusSchema>;
export type AdminUser = z.infer<typeof AdminUserSchema>;
export type AdminUserPage = z.infer<typeof AdminUserPageSchema>;
export type AdminResetLink = z.infer<typeof AdminResetLinkSchema>;
export type AdminInvitation = z.infer<typeof AdminInvitationSchema>;
export type AdminInvitationPage = z.infer<typeof AdminInvitationPageSchema>;
export type AdminInvitationCreated = z.infer<
  typeof AdminInvitationCreatedSchema
>;
export type AdminAuditEvent = z.infer<typeof AdminAuditEventSchema>;
export type AdminAuditActor = z.infer<typeof AdminAuditActorSchema>;
export type AdminAuditPage = z.infer<typeof AdminAuditPageSchema>;
export type AdminOrg = z.infer<typeof AdminOrgSchema>;
export type AdminOrgMember = z.infer<typeof AdminOrgMemberSchema>;
export type AdminGroup = z.infer<typeof AdminGroupSchema>;
export type AdminOrgPage = z.infer<typeof AdminOrgPageSchema>;
export type AdminOrgMemberPage = z.infer<typeof AdminOrgMemberPageSchema>;
export type AdminOrgMemberFacets = z.infer<typeof AdminOrgMemberFacetsSchema>;
export type AdminGroupPage = z.infer<typeof AdminGroupPageSchema>;
export type AdminGroupMember = z.infer<typeof AdminGroupMemberSchema>;
export type AdminGroupMemberPage = z.infer<typeof AdminGroupMemberPageSchema>;
export type AdminUserFacets = z.infer<typeof AdminUserFacetsSchema>;
export type AdminUserOrg = z.infer<typeof AdminUserOrgSchema>;
export type AdminUserOrgPage = z.infer<typeof AdminUserOrgPageSchema>;
export type PickerItem = z.infer<typeof PickerItemSchema>;
export type PickerList = z.infer<typeof PickerListSchema>;
export type CreateAdminOrgRequest = z.infer<typeof CreateAdminOrgRequestSchema>;
export type CreateAdminGroupRequest = z.infer<
  typeof CreateAdminGroupRequestSchema
>;
export type UpdateAdminGroupRequest = z.infer<
  typeof UpdateAdminGroupRequestSchema
>;
export const MyOrgSchema = z.strictObject({
  slug: z.string(),
  name: z.string(),
  my_role: OrgRoleNameSchema,
  member_count: z.number().int(),
  groups: z.array(z.string()),
  sole_owner: z.boolean(),
});
export const ProjectAccessEntrySchema = z.strictObject({
  subject_kind: z.enum(["user", "group", "org"]),
  subject_id: z.string(),
  name: z.string(),
  detail: z.string().nullable(),
  role: ProjectRoleSchema,
  locked: z.boolean(),
});
// Панель «Доступ» страницей: владелец и организация-владелец всегда первыми.
export const ProjectAccessPageSchema = pageOf(ProjectAccessEntrySchema);
export const ProjectAccessCandidateSchema = z.strictObject({
  subject_kind: z.enum(["user", "group"]),
  subject_id: z.string(),
  name: z.string(),
  detail: z.string().nullable(),
});
// Пикер «Добавить»: до 20 подходящих; has_more значит «уточните поиск».
export const ProjectAccessCandidateListSchema = z.strictObject({
  items: z.array(ProjectAccessCandidateSchema),
  has_more: z.boolean(),
});
export type MyOrg = z.infer<typeof MyOrgSchema>;
export type ProjectAccessEntry = z.infer<typeof ProjectAccessEntrySchema>;
export type ProjectAccessCandidate = z.infer<
  typeof ProjectAccessCandidateSchema
>;
export const AdminSettingsSchema = z.strictObject({
  registration_mode: RegistrationModeSchema,
  require_approval: z.boolean(),
  password_enabled: z.boolean(),
  allowed_domains: z.array(z.string()),
  smtp_enabled: z.boolean(),
  public_url: z.string(),
});

const SettingStateSchema = z.strictObject({
  source: z.enum(["env", "admin", "default"]),
  locked: z.boolean(),
});
const settingFields = z.record(z.string(), SettingStateSchema);
const SmtpSecuritySchema = z.enum(["starttls", "tls", "none"]);
export const AdminRegistrationSettingsSchema = z.strictObject({
  registration_mode: RegistrationModeSchema,
  registration_domains: z.array(z.string()),
  require_approval: z.boolean(),
  fields: settingFields,
});
export const UpdateAdminRegistrationRequestSchema = z.strictObject({
  registration_mode: RegistrationModeSchema.nullable(),
  registration_domains: z.array(z.string()).nullable(),
  require_approval: z.boolean().nullable(),
});
export const AdminAuthSettingsSchema = z.strictObject({
  password_enabled: z.boolean(),
  oidc_enabled_count: z.number().int(),
  fields: settingFields,
});
export const UpdateAdminAuthRequestSchema = z.strictObject({
  password_enabled: z.boolean().nullable(),
});
export const AdminSmtpSettingsSchema = z.strictObject({
  enabled: z.boolean(),
  host: z.string().nullable(),
  port: z.number().int(),
  security: SmtpSecuritySchema,
  username: z.string().nullable(),
  password_set: z.boolean(),
  from_address: z.string(),
  from_name: z.string(),
  fields: settingFields,
});
export const UpdateAdminSmtpRequestSchema = z.strictObject({
  host: z.string().nullable(),
  port: z.number().int().nullable(),
  security: SmtpSecuritySchema.nullable(),
  username: z.string().nullable(),
  password: z.string().nullable(),
  from_address: z.string().nullable(),
  from_name: z.string().nullable(),
});
export const AdminSmtpTestRequestSchema = z.strictObject({
  to: z.string().nullable(),
});
export const AdminSmtpTestResultSchema = z.strictObject({
  ok: z.boolean(),
  error: z.string().nullable(),
});
export const AdminOidcProviderSchema = z.strictObject({
  id: z.string(),
  label: z.string(),
  issuer: z.string(),
  client_id: z.string(),
  client_secret_set: z.boolean(),
  scopes: z.string(),
  enabled: z.boolean(),
  auto_provision: z.boolean(),
  created_at: iso,
});
export const AdminOidcProviderPageSchema = pageOf(AdminOidcProviderSchema);
export const CreateAdminOidcProviderRequestSchema = z.strictObject({
  label: z.string(),
  issuer: z.string(),
  client_id: z.string(),
  client_secret: z.string(),
  scopes: z.string(),
  enabled: z.boolean(),
  auto_provision: z.boolean(),
});
export const UpdateAdminOidcProviderRequestSchema = z.strictObject({
  label: z.string().nullable(),
  issuer: z.string().nullable(),
  client_id: z.string().nullable(),
  client_secret: z.string().nullable(),
  scopes: z.string().nullable(),
  enabled: z.boolean().nullable(),
  auto_provision: z.boolean().nullable(),
});

const JobStateSchema = z.enum([
  "queued",
  "running",
  "succeeded",
  "failed",
  "cancelled",
  "timed_out",
]);
export const AdminJobSchema = z.strictObject({
  id: z.string(),
  kind: z.enum([
    "compile",
    "office.convert",
    "signature.verify_detached",
    "pack.submission",
  ]),
  state: JobStateSchema,
  project_id: z.string(),
  user_id: z.string(),
  org_id: z.string().nullable(),
  tags: z.array(z.string()),
  priority_class: z.string(),
  queued_at: iso,
  started_at: iso.nullable(),
  finished_at: iso.nullable(),
  attempt: z.number().int(),
  max_attempts: z.number().int(),
  runner_id: z.string().nullable(),
  cancel_requested: z.boolean(),
  error_code: z.string().nullable(),
  // Подписи от сервера (JOIN); null, если записи уже нет.
  user_name: z.string().nullable(),
  user_email: z.string().nullable(),
  org_name: z.string().nullable(),
  project_name: z.string().nullable(),
  runner_name: z.string().nullable(),
});
/** Журнал очереди: курсор непрозрачный, null на последней странице; оценка только без фильтров. */
export const AdminJobPageSchema = cursorPageOf(AdminJobSchema);
export const AdminQueueSummarySchema = z.strictObject({
  by_state: z.record(z.string(), z.number().int()),
  queued_by_class: z.record(z.string(), z.number().int()),
  oldest_queued_at: iso.nullable(),
  wait_p50_s: z.number().nullable(),
  wait_p95_s: z.number().nullable(),
});
export const AdminQuotasSchema = z.strictObject({
  user_concurrent: z.number().int().nullable(),
  org_concurrent: z.number().int().nullable(),
  max_duration_s: z.number().int().nullable(),
  on_exhausted: z.literal("wait"),
});
export const UpdateAdminQuotasRequestSchema = z.strictObject({
  user_concurrent: z.number().int().min(1).max(1000).nullable(),
  org_concurrent: z.number().int().min(1).max(1000).nullable(),
  max_duration_s: z.number().int().min(10).max(86400).nullable(),
});
export const AdminServiceHealthSchema = z.strictObject({
  id: z.string(),
  state: z.enum(["ok", "down", "degraded", "not_configured"]),
  reason: z.string().nullable(),
  total: z.number().int().nullable(),
  online: z.number().int().nullable(),
});
export const AdminStorageUsageSchema = z.strictObject({
  blob_count: z.number().int(),
  blob_bytes: z.number().int(),
  projects: z.number().int(),
  deleted_projects: z.number().int(),
  top_owners: z.array(
    z.strictObject({
      owner_id: z.string(),
      owner_name: z.string(),
      projects: z.number().int(),
    }),
  ),
  volume_total_bytes: z.number().int().nullable(),
  volume_free_bytes: z.number().int().nullable(),
  computed_at: iso.nullable(),
});
export const AdminStorageOwnerRowSchema = z.strictObject({
  kind: z.enum(["user", "org"]),
  id: z.string(),
  name: z.string(),
  email: z.string().nullable(),
  projects: z.number().int(),
  bytes: z.number().int(),
});
export const AdminStorageOwnerPageSchema = pageOf(AdminStorageOwnerRowSchema);
export type AdminStorageOwnerRow = z.infer<typeof AdminStorageOwnerRowSchema>;
const ServerKeyPolicySchema = z.enum(["allowed", "forbidden"]);
export const AdminSigningPolicySchema = z.strictObject({
  server_keys: ServerKeyPolicySchema,
  stored_keys: z.number().int(),
});
export type AdminSigningPolicy = z.infer<typeof AdminSigningPolicySchema>;
export type SigningServerKeys = z.infer<typeof ServerKeyPolicySchema>;
export const UpdateAdminSigningPolicyRequestSchema = z.strictObject({
  server_keys: ServerKeyPolicySchema,
});
const AiProviderTypeSchema = z.enum([
  "claude",
  "openai",
  "openai_compat",
  "ollama",
]);
export const AdminAiProviderSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  type: AiProviderTypeSchema,
  base_url: z.string(),
  models: z.array(z.string()),
  key_set: z.boolean(),
  ssl_verify: z.boolean(),
  connect_timeout_s: z.number(),
  request_timeout_s: z.number(),
  created_at: iso,
});
export const AdminAiProviderPageSchema = pageOf(AdminAiProviderSchema);
export const CreateAdminAiProviderRequestSchema = z.strictObject({
  name: z.string().min(1).max(128),
  type: AiProviderTypeSchema,
  api_key: z.string(),
  base_url: z.string(),
  models: z.array(z.string()),
  ssl_verify: z.boolean(),
  connect_timeout_s: z.number(),
  request_timeout_s: z.number(),
});
export const UpdateAdminAiProviderRequestSchema = z.strictObject({
  name: z.string().nullable(),
  type: AiProviderTypeSchema.nullable(),
  api_key: z.string().nullable(),
  clear_key: z.boolean(),
  base_url: z.string().nullable(),
  models: z.array(z.string()).nullable(),
  ssl_verify: z.boolean().nullable(),
  connect_timeout_s: z.number().nullable(),
  request_timeout_s: z.number().nullable(),
});
export const AdminAiProviderCheckSchema = z.strictObject({
  ok: z.boolean(),
  models: z.array(z.string()),
  error: z.string().nullable(),
});
export type AdminSettingState = z.infer<typeof SettingStateSchema>;
export type AdminRegistrationSettings = z.infer<
  typeof AdminRegistrationSettingsSchema
>;
export type UpdateAdminRegistrationRequest = z.infer<
  typeof UpdateAdminRegistrationRequestSchema
>;
export type AdminAuthSettings = z.infer<typeof AdminAuthSettingsSchema>;
export type AdminSmtpSettings = z.infer<typeof AdminSmtpSettingsSchema>;
export type UpdateAdminSmtpRequest = z.infer<
  typeof UpdateAdminSmtpRequestSchema
>;
export type AdminSmtpTestResult = z.infer<typeof AdminSmtpTestResultSchema>;
export type AdminOidcProvider = z.infer<typeof AdminOidcProviderSchema>;
export type CreateAdminOidcProviderRequest = z.infer<
  typeof CreateAdminOidcProviderRequestSchema
>;
export type UpdateAdminOidcProviderRequest = z.infer<
  typeof UpdateAdminOidcProviderRequestSchema
>;

export const COMPILE_WAIT_REASONS = [
  "queued",
  "no_runner",
  "quota_wait",
  "runner_lost",
  "superseded",
] as const;
export const CompileWaitSchema = z.strictObject({
  reason: z.enum(COMPILE_WAIT_REASONS),
  queue_position: z.number().int().min(1).nullable(),
  wait_hint_seconds: z.number().int().min(0).nullable(),
  attempt: z.number().int().min(1).nullable(),
  max_attempts: z.number().int().min(1).nullable(),
});
export type CompileWait = z.infer<typeof CompileWaitSchema>;
export type CompileWaitReason = CompileWait["reason"];
export const OfficeEditorBusySchema = z.strictObject({
  state: z.literal("editor_busy"),
  retry_after_s: z.number().int().min(1),
  limit: z.number().int().min(1),
});
export type OfficeEditorBusy = z.infer<typeof OfficeEditorBusySchema>;
