import { z } from "zod";
import { GuestInfoSchema, LinkRoleSchema } from "@entities/session";

// Зеркало services/api/hse_doc_studio/api/schemas/sharing.py (раздел links контракта).
// Эталоны: contracts/server/fixtures/ShareLink*, GuestInfo, OrgSharingPolicy, AdminSharingSettings.

const iso = z.string().min(1);

export { GuestInfoSchema, LinkRoleSchema };
export type { GuestInfo, GuestLinkInfo, LinkRole } from "@entities/session";

export const LinkStateSchema = z.enum([
  "active",
  "expired",
  "revoked",
  "blocked",
]);
export type LinkState = z.infer<typeof LinkStateSchema>;
export const LinkBlockReasonSchema = z.enum([
  "links_disabled",
  "org_links_off",
  "org_role_cap",
  "nda",
]);
export type LinkBlockReason = z.infer<typeof LinkBlockReasonSchema>;

export const ShareLinkSchema = z.strictObject({
  id: z.string(),
  label: z.string(),
  role: LinkRoleSchema,
  show_sources: z.boolean(),
  require_login: z.boolean(),
  has_password: z.boolean(),
  // Адрес есть только у действующей и заблокированной политикой ссылки.
  url: z.string().nullable(),
  token_prefix: z.string(),
  // Автор скрыт у редактора: он видит только свои ссылки.
  created_by: z.strictObject({ id: z.string(), name: z.string() }).nullable(),
  created_at: iso,
  updated_at: iso,
  expires_at: iso.nullable(),
  state: LinkStateSchema,
  blocked_reason: LinkBlockReasonSchema.nullable(),
  editable: z.boolean(),
  visits: z.strictObject({
    visitors: z.number().int(),
    opens: z.number().int(),
    last_at: iso.nullable(),
  }),
});
export type ShareLink = z.infer<typeof ShareLinkSchema>;

export const ShareLinkListSchema = z.strictObject({
  items: z.array(ShareLinkSchema),
  can_create: z.boolean(),
  max_role: LinkRoleSchema,
  forced_login: z.boolean(),
  revoked_count: z.number().int(),
});
export type ShareLinkList = z.infer<typeof ShareLinkListSchema>;

export const CreateShareLinkRequestSchema = z.strictObject({
  label: z.string(),
  role: LinkRoleSchema,
  show_sources: z.boolean(),
  require_login: z.boolean(),
  password: z.string().nullable(),
  expires_in_days: z.number().int().nullable(),
});
export type CreateShareLinkRequest = z.infer<
  typeof CreateShareLinkRequestSchema
>;

export const UpdateShareLinkRequestSchema = z.strictObject({
  label: z.string().nullable(),
  role: LinkRoleSchema.nullable(),
  show_sources: z.boolean().nullable(),
  require_login: z.boolean().nullable(),
  password: z.string().nullable(),
  clear_password: z.boolean(),
  expires_in_days: z.number().int().nullable(),
  clear_expiry: z.boolean(),
});
export type UpdateShareLinkRequest = z.infer<
  typeof UpdateShareLinkRequestSchema
>;

export const ShareLinkVisitSchema = z.strictObject({
  visitor_kind: z.enum(["guest", "user"]),
  name: z.string().nullable(),
  first_at: iso,
  last_at: iso,
  opens: z.number().int(),
});
export type ShareLinkVisit = z.infer<typeof ShareLinkVisitSchema>;
export const ShareLinkVisitPageSchema = z.strictObject({
  items: z.array(ShareLinkVisitSchema),
  total: z.number().int(),
  limit: z.number().int(),
  offset: z.number().int(),
});
export type ShareLinkVisitPage = z.infer<typeof ShareLinkVisitPageSchema>;

export const LinkPreviewStateSchema = z.enum([
  "ok",
  "password_required",
  "login_required",
  "org_only",
  "inactive",
]);
export type LinkPreviewState = z.infer<typeof LinkPreviewStateSchema>;
export const ShareLinkPreviewSchema = z.strictObject({
  state: LinkPreviewStateSchema,
  project_name: z.string().nullable(),
  owner_name: z.string().nullable(),
  role: LinkRoleSchema.nullable(),
  show_sources: z.boolean(),
  guest_name_required: z.boolean(),
  signed_in: z.boolean(),
});
export type ShareLinkPreview = z.infer<typeof ShareLinkPreviewSchema>;

export const OpenShareLinkRequestSchema = z.strictObject({
  password: z.string().nullable(),
  guest_name: z.string().nullable(),
});
export type OpenShareLinkRequest = z.infer<typeof OpenShareLinkRequestSchema>;

export const OpenShareLinkResponseSchema = z.strictObject({
  project_id: z.string(),
  mode: z.enum(["guest", "user"]),
  role: LinkRoleSchema,
  show_sources: z.boolean(),
  landing: z.enum(["workspace", "view"]),
});
export type OpenShareLinkResponse = z.infer<typeof OpenShareLinkResponseSchema>;

export const UpdateGuestSessionRequestSchema = z.strictObject({
  name: z.string(),
});

export const OrgLinksModeSchema = z.enum(["any", "org_only", "off"]);
export type OrgLinksMode = z.infer<typeof OrgLinksModeSchema>;
export const OrgSharingPolicySchema = z.strictObject({
  links: OrgLinksModeSchema,
  max_link_role: LinkRoleSchema,
  nda_public_links: z.boolean(),
  external_invites: z.boolean(),
  editable: z.boolean(),
});
export type OrgSharingPolicy = z.infer<typeof OrgSharingPolicySchema>;

const SettingStateSchema = z.strictObject({
  source: z.enum(["env", "admin", "default"]),
  locked: z.boolean(),
});
export const AdminSharingSettingsSchema = z.strictObject({
  links_enabled: z.boolean(),
  max_link_role: LinkRoleSchema,
  project_invites_allow_signup: z.boolean(),
  fields: z.record(z.string(), SettingStateSchema),
});
export type AdminSharingSettings = z.infer<typeof AdminSharingSettingsSchema>;
export const UpdateAdminSharingRequestSchema = z.strictObject({
  links_enabled: z.boolean().nullable(),
  max_link_role: LinkRoleSchema.nullable(),
  project_invites_allow_signup: z.boolean().nullable(),
});
export type UpdateAdminSharingRequest = z.infer<
  typeof UpdateAdminSharingRequestSchema
>;
