import type {
  ApproveSigningTaskRequest,
  CreateSigningRouteRequest,
  ReturnSigningTaskRequest,
  RouteDocVersion,
  RouteEvent,
  RouteDocSlot,
  RouteParticipant,
  RouteSkip,
  RouteSkipBlocker,
  SendSigningRouteRequest,
  SetSigningTaskPlateRequest,
  SignSigningTaskRequest,
  SigningLink,
  SigningReminder,
  SigningRoute,
  SigningRouteList,
  SigningRoutePreview,
  SigningRouteSummary,
  SigningTask,
  SigningTaskList,
  SigningTaskSummary,
  UpdateSigningRouteRequest,
} from "../model/signingRoute.schema";

// Данные для тестов и галерей по образцу эталонов contracts/server: «Заявка на тему КП»,
// автор картинкой, научрук открепленной ЭП, шаг 2 из 2. Все поля явно, как в контракте.

export const SR_PROJECT_ID = "p_01hxa1c4de";
export const SR_ROUTE_ID = "sr_01hy2b7k9q";
export const SR_PROFILE = {
  id: "topic-approval",
  name: { ru: "Заявка на тему КП", en: "Course project topic application" },
};
export const SR_DOC = {
  doc_id: "topic_application",
  name: { ru: "Заявление о выборе темы", en: "Topic selection application" },
};
export const SR_AUTHOR = { id: "u_01hx7k5ivan", name: "Иванов И. И." };
export const SR_SUPERVISOR = { id: "u_01hx7k5petr", name: "Петров П. П." };
/** Второй документ для новой версии (12.6): научрук подписывает оба, меняется один. */
export const SR_REVIEW_DOC = {
  doc_id: "supervisor_review",
  name: { ru: "Отзыв руководителя", en: "Supervisor's review" },
};

const BUILD_SHA = "3f".repeat(32);
/** Рабочая сборка после правки: ушла от версии на подписи. */
const WORKING_SHA = "a7".repeat(32);
const REVIEW_SHA = "5e".repeat(32);
const SENT_AT = "2026-11-10T09:00:00Z";
const NEW_VERSION_AT = "2026-11-12T10:30:00Z";

/** Версия на подписи (12.3), снятая первой отправкой. */
export const makeRouteDocVersion = (
  overrides: Partial<RouteDocVersion> = {},
): RouteDocVersion => ({
  sha256: BUILD_SHA,
  at: SENT_AT,
  round: 1,
  ...overrides,
});

export const makeRouteEvent = (
  overrides: Partial<RouteEvent> = {},
): RouteEvent => ({
  id: "sre_01",
  kind: "sent",
  round: 1,
  at: "2026-11-10T09:00:00Z",
  who: SR_AUTHOR.name,
  participant_id: null,
  comment: null,
  reason: null,
  changed_docs: null,
  ...overrides,
});

export const makeRouteParticipant = (
  overrides: Partial<RouteParticipant> = {},
): RouteParticipant => ({
  id: "srp_author",
  persona: "author",
  user_id: SR_AUTHOR.id,
  invitation_id: null,
  name: SR_AUTHOR.name,
  membership: "member",
  card_name: SR_AUTHOR.name,
  assignments: [{ doc_id: SR_DOC.doc_id, slot_id: "author" }],
  method: "image",
  state: "done",
  next_action: "done",
  changes_visible: false,
  approved_at: "2026-11-10T09:00:00Z",
  notified_at: null,
  reminded_at: null,
  reminders: 0,
  skipped_at: null,
  skip: null,
  ...overrides,
});

/** Пропуск глазами автора маршрута (13.6): blocker null значит «можно пропустить». */
export const makeRouteSkip = (
  blocker: RouteSkipBlocker | null,
  docs: { keeps_marks?: string[]; refreezes?: string[] } = {},
): RouteSkip => ({
  available: blocker === null,
  blocker,
  keeps_marks: docs.keeps_marks ?? [],
  refreezes: docs.refreezes ?? [],
});

const supervisor = (overrides: Partial<RouteParticipant> = {}) =>
  makeRouteParticipant({
    id: "srp_supervisor",
    persona: "supervisor",
    user_id: SR_SUPERVISOR.id,
    name: SR_SUPERVISOR.name,
    card_name: SR_SUPERVISOR.name,
    assignments: [{ doc_id: SR_DOC.doc_id, slot_id: "supervisor" }],
    method: "detached",
    state: "to_approve_sign",
    next_action: "approve_and_sign",
    approved_at: null,
    notified_at: "2026-11-10T09:00:00Z",
    ...overrides,
  });

export const makeSigningRoute = (
  overrides: Partial<SigningRoute> = {},
): SigningRoute => ({
  id: SR_ROUTE_ID,
  project_id: SR_PROJECT_ID,
  profile: SR_PROFILE,
  status: "active",
  phase: "signing",
  round: 1,
  current_step: 2,
  deadline: "2026-11-15T20:59:00Z",
  message: "Прошу подписать заявление до пятницы.",
  stop_reason: null,
  sent_by: SR_AUTHOR,
  sent_at: "2026-11-10T09:00:00Z",
  completed_at: null,
  created_at: "2026-11-10T08:40:00Z",
  updated_at: "2026-11-10T09:00:00Z",
  docs: [
    {
      ...SR_DOC,
      frozen: true,
      slots: [
        {
          slot_id: "author",
          label: { ru: "Студент", en: "Student" },
          participant_id: "srp_author",
          extra: false,
          optional: false,
          status: "signed",
        },
        {
          slot_id: "supervisor",
          label: { ru: "Научный руководитель", en: "Supervisor" },
          participant_id: "srp_supervisor",
          extra: false,
          optional: false,
          status: "pending",
        },
      ],
      sent: makeRouteDocVersion(),
      changed: false,
    },
  ],
  // Автор видит пропуск у каждого: сам закончил, у научрука подпись обязательна.
  steps: [
    [makeRouteParticipant({ skip: makeRouteSkip("done") })],
    [supervisor({ skip: makeRouteSkip("required_slots") })],
  ],
  events: [
    makeRouteEvent(),
    makeRouteEvent({ id: "sre_02", kind: "frozen", who: null }),
  ],
  candidates: [
    {
      persona: "author",
      people: [{ kind: "member", id: SR_AUTHOR.id, name: SR_AUTHOR.name }],
    },
    {
      persona: "supervisor",
      people: [
        { kind: "member", id: SR_SUPERVISOR.id, name: SR_SUPERVISOR.name },
        { kind: "invitation", id: "inv_01hx9", name: "s***@hse.ru" },
      ],
    },
  ],
  changed_docs: [],
  ...overrides,
});

export const makeSigningRouteSummary = (
  overrides: Partial<SigningRouteSummary> = {},
): SigningRouteSummary => ({
  id: SR_ROUTE_ID,
  profile: SR_PROFILE,
  status: "active",
  phase: "signing",
  round: 1,
  current_step: 2,
  steps_total: 2,
  deadline: "2026-11-15T20:59:00Z",
  stop_reason: null,
  sent_at: "2026-11-10T09:00:00Z",
  completed_at: null,
  updated_at: "2026-11-10T09:00:00Z",
  waiting_for: [{ name: SR_SUPERVISOR.name, persona: "supervisor" }],
  docs: [SR_DOC.doc_id],
  changed_docs: [],
  ...overrides,
});

export const makeSigningRoutePreview = (
  overrides: Partial<SigningRoutePreview> = {},
): SigningRoutePreview => ({
  route_id: SR_ROUTE_ID,
  can_send: true,
  can_send_and_sign: false,
  visual_step: 0,
  docs: [
    {
      ...SR_DOC,
      built: true,
      token: `build:${BUILD_SHA}`,
      change: "new",
      sent: null,
    },
  ],
  participants: [
    {
      participant_id: "srp_author",
      step: 1,
      persona: "author",
      name: SR_AUTHOR.name,
      membership: "member",
      method: "image",
      methods: ["image", "detached"],
      chooses_method: false,
      image_ready: true,
      plate_ready: false,
      actions: 0,
      keeps_approval: false,
    },
    {
      participant_id: "srp_supervisor",
      step: 2,
      persona: "supervisor",
      name: SR_SUPERVISOR.name,
      membership: "member",
      method: "detached",
      methods: ["image", "detached"],
      chooses_method: false,
      image_ready: false,
      plate_ready: true,
      actions: 1,
      keeps_approval: false,
    },
  ],
  blockers: [],
  sender_key: null,
  ...overrides,
});

export const makeSigningTask = (
  overrides: Partial<SigningTask> = {},
): SigningTask => ({
  route: {
    id: SR_ROUTE_ID,
    project: { id: SR_PROJECT_ID, name: "Bertie: курсовой проект" },
    profile: SR_PROFILE,
    status: "active",
    phase: "signing",
    round: 1,
    current_step: 2,
    deadline: "2026-11-15T20:59:00Z",
    message: "Прошу подписать заявление до пятницы.",
    sender: SR_AUTHOR.name,
    sent_at: "2026-11-10T09:00:00Z",
    stop_reason: null,
    new_version: false,
  },
  steps: [
    [
      {
        name: SR_AUTHOR.name,
        persona: "author",
        state: "done",
        at: "2026-11-10T09:00:00Z",
        me: false,
        card_name: null,
        changes_visible: false,
      },
    ],
    [
      {
        name: SR_SUPERVISOR.name,
        persona: "supervisor",
        state: "to_approve_sign",
        at: null,
        me: true,
        card_name: null,
        changes_visible: false,
      },
    ],
  ],
  me: {
    participant_id: "srp_supervisor",
    state: "to_approve_sign",
    next_action: "approve_and_sign",
    methods: ["detached"],
    method: "detached",
    image_ready: false,
    image_url: null,
    plate: {
      owner: SR_SUPERVISOR.name,
      kind: "openpgp",
      cert_id: "1A2B 3C4D 5E6F 7A8B",
    },
    keys: { server_keys_allowed: false, default_key: null },
    optional: false,
  },
  docs: [
    {
      ...SR_DOC,
      pdf_url: `/api/v1/projects/${SR_PROJECT_ID}/docs/${SR_DOC.doc_id}/frozen/pdf`,
      frozen: true,
      token: `pdf:${"9c".repeat(32)}`,
      mine: [
        {
          slot_id: "supervisor",
          label: { ru: "Научный руководитель", en: "Supervisor" },
          page: 1,
          x_mm: 110,
          y_mm: 130,
          width_mm: 40,
          height_mm: 22,
          mark: "plate",
          dates: [],
          status: "pending",
          reason: "no_signature_file",
          optional: false,
        },
      ],
      others: [
        {
          slot_id: "author",
          label: { ru: "Студент", en: "Student" },
          page: 1,
          x_mm: 160,
          y_mm: 208,
          width_mm: 30,
          height_mm: 12,
          mark: "png",
          dates: [],
          status: "signed",
        },
      ],
      sent_at: SENT_AT,
      changed_since_mine: false,
      changed: null,
    },
  ],
  events: [makeRouteEvent()],
  ...overrides,
});

export const makeSigningTaskSummary = (
  overrides: Partial<SigningTaskSummary> = {},
): SigningTaskSummary => ({
  project: { id: SR_PROJECT_ID, name: "Bertie: курсовой проект" },
  route_id: SR_ROUTE_ID,
  profile: SR_PROFILE,
  round: 1,
  sender: SR_AUTHOR.name,
  deadline: "2026-11-15T20:59:00Z",
  next_action: "approve_and_sign",
  since: "2026-11-10T09:00:00Z",
  ...overrides,
});

// Версия на подписи (раздел 12): маршрут подписывает снимок PDF, снятый при отправке.

const SUPERVISOR_LABEL = { ru: "Научный руководитель", en: "Supervisor" };
const ACADEMIC_LABEL = {
  ru: "Академический руководитель",
  en: "Academic supervisor",
};

/** Рабочая сборка заявления ушла вперёд, маршрут идёт дальше: подписанты ничего не замечают. */
const divergedRoute = makeSigningRoute({
  docs: makeSigningRoute().docs.map((doc) => ({
    ...doc,
    changed: true,
  })),
  changed_docs: [SR_DOC.doc_id],
});

const academic = (overrides: Partial<RouteParticipant> = {}) =>
  makeRouteParticipant({
    id: "srp_academic",
    persona: "academic_supervisor",
    user_id: "u_01hx7k5sido",
    name: "Сидоров С. С.",
    card_name: "Сидоров С. С.",
    assignments: [
      { doc_id: SR_REVIEW_DOC.doc_id, slot_id: "academic_supervisor" },
    ],
    ...overrides,
  });

/**
 * Новая версия (12.6), раунд 2: изменилось заявление, отзыв нет. Научрук согласует заново только
 * заявление: его ЭП на отзыве осталась, B отзыва тот же. Академрук подписывает только отзыв и
 * остаётся `done`.
 */
const newVersionRoute = makeSigningRoute({
  phase: "approval",
  round: 2,
  current_step: 2,
  sent_at: NEW_VERSION_AT,
  updated_at: NEW_VERSION_AT,
  message: "Исправил формулировку темы.",
  docs: [
    {
      ...SR_DOC,
      frozen: false,
      slots: [
        {
          slot_id: "author",
          label: { ru: "Студент", en: "Student" },
          participant_id: "srp_author",
          extra: false,
          optional: false,
          status: "signed",
        },
        {
          slot_id: "supervisor",
          label: SUPERVISOR_LABEL,
          participant_id: "srp_supervisor",
          extra: false,
          optional: false,
          status: "pending",
        },
      ],
      sent: makeRouteDocVersion({
        sha256: WORKING_SHA,
        at: NEW_VERSION_AT,
        round: 2,
      }),
      changed: false,
    },
    {
      ...SR_REVIEW_DOC,
      frozen: true,
      slots: [
        {
          slot_id: "supervisor",
          label: SUPERVISOR_LABEL,
          participant_id: "srp_supervisor",
          extra: false,
          optional: false,
          status: "signed",
        },
        {
          slot_id: "academic_supervisor",
          label: ACADEMIC_LABEL,
          participant_id: "srp_academic",
          extra: false,
          optional: false,
          status: "signed",
        },
      ],
      sent: makeRouteDocVersion({ sha256: REVIEW_SHA }),
      changed: false,
    },
  ],
  steps: [
    [
      makeRouteParticipant({
        approved_at: NEW_VERSION_AT,
        skip: makeRouteSkip("done"),
      }),
    ],
    [
      supervisor({
        assignments: [
          { doc_id: SR_DOC.doc_id, slot_id: "supervisor" },
          { doc_id: SR_REVIEW_DOC.doc_id, slot_id: "supervisor" },
        ],
        state: "to_approve",
        next_action: "approve",
        changes_visible: true,
        notified_at: NEW_VERSION_AT,
        skip: makeRouteSkip("required_slots"),
      }),
    ],
    [
      academic({
        approved_at: "2026-11-11T15:00:00Z",
        skip: makeRouteSkip("done"),
      }),
    ],
  ],
  events: [
    makeRouteEvent(),
    makeRouteEvent({ id: "sre_02", kind: "frozen", who: null }),
    makeRouteEvent({
      id: "sre_05",
      kind: "sent",
      round: 2,
      at: NEW_VERSION_AT,
      changed_docs: [SR_DOC.doc_id],
    }),
  ],
  changed_docs: [],
});

const SNAPSHOT_ROUTE_EXAMPLES = {
  diverged: divergedRoute,
  new_version: newVersionRoute,
  // Все подписали версию от 10.11, потом правка: «Есть изменения после подписания».
  completed_changed: makeSigningRoute({
    status: "completed",
    phase: "done",
    current_step: null,
    completed_at: "2026-11-11T12:00:00Z",
    docs: divergedRoute.docs.map((doc) => ({
      ...doc,
      slots: doc.slots.map((slot) => ({ ...slot, status: "signed" as const })),
    })),
    steps: [
      [makeRouteParticipant()],
      [
        supervisor({
          state: "done",
          next_action: "done",
          approved_at: "2026-11-11T12:00:00Z",
        }),
      ],
    ],
    changed_docs: [SR_DOC.doc_id],
  }),
  // Маршрут 0.20.0, версию которого перенос не восстановил (12.11): стоит, версии на подписи нет.
  migration_lost: makeSigningRoute({
    status: "paused",
    phase: null,
    current_step: null,
    stop_reason: "sent_changed",
    // Пропуск отдаётся только у идущего маршрута.
    steps: [[makeRouteParticipant()], [supervisor()]],
    docs: divergedRoute.docs.map((doc) => ({
      ...doc,
      frozen: false,
      sent: null,
    })),
    events: [
      makeRouteEvent(),
      makeRouteEvent({
        id: "sre_04",
        kind: "paused",
        at: "2026-11-12T03:00:00Z",
        who: null,
        reason: "sent_changed",
      }),
    ],
    changed_docs: [SR_DOC.doc_id],
  }),
} satisfies Record<string, SigningRoute>;

/** Предпросмотр новой версии: заявление изменилось, отзыв нет; академрук сохраняет согласие. */
const SNAPSHOT_PREVIEW_EXAMPLES = {
  new_version: makeSigningRoutePreview({
    visual_step: 2,
    docs: [
      {
        ...SR_DOC,
        built: true,
        token: `build:${WORKING_SHA}`,
        change: "changed",
        sent: makeRouteDocVersion(),
      },
      {
        ...SR_REVIEW_DOC,
        built: true,
        token: `build:${REVIEW_SHA}`,
        change: "same",
        sent: makeRouteDocVersion({ sha256: REVIEW_SHA }),
      },
    ],
    participants: [
      ...makeSigningRoutePreview().participants,
      {
        participant_id: "srp_academic",
        step: 3,
        persona: "academic_supervisor",
        name: "Сидоров С. С.",
        membership: "member",
        method: "image",
        methods: ["image", "detached"],
        chooses_method: false,
        image_ready: true,
        plate_ready: false,
        actions: 0,
        keeps_approval: true,
      },
    ],
  }),
} satisfies Record<string, SigningRoutePreview>;

/**
 * Задача научрука в раунде новой версии: заявление согласовать заново, отзыв без изменений
 * (его согласие и ЭП остались, отпечатка для действия нет).
 */
const SNAPSHOT_TASK_EXAMPLES = {
  new_version: makeSigningTask({
    route: {
      ...makeSigningTask().route,
      phase: "approval",
      round: 2,
      message: "Исправил формулировку темы.",
      sent_at: NEW_VERSION_AT,
      new_version: true,
    },
    steps: [
      makeSigningTask().steps[0] ?? [],
      [
        {
          name: SR_SUPERVISOR.name,
          persona: "supervisor",
          state: "to_approve",
          at: null,
          me: true,
          card_name: null,
          changes_visible: true,
        },
      ],
      [
        {
          name: "Сидоров С. С.",
          persona: "academic_supervisor",
          state: "done",
          at: "2026-11-11T15:00:00Z",
          me: false,
          card_name: null,
          changes_visible: false,
        },
      ],
    ],
    me: {
      ...makeSigningTask().me,
      state: "to_approve",
      next_action: "approve",
    },
    docs: [
      {
        ...SR_DOC,
        pdf_url: `/api/v1/projects/${SR_PROJECT_ID}/docs/${SR_DOC.doc_id}/pdf/signed`,
        frozen: false,
        token: `build:${WORKING_SHA}`,
        mine: [
          {
            slot_id: "supervisor",
            label: SUPERVISOR_LABEL,
            page: 1,
            x_mm: 110,
            y_mm: 130,
            width_mm: 40,
            height_mm: 22,
            mark: "plate",
            dates: [],
            status: "pending",
            reason: "awaiting_approval",
            optional: false,
          },
        ],
        others: makeSigningTask().docs[0]?.others ?? [],
        sent_at: NEW_VERSION_AT,
        changed_since_mine: true,
        changed: null,
      },
      {
        ...SR_REVIEW_DOC,
        pdf_url: `/api/v1/projects/${SR_PROJECT_ID}/docs/${SR_REVIEW_DOC.doc_id}/frozen/pdf`,
        frozen: true,
        token: null,
        mine: [
          {
            slot_id: "supervisor",
            label: SUPERVISOR_LABEL,
            page: 2,
            x_mm: 110,
            y_mm: 240,
            width_mm: 40,
            height_mm: 22,
            mark: "plate",
            dates: [],
            status: "signed",
            reason: null,
            optional: false,
          },
        ],
        others: [
          {
            slot_id: "academic_supervisor",
            label: ACADEMIC_LABEL,
            page: 2,
            x_mm: 110,
            y_mm: 260,
            width_mm: 40,
            height_mm: 16,
            mark: "png",
            dates: [],
            status: "signed",
          },
        ],
        sent_at: SENT_AT,
        changed_since_mine: false,
        changed: null,
      },
    ],
    events: newVersionRoute.events,
  }),
} satisfies Record<string, SigningTask>;

// Необязательные подписи и пропуск (раздел 13): живой маршрут «Заявка на тему КП». Автор
// картинкой, научрук открепленной ЭП с известными данными плашки, академрук сверх точки
// (`extra`) с отметкой «Подпись необязательна» (`optional`).

const SKIPPED_AT = "2026-11-13T10:00:00Z";
const ACADEMIC_NAME = "Сидоров С. С.";

const academicSlot = (status: RouteDocSlot["status"]): RouteDocSlot => ({
  slot_id: "academic_supervisor",
  label: ACADEMIC_LABEL,
  participant_id: "srp_academic",
  extra: true,
  optional: true,
  status,
});

const optionalDoc = (
  frozen: boolean,
  supervisorSlot: RouteDocSlot["status"],
  academicStatus: RouteDocSlot["status"],
): SigningRoute["docs"][number] => ({
  ...SR_DOC,
  frozen,
  slots: [
    {
      slot_id: "author",
      label: { ru: "Студент", en: "Student" },
      participant_id: "srp_author",
      extra: false,
      optional: false,
      status: "signed",
    },
    {
      slot_id: "supervisor",
      label: SUPERVISOR_LABEL,
      participant_id: "srp_supervisor",
      extra: false,
      optional: false,
      status: supervisorSlot,
    },
    academicSlot(academicStatus),
  ],
  sent: makeRouteDocVersion(),
  changed: false,
});

const optionalAcademic = (overrides: Partial<RouteParticipant> = {}) =>
  academic({
    name: ACADEMIC_NAME,
    card_name: ACADEMIC_NAME,
    assignments: [{ doc_id: SR_DOC.doc_id, slot_id: "academic_supervisor" }],
    approved_at: null,
    ...overrides,
  });

/** Научрук согласовал до фиксации и ждёт её: его ЭП после фиксации. */
const approvedSupervisor = (overrides: Partial<RouteParticipant> = {}) =>
  supervisor({
    state: "waiting",
    next_action: "wait",
    approved_at: "2026-11-11T12:00:00Z",
    skip: makeRouteSkip("not_turn"),
    ...overrides,
  });

const optionalEvents = [
  makeRouteEvent(),
  makeRouteEvent({
    id: "sre_06",
    kind: "approved",
    at: "2026-11-11T12:00:00Z",
    who: SR_SUPERVISOR.name,
    participant_id: "srp_supervisor",
  }),
];

const skippedEvents = [
  ...optionalEvents,
  makeRouteEvent({
    id: "sre_07",
    kind: "skipped",
    at: SKIPPED_AT,
    who: SR_AUTHOR.name,
    participant_id: "srp_academic",
  }),
  makeRouteEvent({ id: "sre_08", kind: "frozen", at: SKIPPED_AT, who: null }),
];

/** Очередь академрука, все его подписи необязательны: автор видит «Пропустить». */
const skippableRoute = makeSigningRoute({
  phase: "approval",
  current_step: 3,
  docs: [optionalDoc(false, "pending", "pending")],
  steps: [
    [makeRouteParticipant({ skip: makeRouteSkip("done") })],
    [approvedSupervisor()],
    [
      optionalAcademic({
        state: "to_approve",
        next_action: "approve",
        changes_visible: true,
        notified_at: "2026-11-11T12:00:00Z",
        skip: makeRouteSkip(null),
      }),
    ],
  ],
  events: optionalEvents,
});

const OPTIONAL_ROUTE_EXAMPLES = {
  skippable: skippableRoute,
  // Фаза подписи: плашка академрука уже в B, ЭП над ним нет; пропуск зафиксирует его заново.
  skippable_refreezes: makeSigningRoute({
    phase: "signing",
    current_step: 3,
    docs: [optionalDoc(true, "pending", "pending")],
    steps: [
      [makeRouteParticipant({ skip: makeRouteSkip("done") })],
      [
        supervisor({
          state: "to_sign",
          next_action: "sign",
          approved_at: "2026-11-11T12:00:00Z",
          skip: makeRouteSkip("required_slots"),
        }),
      ],
      [
        optionalAcademic({
          method: "detached",
          state: "to_approve_sign",
          next_action: "approve_and_sign",
          notified_at: "2026-11-11T12:00:00Z",
          skip: makeRouteSkip(null, { refreezes: [SR_DOC.doc_id] }),
        }),
      ],
    ],
    events: [
      ...optionalEvents,
      makeRouteEvent({ id: "sre_08", kind: "frozen", who: null }),
    ],
  }),
  // Над B уже ЭП научрука: плашка академрука останется в нём.
  skippable_keeps_marks: makeSigningRoute({
    phase: "signing",
    current_step: 3,
    docs: [optionalDoc(true, "signed", "pending")],
    steps: [
      [makeRouteParticipant({ skip: makeRouteSkip("done") })],
      [
        supervisor({
          state: "done",
          next_action: "done",
          approved_at: "2026-11-11T12:00:00Z",
          skip: makeRouteSkip("done"),
        }),
      ],
      [
        optionalAcademic({
          method: "detached",
          state: "to_approve_sign",
          next_action: "approve_and_sign",
          notified_at: "2026-11-11T12:00:00Z",
          skip: makeRouteSkip(null, { keeps_marks: [SR_DOC.doc_id] }),
        }),
      ],
    ],
    events: [
      ...optionalEvents,
      makeRouteEvent({ id: "sre_08", kind: "frozen", who: null }),
    ],
  }),
  // Академрук пропущен: маршрут зафиксировал заявление и ждёт ЭП научрука.
  skipped: makeSigningRoute({
    phase: "signing",
    current_step: 2,
    updated_at: SKIPPED_AT,
    docs: [optionalDoc(true, "pending", "skipped")],
    steps: [
      [makeRouteParticipant({ skip: makeRouteSkip("done") })],
      [
        supervisor({
          state: "to_sign",
          next_action: "sign",
          approved_at: "2026-11-11T12:00:00Z",
          notified_at: SKIPPED_AT,
          skip: makeRouteSkip("required_slots"),
        }),
      ],
      [
        optionalAcademic({
          state: "skipped",
          next_action: "done",
          notified_at: "2026-11-11T12:00:00Z",
          skipped_at: SKIPPED_AT,
          skip: makeRouteSkip("done"),
        }),
      ],
    ],
    events: skippedEvents,
  }),
  // Пропущен после ЭП научрука над B: плашка осталась, маршрут завершён.
  skipped_kept_mark: makeSigningRoute({
    status: "completed",
    phase: "done",
    current_step: null,
    updated_at: SKIPPED_AT,
    completed_at: SKIPPED_AT,
    docs: [optionalDoc(true, "signed", "skipped")],
    steps: [
      [makeRouteParticipant()],
      [
        supervisor({
          state: "done",
          next_action: "done",
          approved_at: "2026-11-11T12:00:00Z",
        }),
      ],
      [
        optionalAcademic({
          method: "detached",
          state: "skipped",
          next_action: "done",
          notified_at: "2026-11-11T12:00:00Z",
          skipped_at: SKIPPED_AT,
        }),
      ],
    ],
    events: [
      ...optionalEvents,
      makeRouteEvent({ id: "sre_08", kind: "frozen", who: null }),
      makeRouteEvent({
        id: "sre_09",
        kind: "signed",
        at: "2026-11-12T09:00:00Z",
        who: SR_SUPERVISOR.name,
        participant_id: "srp_supervisor",
      }),
      makeRouteEvent({
        id: "sre_10",
        kind: "skipped",
        at: SKIPPED_AT,
        who: SR_AUTHOR.name,
        participant_id: "srp_academic",
      }),
      makeRouteEvent({
        id: "sre_11",
        kind: "completed",
        at: SKIPPED_AT,
        who: null,
      }),
    ],
  }),
} satisfies Record<string, SigningRoute>;

/** Задача академрука: его место на заявлении необязательно. */
const optionalTask = (
  me: Partial<SigningTask["me"]>,
  status: RouteDocSlot["status"],
): SigningTask =>
  makeSigningTask({
    route: { ...makeSigningTask().route, phase: "approval", current_step: 3 },
    steps: [
      makeSigningTask().steps[0] ?? [],
      [
        {
          name: SR_SUPERVISOR.name,
          persona: "supervisor",
          state: "waiting",
          at: "2026-11-11T12:00:00Z",
          me: false,
          card_name: null,
          changes_visible: false,
        },
      ],
      [
        {
          name: ACADEMIC_NAME,
          persona: "academic_supervisor",
          state: me.state ?? "to_approve",
          at: null,
          me: true,
          card_name: null,
          changes_visible: status === "pending",
        },
      ],
    ],
    me: {
      participant_id: "srp_academic",
      state: "to_approve",
      next_action: "approve",
      methods: ["image", "detached"],
      method: "image",
      image_ready: true,
      image_url: `/api/v1/projects/${SR_PROJECT_ID}/signing-routes/${SR_ROUTE_ID}/task/image`,
      plate: null,
      keys: { server_keys_allowed: false, default_key: null },
      optional: true,
      ...me,
    },
    docs: [
      {
        ...SR_DOC,
        pdf_url: `/api/v1/projects/${SR_PROJECT_ID}/docs/${SR_DOC.doc_id}/pdf/signed`,
        frozen: false,
        token: status === "pending" ? `build:${BUILD_SHA}` : null,
        mine: [
          {
            slot_id: "academic_supervisor",
            label: ACADEMIC_LABEL,
            page: 1,
            x_mm: 110,
            y_mm: 160,
            width_mm: 40,
            height_mm: 16,
            mark: "png",
            dates: [],
            status,
            reason: status === "pending" ? "awaiting_approval" : null,
            optional: true,
          },
        ],
        others: makeSigningTask().docs[0]?.others ?? [],
        sent_at: SENT_AT,
        changed_since_mine: false,
        changed: null,
      },
    ],
    events: status === "skipped" ? skippedEvents : optionalEvents,
  });

const OPTIONAL_TASK_EXAMPLES = {
  optional: optionalTask({}, "pending"),
  // Пропущен: «Ваша подпись не требуется», действий нет.
  skipped: optionalTask(
    {
      state: "skipped",
      next_action: "done",
      methods: [],
      optional: false,
    },
    "skipped",
  ),
} satisfies Record<string, SigningTask>;

/** Научрук картинкой до фиксации, с метками даты у своего места и у автора (эталон `dates`). */
const datesTask = (): SigningTask => {
  const task = makeSigningTask({
    route: { ...makeSigningTask().route, phase: "approval" },
  });
  const [doc] = task.docs;
  if (!doc) return task;
  const empty = { width_mm: 7, height_mm: 5, text: null };
  return {
    ...task,
    docs: [
      {
        ...doc,
        frozen: false,
        token: `build:${BUILD_SHA}`,
        mine: doc.mine.map((slot) => ({
          ...slot,
          status: "pending" as const,
          reason: "awaiting_approval",
          dates: [
            { page: 1, x_mm: 114, y_mm: 150, ...empty },
            { page: 1, x_mm: 126, y_mm: 150, ...empty, width_mm: 24 },
            { page: 1, x_mm: 156, y_mm: 150, ...empty, width_mm: 6 },
          ],
        })),
        others: doc.others.map((slot) => ({
          ...slot,
          dates: [
            {
              page: 1,
              x_mm: slot.x_mm,
              y_mm: slot.y_mm + 14,
              width_mm: 26,
              height_mm: 5,
              text: "10.11.2026",
            },
          ],
        })),
      },
    ],
  };
};

/**
 * Эталоны тел по каталогам contracts/server/fixtures/<Схема>/<вариант>.json.
 * Ключи совпадают с SIGNING_ROUTE_CONTRACT_SCHEMAS.
 */
export const SIGNING_ROUTE_CONTRACT_EXAMPLES: Record<
  string,
  Record<string, unknown>
> = {
  SigningRoute: {
    signing: makeSigningRoute(),
    draft: makeSigningRoute({
      status: "draft",
      phase: null,
      round: 0,
      current_step: null,
      deadline: null,
      message: null,
      sent_by: null,
      sent_at: null,
      docs: [
        {
          ...SR_DOC,
          frozen: false,
          slots: [
            {
              slot_id: "author",
              label: { ru: "Студент", en: "Student" },
              participant_id: "srp_author",
              extra: false,
              optional: false,
              status: "pending",
            },
            {
              slot_id: "academic_supervisor",
              label: {
                ru: "Академический руководитель",
                en: "Academic supervisor",
              },
              participant_id: "srp_academic",
              extra: true,
              optional: false,
              status: "pending",
            },
          ],
          sent: null,
          changed: false,
        },
      ],
      steps: [
        [
          makeRouteParticipant({
            state: "waiting",
            next_action: "wait",
            approved_at: null,
          }),
        ],
        [
          makeRouteParticipant({
            id: "srp_academic",
            persona: "academic_supervisor",
            user_id: null,
            name: null,
            membership: "missing",
            assignments: [
              { doc_id: SR_DOC.doc_id, slot_id: "academic_supervisor" },
            ],
            state: "waiting",
            next_action: "wait",
            approved_at: null,
          }),
        ],
      ],
      events: [],
      candidates: [
        {
          persona: "author",
          people: [{ kind: "member", id: SR_AUTHOR.id, name: SR_AUTHOR.name }],
        },
        { persona: "academic_supervisor", people: [] },
        {
          persona: "supervisor",
          people: [
            { kind: "member", id: SR_SUPERVISOR.id, name: SR_SUPERVISOR.name },
          ],
        },
      ],
    }),
    returned: makeSigningRoute({
      status: "returned",
      phase: null,
      current_step: null,
      stop_reason: "returned",
      steps: [
        [makeRouteParticipant()],
        [
          supervisor({
            state: "returned",
            next_action: "wait",
          }),
        ],
      ],
      events: [
        makeRouteEvent(),
        makeRouteEvent({
          id: "sre_03",
          kind: "returned",
          at: "2026-11-11T12:00:00Z",
          who: SR_SUPERVISOR.name,
          participant_id: "srp_supervisor",
          comment: "Уточните цель проекта",
          reason: "returned",
        }),
      ],
    }),
    ...SNAPSHOT_ROUTE_EXAMPLES,
    ...OPTIONAL_ROUTE_EXAMPLES,
  },
  SigningRouteList: {
    active: { items: [makeSigningRouteSummary()] } satisfies SigningRouteList,
    // Рабочая сборка ушла от версии на подписи: сводка называет документы маршрута и изменившиеся.
    changed: {
      items: [makeSigningRouteSummary({ changed_docs: [SR_DOC.doc_id] })],
    } satisfies SigningRouteList,
    empty: { items: [] } satisfies SigningRouteList,
  },
  CreateSigningRouteRequest: {
    ok: { profile_id: SR_PROFILE.id } satisfies CreateSigningRouteRequest,
  },
  UpdateSigningRouteRequest: {
    ok: {
      steps: [
        [
          {
            id: "srp_author",
            persona: "author",
            user_id: SR_AUTHOR.id,
            invitation_id: null,
          },
        ],
        [
          {
            id: null,
            persona: "supervisor",
            user_id: null,
            invitation_id: "pinv_01hx9",
          },
        ],
      ],
      extra_slots: [{ doc_id: SR_DOC.doc_id, slot_id: "academic_supervisor" }],
      deadline: "2026-11-15T20:59:00Z",
      message: null,
    } satisfies UpdateSigningRouteRequest,
  },
  SigningRoutePreview: {
    ready: makeSigningRoutePreview(),
    blocked: makeSigningRoutePreview({
      can_send: false,
      visual_step: 2,
      blockers: [
        {
          code: "participant_missing",
          doc_id: null,
          slot_id: null,
          participant_id: "srp_academic",
          other_route: null,
        },
        {
          code: "doc_in_other_route",
          doc_id: SR_DOC.doc_id,
          slot_id: null,
          participant_id: null,
          other_route: {
            id: "sr_01hy0a1b2c",
            profile: {
              id: "pre-defense",
              name: { ru: "Предзащита", en: "Pre-defence" },
            },
            status: "completed",
          },
        },
      ],
      sender_key: {
        id: "5d1f0c3e-7d0b-4b7e-9a51-1c4c2b0b6f11",
        label: "Мой ключ OpenPGP",
        kind: "openpgp",
        protected: true,
        signer: SR_AUTHOR.name,
      },
    }),
    ...SNAPSHOT_PREVIEW_EXAMPLES,
  },
  SendSigningRouteRequest: {
    plain: {
      expected: { [SR_DOC.doc_id]: `build:${BUILD_SHA}` },
      sign: null,
    } satisfies SendSigningRouteRequest,
    and_sign: {
      expected: { [SR_DOC.doc_id]: `build:${BUILD_SHA}` },
      sign: {
        identity_id: "5d1f0c3e-7d0b-4b7e-9a51-1c4c2b0b6f11",
        passphrase: "correct horse",
      },
    } satisfies SendSigningRouteRequest,
    // «Отправить новую версию» с полем «Что изменилось» (12.6).
    new_version: {
      expected: {
        [SR_DOC.doc_id]: `build:${WORKING_SHA}`,
        [SR_REVIEW_DOC.doc_id]: `build:${REVIEW_SHA}`,
      },
      sign: null,
      note: "Исправил формулировку темы.",
    } satisfies SendSigningRouteRequest,
  },
  SigningReminder: {
    inbox: {
      participant_id: "srp_supervisor",
      delivery: "inbox",
      link: null,
    } satisfies SigningReminder,
    manual: {
      participant_id: "srp_academic",
      delivery: "manual",
      link: "https://studio.example.org/project-invite/hspi_x",
    } satisfies SigningReminder,
  },
  SigningLink: {
    page: {
      participant_id: "srp_supervisor",
      kind: "page",
      link: "https://studio.example.org/sign/p_01hxa1c4de/sr_01hy2b7k9q",
    } satisfies SigningLink,
    invitation: {
      participant_id: "srp_academic",
      kind: "invitation",
      link: "https://studio.example.org/project-invite/hspi_x?next=%2Fsign%2Fp_01hxa1c4de%2Fsr_01hy2b7k9q",
    } satisfies SigningLink,
  },
  SigningTask: {
    approve_sign: makeSigningTask(),
    // Научрук картинкой до фиксации: картинка загружена и придержана до согласия.
    approve_image: makeSigningTask({
      route: { ...makeSigningTask().route, phase: "approval" },
      steps: [
        makeSigningTask().steps[0] ?? [],
        [
          {
            name: SR_SUPERVISOR.name,
            persona: "supervisor",
            state: "to_approve",
            at: null,
            me: true,
            card_name: null,
            changes_visible: false,
          },
        ],
      ],
      me: {
        participant_id: "srp_supervisor",
        state: "to_approve",
        next_action: "approve",
        methods: ["image", "detached"],
        method: "image",
        image_ready: true,
        image_url: `/api/v1/projects/${SR_PROJECT_ID}/signing-routes/${SR_ROUTE_ID}/task/image`,
        plate: null,
        keys: {
          server_keys_allowed: true,
          default_key: {
            id: "5d1f0c3e-7d0b-4b7e-9a51-1c4c2b0b6f11",
            label: "Мой ключ OpenPGP",
            kind: "openpgp",
            protected: true,
            signer: SR_SUPERVISOR.name,
          },
        },
        optional: false,
      },
      docs: [
        {
          ...SR_DOC,
          pdf_url: `/api/v1/projects/${SR_PROJECT_ID}/docs/${SR_DOC.doc_id}/pdf/signed`,
          frozen: false,
          token: `build:${BUILD_SHA}`,
          mine: [
            {
              slot_id: "supervisor",
              label: { ru: "Научный руководитель", en: "Supervisor" },
              page: 1,
              x_mm: 110,
              y_mm: 130,
              width_mm: 40,
              height_mm: 13.33,
              mark: "png",
              dates: [],
              status: "pending",
              reason: "awaiting_approval",
              optional: false,
            },
          ],
          others: makeSigningTask().docs[0]?.others ?? [],
          sent_at: SENT_AT,
          changed_since_mine: false,
          changed: null,
        },
      ],
      events: [
        makeRouteEvent(),
        makeRouteEvent({
          id: "sre_02",
          kind: "approved",
          participant_id: "srp_author",
        }),
      ],
    }),
    // Дата подписания (14.7): у места научрука три метки «« 13 » ноября 2026 г.», пока пустые; у
    // автора метка с датой его согласия (отправки).
    dates: datesTask(),
    // Согласующий без слотов видит все документы маршрута, своих мест на них нет.
    approver: makeSigningTask({
      me: {
        participant_id: "srp_academic",
        state: "waiting",
        next_action: "wait",
        methods: [],
        method: null,
        image_ready: false,
        image_url: null,
        plate: null,
        keys: { server_keys_allowed: false, default_key: null },
        optional: false,
      },
      docs: [
        {
          ...SR_DOC,
          pdf_url: `/api/v1/projects/${SR_PROJECT_ID}/docs/${SR_DOC.doc_id}/frozen/pdf`,
          frozen: true,
          token: null,
          mine: [],
          others: [
            ...(makeSigningTask().docs[0]?.others ?? []),
            {
              slot_id: "supervisor",
              label: { ru: "Научный руководитель", en: "Supervisor" },
              page: 1,
              x_mm: 110,
              y_mm: 130,
              width_mm: 40,
              height_mm: 22,
              mark: "plate",
              dates: [],
              status: "pending",
            },
          ],
          sent_at: SENT_AT,
          changed_since_mine: false,
          changed: null,
        },
      ],
    }),
    ...SNAPSHOT_TASK_EXAMPLES,
    ...OPTIONAL_TASK_EXAMPLES,
  },
  ApproveSigningTaskRequest: {
    approve: {
      expected: { [SR_DOC.doc_id]: `build:${BUILD_SHA}` },
      method: null,
      sign: null,
    } satisfies ApproveSigningTaskRequest,
    approve_and_sign: {
      expected: { [SR_DOC.doc_id]: `pdf:${"9c".repeat(32)}` },
      method: "detached",
      sign: { identity_id: null, passphrase: null },
    } satisfies ApproveSigningTaskRequest,
  },
  SignSigningTaskRequest: {
    ok: {
      expected: { [SR_DOC.doc_id]: `pdf:${"9c".repeat(32)}` },
      identity_id: null,
      passphrase: null,
    } satisfies SignSigningTaskRequest,
  },
  ReturnSigningTaskRequest: {
    ok: { comment: "Уточните цель проекта" } satisfies ReturnSigningTaskRequest,
  },
  SetSigningTaskPlateRequest: {
    ok: {
      identity_id: "5d1f0c3e-7d0b-4b7e-9a51-1c4c2b0b6f11",
    } satisfies SetSigningTaskPlateRequest,
  },
  SigningTaskList: {
    one: { items: [makeSigningTaskSummary()] } satisfies SigningTaskList,
  },
};
