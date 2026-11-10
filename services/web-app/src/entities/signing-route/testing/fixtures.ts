import type {
  ApproveSigningTaskRequest,
  CreateSigningRouteRequest,
  ReturnSigningTaskRequest,
  RouteEvent,
  RouteParticipant,
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

// Данные для тестов, галерей и будущих эталонов contracts/server: «Заявка на тему КП»,
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

const BUILD_SHA = "3f".repeat(32);

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
  assignments: [{ doc_id: SR_DOC.doc_id, slot_id: "author" }],
  method: "image",
  state: "done",
  next_action: "done",
  approved_at: "2026-11-10T09:00:00Z",
  notified_at: null,
  reminded_at: null,
  reminders: 0,
  ...overrides,
});

const supervisor = (overrides: Partial<RouteParticipant> = {}) =>
  makeRouteParticipant({
    id: "srp_supervisor",
    persona: "supervisor",
    user_id: SR_SUPERVISOR.id,
    name: SR_SUPERVISOR.name,
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
          optional: false,
          status: "signed",
        },
        {
          slot_id: "supervisor",
          label: { ru: "Научный руководитель", en: "Supervisor" },
          participant_id: "srp_supervisor",
          optional: false,
          status: "pending",
        },
      ],
    },
  ],
  steps: [[makeRouteParticipant()], [supervisor()]],
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
  ...overrides,
});

export const makeSigningRoutePreview = (
  overrides: Partial<SigningRoutePreview> = {},
): SigningRoutePreview => ({
  route_id: SR_ROUTE_ID,
  can_send: true,
  can_send_and_sign: false,
  visual_step: 0,
  docs: [{ ...SR_DOC, built: true, token: `build:${BUILD_SHA}` }],
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
  },
  steps: [
    [
      {
        name: SR_AUTHOR.name,
        persona: "author",
        state: "done",
        at: "2026-11-10T09:00:00Z",
        me: false,
      },
    ],
    [
      {
        name: SR_SUPERVISOR.name,
        persona: "supervisor",
        state: "to_approve_sign",
        at: null,
        me: true,
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
          status: "pending",
          reason: "no_signature_file",
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
          status: "signed",
        },
      ],
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

/**
 * Эталоны тел по будущим каталогам contracts/server/fixtures/<Схема>/<вариант>.json.
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
              optional: true,
              status: "pending",
            },
          ],
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
  },
  SigningRouteList: {
    active: { items: [makeSigningRouteSummary()] } satisfies SigningRouteList,
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
              status: "pending",
              reason: "awaiting_approval",
            },
          ],
          others: makeSigningTask().docs[0]?.others ?? [],
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
              status: "pending",
            },
          ],
        },
      ],
    }),
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
