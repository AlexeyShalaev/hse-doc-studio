import { z } from "zod";

// Приглашения в проект, запросы доступа, передача владения, уведомления и сводка «Входящих».
// Зеркало api/schemas/invitations.py; эталоны лежат в contracts/server/fixtures
// (ProjectInvitation, MyInvitation, AccessRequestView, MyTransfer, Notification...).
// strictObject повторяет extra=forbid бэкенда: лишнее поле значит расхождение сторон.

const iso = z.string().min(1);

export const GrantRoleSchema = z.enum(["reader", "reviewer", "editor"]);
export type GrantRole = z.infer<typeof GrantRoleSchema>;

export const InvitationStatusSchema = z.enum([
  "pending",
  "accepted",
  "declined",
  "revoked",
  "expired",
]);
export type InvitationStatus = z.infer<typeof InvitationStatusSchema>;

export const PersonRefSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
});
export type PersonRef = z.infer<typeof PersonRefSchema>;

export const InvitationInviteeSchema = z.strictObject({
  kind: z.enum(["user", "email"]),
  user_id: z.string().nullable(),
  name: z.string().nullable(),
  email_hint: z.string().nullable(),
});

export const ProjectInvitationSchema = z.strictObject({
  id: z.string(),
  invitee: InvitationInviteeSchema,
  role: GrantRoleSchema,
  persona: z.string().nullable(),
  can_share: z.boolean(),
  show_sources: z.boolean(),
  can_edit_all: z.boolean(),
  message: z.string().nullable(),
  invited_by: PersonRefSchema.nullable(),
  created_at: iso,
  expires_at: iso,
  status: InvitationStatusSchema,
  sent_count: z.number().int(),
  last_sent_at: iso,
});
export type ProjectInvitation = z.infer<typeof ProjectInvitationSchema>;

export const ProjectInvitationPageSchema = z.strictObject({
  items: z.array(ProjectInvitationSchema),
  total: z.number().int(),
  limit: z.number().int(),
  offset: z.number().int(),
});
export type ProjectInvitationPage = z.infer<typeof ProjectInvitationPageSchema>;

export const CreateProjectInvitationRequestSchema = z
  .strictObject({
    user_id: z.string().nullable(),
    email: z.string().nullable(),
    role: GrantRoleSchema,
    persona: z.string().nullable(),
    can_share: z.boolean(),
    show_sources: z.boolean(),
    can_edit_all: z.boolean(),
    message: z.string().max(1000).nullable(),
    expires_in_days: z.number().int().min(1).max(30),
  })
  .refine((v) => (v.user_id === null) !== (v.email === null));
export type CreateProjectInvitationRequest = z.infer<
  typeof CreateProjectInvitationRequestSchema
>;

export const InvitationDeliverySchema = z.enum(["email", "manual", "inbox"]);
export type InvitationDelivery = z.infer<typeof InvitationDeliverySchema>;

export const ProjectInvitationCreatedSchema = z.strictObject({
  invitation: ProjectInvitationSchema,
  delivery: InvitationDeliverySchema,
  link: z.string().nullable(),
});
export type ProjectInvitationCreated = z.infer<
  typeof ProjectInvitationCreatedSchema
>;

export const MyInvitationSchema = z.strictObject({
  id: z.string(),
  project: z.strictObject({
    id: z.string(),
    name: z.string(),
    owner_name: z.string(),
  }),
  role: GrantRoleSchema,
  persona: z.string().nullable(),
  message: z.string().nullable(),
  invited_by: PersonRefSchema.nullable(),
  created_at: iso,
  expires_at: iso,
  status: InvitationStatusSchema,
});
export type MyInvitation = z.infer<typeof MyInvitationSchema>;

export const MyInvitationListSchema = z.strictObject({
  items: z.array(MyInvitationSchema),
});

export const ProjectInvitationPreviewSchema = z.strictObject({
  state: z.enum(["ok", "expired", "used", "invalid"]),
  project_name: z.string().nullable(),
  inviter_name: z.string().nullable(),
  role: GrantRoleSchema.nullable(),
  email_hint: z.string().nullable(),
  registration_token: z.string().nullable(),
});
export type ProjectInvitationPreview = z.infer<
  typeof ProjectInvitationPreviewSchema
>;

export const AccessRequestStatusSchema = z.enum([
  "pending",
  "approved",
  "denied",
  "cancelled",
]);
export type AccessRequestStatus = z.infer<typeof AccessRequestStatusSchema>;

export const AccessRequestViewSchema = z.strictObject({
  id: z.string(),
  requester: z.strictObject({
    id: z.string(),
    name: z.string(),
    email: z.string(),
  }),
  message: z.string().nullable(),
  status: AccessRequestStatusSchema,
  created_at: iso,
  decided_at: iso.nullable(),
  decided_by: PersonRefSchema.nullable(),
  granted_role: GrantRoleSchema.nullable(),
});
export type AccessRequestView = z.infer<typeof AccessRequestViewSchema>;

export const AccessRequestPageSchema = z.strictObject({
  items: z.array(AccessRequestViewSchema),
  total: z.number().int(),
  limit: z.number().int(),
  offset: z.number().int(),
});
export type AccessRequestPage = z.infer<typeof AccessRequestPageSchema>;

export const ApproveAccessRequestSchema = z.strictObject({
  role: GrantRoleSchema,
  persona: z.string().nullable(),
  can_share: z.boolean(),
  show_sources: z.boolean(),
  can_edit_all: z.boolean(),
});
export type ApproveAccessRequest = z.infer<typeof ApproveAccessRequestSchema>;

export const DenyAccessRequestSchema = z.strictObject({
  message: z.string().max(1000).nullable(),
});

export const CreateAccessRequestSchema = z.strictObject({
  project_id: z.string(),
  message: z.string().max(1000).nullable(),
});
export type CreateAccessRequest = z.infer<typeof CreateAccessRequestSchema>;

export const AccessRequestAcceptedSchema = z.strictObject({
  accepted: z.literal(true),
});

export const MyAccessRequestSchema = z.strictObject({
  id: z.string(),
  project: z.strictObject({ id: z.string(), name: z.string().nullable() }),
  status: AccessRequestStatusSchema,
  created_at: iso,
  decided_at: iso.nullable(),
  granted_role: GrantRoleSchema.nullable(),
});
export type MyAccessRequest = z.infer<typeof MyAccessRequestSchema>;

export const MyAccessRequestListSchema = z.strictObject({
  items: z.array(MyAccessRequestSchema),
});

export const OwnerKindSchema = z.enum(["user", "org"]);
export type OwnerKind = z.infer<typeof OwnerKindSchema>;

export const ProjectTransferStateSchema = z.strictObject({
  pending: z.boolean(),
  transfer: z
    .strictObject({
      id: z.string(),
      to: z.strictObject({
        kind: OwnerKindSchema,
        id: z.string(),
        name: z.string(),
      }),
      created_at: iso,
      expires_at: iso,
      message: z.string().nullable(),
    })
    .nullable(),
});
export type ProjectTransferState = z.infer<typeof ProjectTransferStateSchema>;

export const StartProjectTransferRequestSchema = z.strictObject({
  to_kind: OwnerKindSchema,
  to_id: z.string().min(1),
  message: z.string().max(1000).nullable(),
  confirm_name: z.string().nullable(),
});
export type StartProjectTransferRequest = z.infer<
  typeof StartProjectTransferRequestSchema
>;

export const TransferStatusSchema = z.enum([
  "pending",
  "accepted",
  "declined",
  "cancelled",
  "superseded",
  "expired",
]);

export const MyTransferSchema = z.strictObject({
  id: z.string(),
  project: z.strictObject({ id: z.string(), name: z.string() }),
  from: z.strictObject({ kind: OwnerKindSchema, name: z.string() }),
  message: z.string().nullable(),
  created_at: iso,
  expires_at: iso,
  status: TransferStatusSchema,
  previous_owner_role: GrantRoleSchema.nullable(),
});
export type MyTransfer = z.infer<typeof MyTransferSchema>;

export const MyTransferListSchema = z.strictObject({
  items: z.array(MyTransferSchema),
});

export const NOTIFICATION_KINDS = [
  "project_invitation",
  "invitation_accepted",
  "invitation_declined",
  "access_request",
  "access_request_decided",
  "transfer_request",
  "transfer_decided",
  "member_removed",
] as const;
export const NotificationKindSchema = z.enum(NOTIFICATION_KINDS);
export type NotificationKind = z.infer<typeof NotificationKindSchema>;

export const NotificationSchema = z.strictObject({
  id: z.string(),
  kind: NotificationKindSchema,
  created_at: iso,
  read_at: iso.nullable(),
  payload: z.strictObject({
    project_id: z.string().nullable(),
    project_name: z.string().nullable(),
    actor_name: z.string().nullable(),
    role: z.string().nullable(),
    ref_id: z.string().nullable(),
    outcome: z.enum(["accepted", "declined", "approved", "denied"]).nullable(),
  }),
});
export type Notification = z.infer<typeof NotificationSchema>;

export const NotificationPageSchema = z.strictObject({
  items: z.array(NotificationSchema),
  total: z.number().int(),
  limit: z.number().int(),
  offset: z.number().int(),
});
export type NotificationPage = z.infer<typeof NotificationPageSchema>;

export const MarkNotificationsReadRequestSchema = z.strictObject({
  ids: z.array(z.string()).nullable(),
});

export const InboxSummarySchema = z.strictObject({
  unread: z.number().int(),
  invitations: z.number().int(),
  transfers: z.number().int(),
  access_requests: z.number().int(),
});
export type InboxSummary = z.infer<typeof InboxSummarySchema>;

export const InboxBadgeSchema = z.strictObject({ unread: z.number().int() });
