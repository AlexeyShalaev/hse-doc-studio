import type { ZodType } from "zod";
import { z } from "zod";

// Маршрут подписания «Отправить на подписание» (docs/design/signing-route.md, раздел 8).
// Только серверный режим: локальная Студия отвечает 404. Бэкенда пока нет (срезы R5, R6),
// поэтому источник истины здесь контракт раздела 8. strictObject повторяет extra=forbid
// будущих моделей api/schemas/signing_route.py: лишнее поле значит расхождение сторон.
// Все поля приходят явно, пустое значение это null.

const iso = z.string().min(1);
const LocalizedSchema = z.record(z.string(), z.string());

export const SigningRouteStatusSchema = z.enum([
  "draft",
  "active",
  "paused",
  "returned",
  "completed",
  "cancelled",
  "archived",
]);
export type SigningRouteStatus = z.infer<typeof SigningRouteStatusSchema>;

/** Фаза есть только у активного и завершённого маршрута; у остальных null. */
export const SigningRoutePhaseSchema = z.enum(["approval", "signing", "done"]);
export type SigningRoutePhase = z.infer<typeof SigningRoutePhaseSchema>;

export const SigningStopReasonSchema = z.enum([
  "rebuilt",
  "marks_changed",
  "frozen_changed",
  "participant_left",
  "returned",
]);
export type SigningStopReason = z.infer<typeof SigningStopReasonSchema>;

/**
 * Состояние участника (раздел 5.3, `ParticipantState` ядра), вычисляется сервером.
 * `waiting` и у того, кто согласовал до фиксации и ждёт её: у него есть `approved_at`.
 */
export const ParticipantStateSchema = z.enum([
  "invited",
  "waiting",
  "to_approve",
  "to_approve_sign",
  "to_sign",
  "done",
  "returned",
]);
export type ParticipantState = z.infer<typeof ParticipantStateSchema>;

/** Следующее действие участника, как в `evaluate()` (раздел 5.1). */
export const SigningNextActionSchema = z.enum([
  "wait",
  "approve",
  "approve_and_sign",
  "sign",
  "done",
]);
export type SigningNextAction = z.infer<typeof SigningNextActionSchema>;

/** Действие, которое ждут от человека прямо сейчас (задачи «На подпись»). */
export const SigningTaskActionSchema = z.enum([
  "approve",
  "approve_and_sign",
  "sign",
]);
export type SigningTaskAction = z.infer<typeof SigningTaskActionSchema>;

/** Статус человека в проекте: участник, приглашение отправлено, нет в проекте. */
export const ParticipantMembershipSchema = z.enum([
  "member",
  "invited",
  "missing",
]);
export type ParticipantMembership = z.infer<typeof ParticipantMembershipSchema>;

/** Способ подписи слота, как `SignMethod` плана подписей. */
export const RouteSignMethodSchema = z.enum(["image", "detached", "pades"]);
export type RouteSignMethod = z.infer<typeof RouteSignMethodSchema>;

/** Статус слота, как `SlotStatus` плана подписей. */
export const RouteSlotStatusSchema = z.enum([
  "pending",
  "signed",
  "invalid",
  "stale",
]);
export type RouteSlotStatus = z.infer<typeof RouteSlotStatusSchema>;

/** Что видно на странице, как `VisibleMark` плана подписей. */
export const RouteVisibleMarkSchema = z.enum(["png", "plate", "none"]);
export type RouteVisibleMark = z.infer<typeof RouteVisibleMarkSchema>;

export const RouteEventKindSchema = z.enum([
  "sent",
  "approved",
  "signed",
  "returned",
  "paused",
  "resumed",
  "cancelled",
  "completed",
  "reminded",
  "invited",
  "frozen",
]);
export type RouteEventKind = z.infer<typeof RouteEventKindSchema>;

export const SigningProfileRefSchema = z.strictObject({
  id: z.string(),
  name: LocalizedSchema,
});
export type SigningProfileRef = z.infer<typeof SigningProfileRefSchema>;

export const SigningProjectRefSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
});
export type SigningProjectRef = z.infer<typeof SigningProjectRefSchema>;

export const SigningPersonRefSchema = z.strictObject({
  id: z.string(),
  name: z.string(),
});
export type SigningPersonRef = z.infer<typeof SigningPersonRefSchema>;

/** Пара «документ, слот» маршрута. */
export const RouteSlotRefSchema = z.strictObject({
  doc_id: z.string(),
  slot_id: z.string(),
});
export type RouteSlotRef = z.infer<typeof RouteSlotRefSchema>;

/** Событие маршрута. Комментарий видят управляющие маршрутом и его участники. */
export const RouteEventSchema = z.strictObject({
  id: z.string(),
  kind: RouteEventKindSchema,
  round: z.number().int().min(0),
  at: iso,
  who: z.string().nullable(),
  /** Участник маршрута, к которому относится событие (согласие, подпись, возврат); null у событий автора и сервера. */
  participant_id: z.string().nullable(),
  comment: z.string().nullable(),
  reason: SigningStopReasonSchema.nullable(),
});
export type RouteEvent = z.infer<typeof RouteEventSchema>;

// Ход маршрута глазами автора: GET/POST/PUT .../signing-routes[/{route_id}], send, cancel, archive.

export const RouteParticipantSchema = z.strictObject({
  id: z.string(),
  persona: z.string(),
  user_id: z.string().nullable(),
  invitation_id: z.string().nullable(),
  /** Имя участника; у приглашённого подсказка адреса; null, если человека ещё нет. */
  name: z.string().nullable(),
  membership: ParticipantMembershipSchema,
  /** Имя персоны по карточке проекта: у приглашённого `name` только маска почты. */
  card_name: z.string().nullable(),
  /** Пары маршрута этого участника; пусто: только согласование. */
  assignments: z.array(RouteSlotRefSchema),
  /** Способ его слотов; null у согласующего без слотов. */
  method: RouteSignMethodSchema.nullable(),
  state: ParticipantStateSchema,
  next_action: SigningNextActionSchema,
  /** Его согласие ещё меняет видимый слой: пока такие есть, PDF не фиксируется и ЭП не запрашивается. */
  changes_visible: z.boolean(),
  /** Согласие текущего раунда. */
  approved_at: iso.nullable(),
  notified_at: iso.nullable(),
  reminded_at: iso.nullable(),
  reminders: z.number().int().min(0),
});
export type RouteParticipant = z.infer<typeof RouteParticipantSchema>;

export const RouteDocSlotSchema = z.strictObject({
  slot_id: z.string(),
  label: LocalizedSchema,
  participant_id: z.string().nullable(),
  /** Необязательный для точки слот, который автор добавил в маршрут. */
  optional: z.boolean(),
  status: RouteSlotStatusSchema,
});
export type RouteDocSlot = z.infer<typeof RouteDocSlotSchema>;

export const RouteDocSchema = z.strictObject({
  doc_id: z.string(),
  name: LocalizedSchema,
  frozen: z.boolean(),
  slots: z.array(RouteDocSlotSchema),
});
export type RouteDoc = z.infer<typeof RouteDocSchema>;

/** Кого можно поставить на персону: участник проекта с ней или ожидающее приглашение с ней (раздел 6.5). */
export const RoutePersonOptionSchema = z.strictObject({
  kind: z.enum(["member", "invitation"]),
  /** `user_id` участника проекта или `invitation_id` приглашения: то, что передать в PUT. */
  id: z.string(),
  /** Имя; у приглашения имя аккаунта или подсказка адреса. */
  name: z.string().nullable(),
});
export type RoutePersonOption = z.infer<typeof RoutePersonOptionSchema>;

export const RoutePersonaCandidatesSchema = z.strictObject({
  persona: z.string(),
  people: z.array(RoutePersonOptionSchema),
});
export type RoutePersonaCandidates = z.infer<
  typeof RoutePersonaCandidatesSchema
>;

export const SigningRouteSchema = z.strictObject({
  id: z.string(),
  project_id: z.string(),
  profile: SigningProfileRefSchema,
  status: SigningRouteStatusSchema,
  phase: SigningRoutePhaseSchema.nullable(),
  round: z.number().int().min(0),
  /** Номер первого шага, где не все согласовали (с 1); null вне `active`. */
  current_step: z.number().int().min(1).nullable(),
  deadline: iso.nullable(),
  message: z.string().nullable(),
  stop_reason: SigningStopReasonSchema.nullable(),
  sent_by: SigningPersonRefSchema.nullable(),
  sent_at: iso.nullable(),
  completed_at: iso.nullable(),
  created_at: iso,
  updated_at: iso,
  docs: z.array(RouteDocSchema),
  /** Шаги по порядку; номер шага это индекс + 1, внутри шага параллельно. */
  steps: z.array(z.array(RouteParticipantSchema)),
  events: z.array(RouteEventSchema),
  /**
   * Из кого выбирать по персонам маршрута и его слотов (участники проекта, затем приглашения);
   * только тому, кто управляет маршрутом, остальным пусто.
   */
  candidates: z.array(RoutePersonaCandidatesSchema),
});
export type SigningRoute = z.infer<typeof SigningRouteSchema>;

export const SigningWaitingForSchema = z.strictObject({
  name: z.string().nullable(),
  persona: z.string(),
});

export const SigningRouteSummarySchema = z.strictObject({
  id: z.string(),
  profile: SigningProfileRefSchema,
  status: SigningRouteStatusSchema,
  phase: SigningRoutePhaseSchema.nullable(),
  round: z.number().int().min(0),
  current_step: z.number().int().min(1).nullable(),
  steps_total: z.number().int().min(0),
  deadline: iso.nullable(),
  stop_reason: SigningStopReasonSchema.nullable(),
  sent_at: iso.nullable(),
  completed_at: iso.nullable(),
  updated_at: iso,
  /** Чья очередь сейчас. */
  waiting_for: z.array(SigningWaitingForSchema),
});
export type SigningRouteSummary = z.infer<typeof SigningRouteSummarySchema>;

/** Маршруты точки, новые первыми; незавершённый не больше одного. */
export const SigningRouteListSchema = z.strictObject({
  items: z.array(SigningRouteSummarySchema),
});
export type SigningRouteList = z.infer<typeof SigningRouteListSchema>;

export const CreateSigningRouteRequestSchema = z.strictObject({
  profile_id: z.string().min(1),
});
export type CreateSigningRouteRequest = z.infer<
  typeof CreateSigningRouteRequestSchema
>;

/**
 * Человек в шаге при правке маршрута. Пары «документ, слот» сервер назначает сам по
 * персоне. Без `user_id` и `invitation_id` сервер подбирает человека по персоне, как в
 * заготовке (ещё не занятого в маршруте участника проекта, иначе приглашение); никого нет:
 * «нет в проекте» (мешает отправке).
 */
export const RouteParticipantDraftSchema = z
  .strictObject({
    id: z.string().nullable(),
    persona: z.string().min(1),
    user_id: z.string().nullable(),
    invitation_id: z.string().nullable(),
  })
  .refine((v) => v.user_id === null || v.invitation_id === null, {
    message: "user_id and invitation_id are mutually exclusive",
  });
export type RouteParticipantDraft = z.infer<typeof RouteParticipantDraftSchema>;

export const SIGNING_TEXT_MAX = 2000;

/** PUT заменяет шаги, людей, доп. слоты, срок и сообщение целиком. */
export const UpdateSigningRouteRequestSchema = z.strictObject({
  steps: z.array(z.array(RouteParticipantDraftSchema).min(1)),
  extra_slots: z.array(RouteSlotRefSchema),
  deadline: iso.nullable(),
  message: z.string().max(SIGNING_TEXT_MAX).nullable(),
});
export type UpdateSigningRouteRequest = z.infer<
  typeof UpdateSigningRouteRequestSchema
>;

/** Ключ Студии, которым подписывает сервер; пароль только на время подписи. */
export const SigningKeyRequestSchema = z.strictObject({
  identity_id: z.string().nullable(),
  passphrase: z.string().max(500).nullable(),
});
export type SigningKeyRequest = z.infer<typeof SigningKeyRequestSchema>;

export const SigningKeyInfoSchema = z.strictObject({
  id: z.string(),
  label: z.string(),
  kind: z.string(),
  protected: z.boolean(),
  signer: z.string(),
});
export type SigningKeyInfo = z.infer<typeof SigningKeyInfoSchema>;

export const SigningRoutePreviewDocSchema = z.strictObject({
  doc_id: z.string(),
  name: LocalizedSchema,
  built: z.boolean(),
  /** `build:<sha>`: что вернуть в `expected` отправки; null, пока документ не собран. */
  token: z.string().nullable(),
});

export const SigningRoutePreviewParticipantSchema = z.strictObject({
  participant_id: z.string(),
  step: z.number().int().min(1),
  persona: z.string(),
  name: z.string().nullable(),
  membership: ParticipantMembershipSchema,
  method: RouteSignMethodSchema.nullable(),
  /** Способы, разрешённые точкой для его слотов. */
  methods: z.array(RouteSignMethodSchema),
  /** Способ выберет сам подписант (`method_not_allowed` у слота). */
  chooses_method: z.boolean(),
  image_ready: z.boolean(),
  plate_ready: z.boolean(),
  /** Сколько действий на своей странице после отправки (раздел 4.4). */
  actions: z.number().int().min(0).max(2),
});

/** Маршрут, который держит документ (`doc_in_other_route`): его точка и статус. */
export const SigningRouteBlockerRouteSchema = z.strictObject({
  id: z.string(),
  profile: SigningProfileRefSchema,
  status: SigningRouteStatusSchema,
});
export type SigningRouteBlockerRoute = z.infer<
  typeof SigningRouteBlockerRouteSchema
>;

export const SigningRouteBlockerSchema = z.strictObject({
  code: z.string(),
  doc_id: z.string().nullable(),
  slot_id: z.string().nullable(),
  participant_id: z.string().nullable(),
  /** Только у `doc_in_other_route`: какой маршрут держит документ. */
  other_route: SigningRouteBlockerRouteSchema.nullable(),
});
export type SigningRouteBlocker = z.infer<typeof SigningRouteBlockerSchema>;

export const SigningRoutePreviewSchema = z.strictObject({
  route_id: z.string(),
  can_send: z.boolean(),
  /** L = 0 и отправитель подписывает ЭП: доступно «Отправить и подписать». */
  can_send_and_sign: z.boolean(),
  /** L: последний шаг, где кто-то ещё меняет видимый слой; 0: фиксация при отправке. */
  visual_step: z.number().int().min(0),
  docs: z.array(SigningRoutePreviewDocSchema),
  participants: z.array(SigningRoutePreviewParticipantSchema),
  blockers: z.array(SigningRouteBlockerSchema),
  /** Ключ отправителя для «Отправить и подписать»; null, если ключа нет. */
  sender_key: SigningKeyInfoSchema.nullable(),
});
export type SigningRoutePreview = z.infer<typeof SigningRoutePreviewSchema>;

export const SendSigningRouteRequestSchema = z.strictObject({
  expected: z.record(z.string(), z.string()),
  sign: SigningKeyRequestSchema.nullable(),
});
export type SendSigningRouteRequest = z.infer<
  typeof SendSigningRouteRequestSchema
>;

export const SigningDeliverySchema = z.enum(["email", "inbox", "manual"]);
export type SigningDelivery = z.infer<typeof SigningDeliverySchema>;

/** «Напомнить»: у приглашённого повторное приглашение, ссылка при `manual`. */
export const SigningReminderSchema = z.strictObject({
  participant_id: z.string(),
  delivery: SigningDeliverySchema,
  link: z.string().nullable(),
});
export type SigningReminder = z.infer<typeof SigningReminderSchema>;

/**
 * «Скопировать ссылку»: что автор сам перешлёт подписанту. `page` страница подписи участника с
 * аккаунтом; `invitation` новая ссылка приглашения (прежняя перестаёт работать); `inbox`
 * «Входящие» приглашённого как аккаунт.
 */
export const SigningLinkSchema = z.strictObject({
  participant_id: z.string(),
  kind: z.enum(["page", "invitation", "inbox"]),
  link: z.string().min(1),
});
export type SigningLink = z.infer<typeof SigningLinkSchema>;

// Задача подписанта: GET .../task и ответы действий task/*.

export const SigningTaskRouteSchema = z.strictObject({
  id: z.string(),
  project: SigningProjectRefSchema,
  profile: SigningProfileRefSchema,
  status: SigningRouteStatusSchema,
  phase: SigningRoutePhaseSchema.nullable(),
  round: z.number().int().min(0),
  current_step: z.number().int().min(1).nullable(),
  deadline: iso.nullable(),
  message: z.string().nullable(),
  sender: z.string().nullable(),
  sent_at: iso.nullable(),
  stop_reason: SigningStopReasonSchema.nullable(),
});
export type SigningTaskRoute = z.infer<typeof SigningTaskRouteSchema>;

export const SigningTaskPersonSchema = z.strictObject({
  name: z.string().nullable(),
  persona: z.string(),
  state: ParticipantStateSchema,
  /** Время последнего действия (согласие или подпись). */
  at: iso.nullable(),
  me: z.boolean(),
  /** Имя персоны по карточке проекта и меняет ли его согласие видимый слой, как у участника маршрута. */
  card_name: z.string().nullable(),
  changes_visible: z.boolean(),
});
export type SigningTaskPerson = z.infer<typeof SigningTaskPersonSchema>;

export const SigningPlateSchema = z.strictObject({
  owner: z.string(),
  kind: z.enum(["x509", "openpgp", "manual"]),
  cert_id: z.string(),
});
export type SigningPlate = z.infer<typeof SigningPlateSchema>;

export const SigningTaskMeSchema = z.strictObject({
  participant_id: z.string(),
  state: ParticipantStateSchema,
  next_action: SigningNextActionSchema,
  /** Разрешённые сейчас способы; после фиксации только без новой видимой метки. */
  methods: z.array(RouteSignMethodSchema),
  method: RouteSignMethodSchema.nullable(),
  image_ready: z.boolean(),
  /** Путь API от корня сайта к своей загруженной картинке (PNG) для предпросмотра; null, пока её нет. */
  image_url: z.string().nullable(),
  /** Данные плашки, известные серверу: из слота, профиля подписанта или его ключа по умолчанию. */
  plate: SigningPlateSchema.nullable(),
  keys: z.strictObject({
    server_keys_allowed: z.boolean(),
    default_key: SigningKeyInfoSchema.nullable(),
  }),
});
export type SigningTaskMe = z.infer<typeof SigningTaskMeSchema>;

/** Чужой слот на документе: место и статус, без причины плана. */
export const SigningTaskOtherSlotSchema = z.strictObject({
  slot_id: z.string(),
  label: LocalizedSchema,
  page: z.number().int().min(1),
  x_mm: z.number(),
  y_mm: z.number(),
  width_mm: z.number(),
  /** Высота метки: картинка по своим пропорциям, плашка по вёрстке; null у слота без видимой метки. */
  height_mm: z.number().nullable(),
  mark: RouteVisibleMarkSchema,
  status: RouteSlotStatusSchema,
});
export type SigningTaskOtherSlot = z.infer<typeof SigningTaskOtherSlotSchema>;

/** Свой слот: ещё и причина плана. */
export const SigningTaskSlotSchema = z.strictObject({
  ...SigningTaskOtherSlotSchema.shape,
  /** Причина плана (`PlanReason`, в том числе `awaiting_approval`); null у подписанного. */
  reason: z.string().nullable(),
});
export type SigningTaskSlot = z.infer<typeof SigningTaskSlotSchema>;

export const SigningTaskDocSchema = z.strictObject({
  doc_id: z.string(),
  name: LocalizedSchema,
  /** Путь API от корня сайта (`/api/v1/...`): до фиксации предпросмотр, после зафиксированный PDF. */
  pdf_url: z.string().min(1),
  frozen: z.boolean(),
  /**
   * Отпечаток для `expected` следующего действия: `build:<sha>` для согласия,
   * `build:<sha>:<видимый слой>` для согласия с фиксацией, `pdf:<sha>` для подписи;
   * null, когда действовать нечего.
   */
  token: z.string().nullable(),
  mine: z.array(SigningTaskSlotSchema),
  others: z.array(SigningTaskOtherSlotSchema),
});
export type SigningTaskDoc = z.infer<typeof SigningTaskDocSchema>;

export const SigningTaskSchema = z.strictObject({
  route: SigningTaskRouteSchema,
  steps: z.array(z.array(SigningTaskPersonSchema)),
  me: SigningTaskMeSchema,
  docs: z.array(SigningTaskDocSchema),
  events: z.array(RouteEventSchema),
});
export type SigningTask = z.infer<typeof SigningTaskSchema>;

export const ApproveSigningTaskRequestSchema = z.strictObject({
  expected: z.record(z.string(), z.string()),
  /** Сменить способ своих слотов (из `me.methods`); null: оставить. */
  method: RouteSignMethodSchema.nullable(),
  /** «Согласовать и подписать»: подписать свои криптослоты в том же запросе. */
  sign: SigningKeyRequestSchema.nullable(),
});
export type ApproveSigningTaskRequest = z.infer<
  typeof ApproveSigningTaskRequestSchema
>;

export const SignSigningTaskRequestSchema = z.strictObject({
  expected: z.record(z.string(), z.string()),
  identity_id: z.string().nullable(),
  passphrase: z.string().max(500).nullable(),
});
export type SignSigningTaskRequest = z.infer<
  typeof SignSigningTaskRequestSchema
>;

export const ReturnSigningTaskRequestSchema = z.strictObject({
  comment: z.string().trim().min(1).max(SIGNING_TEXT_MAX),
});
export type ReturnSigningTaskRequest = z.infer<
  typeof ReturnSigningTaskRequestSchema
>;

/** Плашка из своего ключа Студии; сертификат файлом идёт multipart в `task/plate/file`. */
export const SetSigningTaskPlateRequestSchema = z.strictObject({
  identity_id: z.string().min(1),
});
export type SetSigningTaskPlateRequest = z.infer<
  typeof SetSigningTaskPlateRequestSchema
>;

// «На подпись»: GET /account/signing-tasks.

export const SigningTaskSummarySchema = z.strictObject({
  project: SigningProjectRefSchema,
  route_id: z.string(),
  profile: SigningProfileRefSchema,
  round: z.number().int().min(0),
  sender: z.string().nullable(),
  deadline: iso.nullable(),
  next_action: SigningTaskActionSchema,
  /** С какого времени ждёт (уведомление этого раунда). */
  since: iso.nullable(),
});
export type SigningTaskSummary = z.infer<typeof SigningTaskSummarySchema>;

export const SigningTaskListSchema = z.strictObject({
  items: z.array(SigningTaskSummarySchema),
});
export type SigningTaskList = z.infer<typeof SigningTaskListSchema>;

/**
 * Коды ошибок маршрута (тело `{detail, code}`), раздел 8.1. 404 `not_found` отдаётся и не
 * участнику, и в локальном режиме. 409 и 429 ниже; 400 за неверно собранный маршрут
 * (`no_participants`, `bad_step`, `duplicate_participant`, `duplicate_slot`, `unknown_doc`);
 * 403 `server_keys_forbidden` за подпись ключом Студии при запрете ключей на сервере.
 */
export const SIGNING_ROUTE_ERROR_CODES = [
  "doc_changed",
  "invalid_transition",
  "not_your_turn",
  "image_required",
  "plate_required",
  "method_not_allowed",
  "visible_layer_final",
  "invalid_file",
  "passphrase_required",
  "passphrase_invalid",
  "sign_failed",
  "key_not_found",
  "server_keys_forbidden",
  "forbidden",
  "route_blocked",
  "route_locked",
  "participant_not_waiting",
  "rate_limited",
] as const;
export type SigningRouteErrorCode = (typeof SIGNING_ROUTE_ERROR_CODES)[number];

/**
 * Будущие каталоги contracts/server/fixtures -> схема. Срезы R5 и R6 кладут эталоны
 * (testing/fixtures: SIGNING_ROUTE_CONTRACT_EXAMPLES) в contracts/server и добавляют эту
 * карту в CONTRACT_SCHEMAS вместе с моделями pydantic.
 */
export const SIGNING_ROUTE_CONTRACT_SCHEMAS: Record<string, ZodType> = {
  SigningRoute: SigningRouteSchema,
  SigningRouteList: SigningRouteListSchema,
  CreateSigningRouteRequest: CreateSigningRouteRequestSchema,
  UpdateSigningRouteRequest: UpdateSigningRouteRequestSchema,
  SigningRoutePreview: SigningRoutePreviewSchema,
  SendSigningRouteRequest: SendSigningRouteRequestSchema,
  SigningReminder: SigningReminderSchema,
  SigningLink: SigningLinkSchema,
  SigningTask: SigningTaskSchema,
  ApproveSigningTaskRequest: ApproveSigningTaskRequestSchema,
  SignSigningTaskRequest: SignSigningTaskRequestSchema,
  ReturnSigningTaskRequest: ReturnSigningTaskRequestSchema,
  SetSigningTaskPlateRequest: SetSigningTaskPlateRequestSchema,
  SigningTaskList: SigningTaskListSchema,
};
