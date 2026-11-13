import type { ZodType } from "zod";
import { z } from "zod";

// Маршрут подписания «Отправить на подписание» (docs/design/signing-route.md, раздел 8).
// Только серверный режим: локальная Студия отвечает 404. Контракт раздела 8 и уточнения 12.9;
// эталоны тел лежат в contracts/server/fixtures. strictObject повторяет extra=forbid моделей
// api/schemas/signing_route.py: лишнее поле значит расхождение сторон.
// Все поля приходят явно, пустое значение это null.
//
// Необязательные подписи и пропуск (раздел 13.6): слот маршрута различает `extra` (добавлен сверх
// точки) и `optional` (подпись необязательна); поля участника и задачи обязательны.
//
// Дата подписания (раздел 14.7): у слотов задачи метки даты `dates` (место рамки и текст), поле
// обязательно (срез R23).

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

/**
 * Причина остановки. `rebuilt` больше не появляется (раздел 12.5): маршрут подписывает версию на
 * подписи, а пересборка его не трогает; значение остаётся у маршрутов, остановленных на 0.20.0.
 * `sent_changed`: версия на подписи другая или удалена мимо маршрута (git, восстановление) или
 * её не удалось восстановить при переносе маршрута 0.20.0 (12.11).
 */
export const SigningStopReasonSchema = z.enum([
  "rebuilt",
  "sent_changed",
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
  /** Автор маршрута пропустил участника: все его оставшиеся подписи на точке необязательны (13.3). */
  "skipped",
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
  /** Пара пропущена вместе с участником: подпись не требуется (13.3). */
  "skipped",
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
  "skipped",
  /** Автор изменил метки даты на документе под маршрутом (14.6): `who` автор. */
  "marks_edited",
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
  /**
   * Только у `sent` новой версии (12.6): документы, у которых сменилась версия на подписи;
   * остальные документы маршрута остались прежними. null у остальных событий и у первой отправки.
   */
  changed_docs: z.array(z.string()).nullable(),
});
export type RouteEvent = z.infer<typeof RouteEventSchema>;

// Ход маршрута глазами автора: GET/POST/PUT .../signing-routes[/{route_id}], send, cancel, archive.

/**
 * Почему участника нельзя пропустить (13.6): `not_turn` не его очередь, `required_slots` есть
 * обязательные пары, `no_slots` согласующий без подписей, `done` уже закончил или пропущен.
 */
export const RouteSkipBlockerSchema = z.enum([
  "not_turn",
  "required_slots",
  "no_slots",
  "done",
]);
export type RouteSkipBlocker = z.infer<typeof RouteSkipBlockerSchema>;

/**
 * Можно ли пропустить участника сейчас (`POST .../participants/{pid}/skip`). `keeps_marks`
 * документы, где его метка уже в зафиксированном PDF с ЭП над ним и останется; `refreezes`
 * документы, которые маршрут зафиксирует заново без его метки.
 */
export const RouteSkipSchema = z.strictObject({
  available: z.boolean(),
  blocker: RouteSkipBlockerSchema.nullable(),
  keeps_marks: z.array(z.string()),
  refreezes: z.array(z.string()),
});
export type RouteSkip = z.infer<typeof RouteSkipSchema>;

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
  /** Когда пропущен в этом раунде; null, если не пропущен. */
  skipped_at: iso.nullable(),
  /**
   * Пропуск (13.6): только тому, кто управляет маршрутом, и только у идущего маршрута; иначе
   * null.
   */
  skip: RouteSkipSchema.nullable(),
});
export type RouteParticipant = z.infer<typeof RouteParticipantSchema>;

export const RouteDocSlotSchema = z.strictObject({
  slot_id: z.string(),
  label: LocalizedSchema,
  participant_id: z.string().nullable(),
  /** Слот добавлен к маршруту сверх точки: точка его не требует, автор включил сам (6.5). */
  extra: z.boolean(),
  /** Подпись необязательна на точке маршрута: автор может пропустить подписанта (13.3). */
  optional: z.boolean(),
  status: RouteSlotStatusSchema,
  /**
   * Кто добавил слот сверх точки (15.11): `pack` шаблон, `author` автор; null у пары точки.
   * Пока необязательно: пометки по нему делает W15.
   */
  added_by: z.enum(["pack", "author"]).nullable().optional(),
  /** Пресет точки отмечает подпись необязательной: галочка «по шаблону» (15.7). */
  preset_optional: z.boolean().optional(),
});

export type RouteDocSlot = z.infer<typeof RouteDocSlotSchema>;

/**
 * Версия на подписи документа (раздел 12.3): копия собранного PDF, снятая при отправке. Её видят
 * подписанты, её фиксирует маршрут. `at` время снятия: у документа без изменений новая версия
 * маршрута его не меняет; `round` раунд, который её снял.
 */
export const RouteDocVersionSchema = z.strictObject({
  sha256: z.string().min(1),
  at: iso,
  round: z.number().int().min(1),
});
export type RouteDocVersion = z.infer<typeof RouteDocVersionSchema>;

export const RouteDocSchema = z.strictObject({
  doc_id: z.string(),
  name: LocalizedSchema,
  frozen: z.boolean(),
  slots: z.array(RouteDocSlotSchema),
  /**
   * Версия на подписи; null у черновика, после отмены и у маршрута 0.20.0, версию которого
   * перенос не восстановил (тогда маршрут стоит с `sent_changed`).
   */
  sent: RouteDocVersionSchema.nullable(),
  /**
   * Рабочая сборка отличается от отправленной: от версии на подписи, а без неё (маршрут 0.20.0)
   * от отпечатка снимка. Несобранные правки не считаются; у черновика и отменённого false.
   */
  changed: z.boolean(),
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

/** Условие слота сверх точки из шаблона (`when`, 15.3): человек указан и, если задана роль, с ней. */
export const RoutePresetConditionSchema = z.strictObject({
  person: z.enum(["supervisor", "co_supervisor", "academic_supervisor"]),
  role: z.enum(["university", "company"]).nullable(),
});

export const RoutePresetSlotSchema = z.strictObject({
  doc_id: z.string(),
  slot_id: z.string(),
  when: RoutePresetConditionSchema.nullable(),
});

/**
 * Пресет точки для проекта сейчас (15.11): шаги персонами, слоты сверх точки, отметки «необязательна»,
 * слоты, которые шаблон не добавил по условию, и чем маршрут отличается (`differs`, пусто: как в шаблоне).
 */
export const RoutePresetSchema = z.strictObject({
  version: z.string(),
  /**
   * Версия шаблона, по пресету которой собран состав маршрута; null: не по пресету. Отличается от
   * `version` после обновления шаблона: «В новой версии шаблона другой маршрут этой точки» (15.7).
   */
  base_version: z.string().nullable(),
  steps: z.array(z.array(z.string())),
  extra_slots: z.array(RoutePresetSlotSchema),
  optional: z.array(RouteSlotRefSchema),
  skipped_by_condition: z.array(
    z.strictObject({
      doc_id: z.string(),
      slot_id: z.string(),
      when: RoutePresetConditionSchema,
    }),
  ),
  differs: z.array(z.enum(["order", "slots", "optional"])),
});
export type RoutePreset = z.infer<typeof RoutePresetSchema>;

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
  /** Документы с `changed`, по порядку `docs`: есть что отправить новой версией (12.6). */
  changed_docs: z.array(z.string()),
  /**
   * Пресет точки (15.11): только тому, кто управляет маршрутом, у маршрута, который можно править,
   * если шаблон его задаёт; иначе null. Пока необязательно: интерфейс делает W15.
   */
  preset: RoutePresetSchema.nullable().optional(),
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
  /**
   * Документы маршрута: по ним мягкое предупреждение правки (12.7) узнаёт документы на
   * подписании одним запросом на проект.
   */
  docs: z.array(z.string()),
  /** Документы, рабочая сборка которых ушла от версии на подписи. */
  changed_docs: z.array(z.string()),
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

/**
 * Документ кандидата против версии на подписи (12.6): `same` версия остаётся вместе с B и
 * подписями над ним, `changed` снимается новая, `new` прежней версии нет (первая отправка,
 * после отмены, маршрут 0.20.0 без перенесённой версии).
 */
export const RouteDocChangeSchema = z.enum(["same", "changed", "new"]);
export type RouteDocChange = z.infer<typeof RouteDocChangeSchema>;

export const SigningRoutePreviewDocSchema = z.strictObject({
  doc_id: z.string(),
  name: LocalizedSchema,
  built: z.boolean(),
  /**
   * `build:<sha>` кандидата: что вернуть в `expected` отправки. У несобранного документа с
   * версией на подписи её отпечаток; null, если нет ни сборки, ни версии.
   */
  token: z.string().nullable(),
  change: RouteDocChangeSchema,
  /** Нынешняя версия на подписи; null, если её нет. */
  sent: RouteDocVersionSchema.nullable(),
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
  /**
   * Согласие участника переносится в новый раунд: его отпечатки совпали с кандидатом по всем
   * его документам (у согласующего без слотов по всем документам маршрута). false, если он ещё
   * не согласовывал.
   */
  keeps_approval: z.boolean(),
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
  /**
   * «Что изменилось» (12.6): заменяет сообщение маршрута и уходит подписантам с запросом.
   * Можно не передавать; пустое клиент не шлёт, сервер обрезает пробелы и пустое считает null.
   */
  note: z.string().max(SIGNING_TEXT_MAX).nullable().optional(),
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
  /** Раунд новой версии, в которой изменился хотя бы один документ участника (12.6). */
  new_version: z.boolean(),
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
  /**
   * Все оставшиеся пары участника необязательны на точке: автор может его пропустить (13.6).
   */
  optional: z.boolean(),
});
export type SigningTaskMe = z.infer<typeof SigningTaskMeSchema>;

/**
 * Метка даты слота на документе задачи (14.7): место рамки и текст сейчас; null, пока у слота нет
 * даты (не согласовал). Страница подписи рисует рамки своих меток «Дата согласования».
 */
export const SigningTaskDateMarkSchema = z.strictObject({
  page: z.number().int().min(1),
  x_mm: z.number(),
  y_mm: z.number(),
  width_mm: z.number(),
  height_mm: z.number(),
  text: z.string().nullable(),
});
export type SigningTaskDateMark = z.infer<typeof SigningTaskDateMarkSchema>;

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
  /** Метки даты слота на этом документе (14.7). */
  dates: z.array(SigningTaskDateMarkSchema),
});
export type SigningTaskOtherSlot = z.infer<typeof SigningTaskOtherSlotSchema>;

/** Свой слот: ещё и причина плана. */
export const SigningTaskSlotSchema = z.strictObject({
  ...SigningTaskOtherSlotSchema.shape,
  /** Причина плана (`PlanReason`, в том числе `awaiting_approval`); null у подписанного. */
  reason: z.string().nullable(),
  /** Подпись необязательна на точке: пометка «необязательна» (13.9). */
  optional: z.boolean(),
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
  /** Дата версии на подписи: «Вы подписываете версию от …»; null, если версии нет. */
  sent_at: iso.nullable(),
  /** Документ изменился с прошлого согласия участника: согласовать заново (12.2). */
  changed_since_mine: z.boolean(),
  /**
   * Рабочая сборка ушла от версии на подписи. Видят автор и управляющие маршрутом, у
   * остальных null: подписант рабочих правок не видит.
   */
  changed: z.boolean().nullable(),
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
 * 409 `nothing_changed`: отправка идущего или завершённого маршрута без изменений (12.6).
 * Необязательные подписи и пропуск (13.6): 409 `participant_not_skippable` (с `reason`),
 * `optional_forbidden`, `slot_signed`; 400 `unknown_slot`.
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
  "nothing_changed",
  "participant_not_skippable",
  "optional_forbidden",
  "slot_signed",
  "unknown_slot",
] as const;
export type SigningRouteErrorCode = (typeof SIGNING_ROUTE_ERROR_CODES)[number];

/**
 * Каталоги contracts/server/fixtures маршрута подписания -> схема; те же пары есть в
 * CONTRACT_SCHEMAS. Эталоны версии на подписи (12.9) лежат там же: SigningRoute (diverged,
 * new_version, completed_changed, migration_lost), SigningRouteList/changed,
 * SigningRoutePreview/new_version, SendSigningRouteRequest/new_version, SigningTask/new_version,
 * Notification (signing_request_new_version, signing_new_version). Локальная копия для тестов
 * и галерей: testing/fixtures, SIGNING_ROUTE_CONTRACT_EXAMPLES.
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
