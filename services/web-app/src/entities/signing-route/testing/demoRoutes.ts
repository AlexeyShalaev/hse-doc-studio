import type { ZodType } from "zod";
import {
  demoError,
  demoJson,
  queryString,
  type DemoRequest,
  type DemoResponse,
  type DemoRoute,
} from "@shared/api/demo";
import {
  ApproveSigningTaskRequestSchema,
  ReturnSigningTaskRequestSchema,
  SendSigningRouteRequestSchema,
  SetSigningTaskPlateRequestSchema,
  SignSigningTaskRequestSchema,
  UpdateSigningRouteRequestSchema,
  type ParticipantMembership,
  type ParticipantState,
  type RouteEvent,
  type RouteEventKind,
  type RouteParticipant,
  type RouteSignMethod,
  type RouteSlotRef,
  type SigningKeyInfo,
  type SigningNextAction,
  type SigningPlate,
  type SigningReminder,
  type SigningRoute,
  type SigningRouteBlocker,
  type SigningRoutePreview,
  type SigningRouteStatus,
  type SigningRouteSummary,
  type SigningStopReason,
  type SigningTask,
  type SigningTaskSummary,
} from "../model/signingRoute.schema";

// Моки маршрута подписания по контракту раздела 8 (docs/design/signing-route.md) поверх
// демо-транспорта (@shared/api/demo): тот же способ, что у серверного демо. Состояние в
// памяти; правила упрощены, но коды ответов и формы тел как у сервера:
// - видимый слой меняют несогласовавшие подписанты картинкой и ЭП без данных плашки;
//   когда таких нет, документы фиксируются, подписанты ЭП шагов до L подписывают параллельно;
// - отпечатки документов: `build:<sha>` до фиксации, `build:<sha>:<слой>` для совмещения
//   с фиксацией, `pdf:<sha>` после неё; несовпадение `expected` даёт 409 `doc_changed`;
// - частота отправки не ограничивается, напоминание раз в 12 часов (429 `rate_limited`).

type Localized = Record<string, string>;

export type SigningDemoUser = { id: string; name: string };

export type SigningDemoMember = {
  user_id: string;
  name: string;
  persona: string;
};

export type SigningDemoInvitation = {
  invitation_id: string;
  persona: string;
  hint: string;
};

export type SigningDemoSlot = {
  slot_id: string;
  label: Localized;
  persona: string;
  method: RouteSignMethod;
  /** Необязательный для точки слот: в маршрут попадает только через `extra_slots`. */
  optional: boolean;
  page: number;
  x_mm: number;
  y_mm: number;
  width_mm: number;
};

export type SigningDemoDoc = {
  doc_id: string;
  name: Localized;
  slots: SigningDemoSlot[];
};

export type SigningDemoProfile = {
  id: string;
  name: Localized;
  docs: SigningDemoDoc[];
  /** Порядок по умолчанию из пака: шаги персон, внутри шага параллельно. */
  order: string[][];
};

export type SigningRouteDemoOptions = {
  /** Кто сейчас вошёл; null: 401. */
  getUser: () => SigningDemoUser | null;
  /** Название проекта; null: проекта нет (404). */
  projectName?: (projectId: string) => string | null;
  /** Участники проекта с персонами; автором считается тот, кто создал черновик. */
  members?: SigningDemoMember[];
  /** Ожидающие приглашения в проект. */
  invitations?: SigningDemoInvitation[];
  profiles?: SigningDemoProfile[];
  /** Ключи на сервере разрешены: у подписанта есть ключ Студии по умолчанию. */
  serverKeysAllowed?: boolean;
  now?: () => number;
};

export type SigningRouteDemo = {
  routes: DemoRoute[];
  /** Сбросить все маршруты. */
  reset: () => void;
  /** Пересборка документа: активный маршрут встаёт на паузу (`rebuilt`). */
  rebuild: (projectId: string, docId: string) => void;
  /** Приглашение принято: участник получает аккаунт. */
  acceptInvitation: (invitationId: string, user: SigningDemoUser) => void;
};

const SLOT_LABEL = {
  author: { ru: "Студент", en: "Student" },
  supervisor: { ru: "Научный руководитель", en: "Supervisor" },
  academic: { ru: "Академический руководитель", en: "Academic supervisor" },
};

/** «Заявка на тему КП»: автор картинкой, научрук открепленной ЭП, академрук по желанию. */
export const DEMO_SIGNING_PROFILE: SigningDemoProfile = {
  id: "topic-approval",
  name: { ru: "Заявка на тему КП", en: "Course project topic application" },
  docs: [
    {
      doc_id: "topic_application",
      name: {
        ru: "Заявление о выборе темы",
        en: "Topic selection application",
      },
      slots: [
        {
          slot_id: "author",
          label: SLOT_LABEL.author,
          persona: "author",
          method: "image",
          optional: false,
          page: 1,
          x_mm: 120,
          y_mm: 230,
          width_mm: 40,
        },
        {
          slot_id: "supervisor",
          label: SLOT_LABEL.supervisor,
          persona: "supervisor",
          method: "detached",
          optional: false,
          page: 1,
          x_mm: 110,
          y_mm: 130,
          width_mm: 40,
        },
        {
          slot_id: "academic_supervisor",
          label: SLOT_LABEL.academic,
          persona: "academic_supervisor",
          method: "image",
          optional: true,
          page: 1,
          x_mm: 110,
          y_mm: 160,
          width_mm: 40,
        },
      ],
    },
  ],
  order: [["author"], ["supervisor", "co_supervisor"], ["academic_supervisor"]],
};

export const DEMO_SIGNING_MEMBERS: SigningDemoMember[] = [
  { user_id: "u_demo_petrov", name: "Петров П. П.", persona: "supervisor" },
];

type Participant = {
  id: string;
  persona: string;
  user_id: string | null;
  invitation_id: string | null;
  name: string | null;
  method: RouteSignMethod | null;
  approval: {
    round: number;
    at: string;
    tokens: Record<string, string>;
  } | null;
  signedRound: number | null;
  returnedRound: number | null;
  imageReady: boolean;
  plate: SigningPlate | null;
  notified_at: string | null;
  reminded_at: string | null;
  reminders: number;
};

type Route = {
  id: string;
  project_id: string;
  profile: SigningDemoProfile;
  status: SigningRouteStatus;
  round: number;
  deadline: string | null;
  message: string | null;
  stop_reason: SigningStopReason | null;
  sent_by: SigningDemoUser | null;
  sent_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  steps: Participant[][];
  extra: RouteSlotRef[];
  /** Отпечаток сборки каждого документа точки. */
  build: Record<string, string>;
  /** Отпечаток зафиксированного PDF; null до фиксации. */
  frozen: Record<string, string> | null;
  events: RouteEvent[];
};

type Body = Record<string, unknown>;

const notFound = () => demoError(404, "not_found", "Not Found");
const conflict = (code: string, detail: string, extra: Body = {}) =>
  demoError(409, code, detail, extra);
const invalid = (detail: string) => demoError(422, "validation_error", detail);

const isCrypto = (method: RouteSignMethod | null): boolean =>
  method === "detached" || method === "pades";

const sha = (seed: string): string => {
  let h = 0x811c9dc5;
  for (const ch of seed) {
    h ^= ch.charCodeAt(0);
    h = Math.imul(h, 0x01000193) >>> 0;
  }
  return h.toString(16).padStart(8, "0").repeat(8);
};

export const createSigningRouteDemo = (
  options: SigningRouteDemoOptions,
): SigningRouteDemo => {
  const profiles = options.profiles ?? [DEMO_SIGNING_PROFILE];
  const members = options.members ?? DEMO_SIGNING_MEMBERS;
  const invitations = options.invitations ?? [];
  const projectName = options.projectName ?? (() => "Демо-проект");
  const clock = options.now ?? (() => Date.now());
  const serverKeys = options.serverKeysAllowed ?? true;
  const now = () => new Date(clock()).toISOString();

  let routes: Route[] = [];
  let seq = 0;
  const nextId = (prefix: string) => {
    seq += 1;
    return `${prefix}_demo${String(seq).padStart(4, "0")}`;
  };
  // Кто владеет черновиком: автор маршрута, его имя для участника-автора.
  const authors = new Map<string, SigningDemoUser>();

  // Пары маршрута и их владельцы

  const pairsOf = (r: Route): (SigningDemoSlot & { doc_id: string })[] =>
    r.profile.docs.flatMap((doc) =>
      doc.slots
        .filter(
          (slot) =>
            !slot.optional ||
            r.extra.some(
              (e) => e.doc_id === doc.doc_id && e.slot_id === slot.slot_id,
            ),
        )
        .map((slot) => ({ ...slot, doc_id: doc.doc_id })),
    );

  const participants = (r: Route): Participant[] => r.steps.flat();
  // Функция, а не поле: обработчики меняют фиксацию через settle(), сужение типа тут мешает.
  const isFrozen = (r: Route): boolean => r.frozen !== null;

  const assignmentsOf = (r: Route, p: Participant): RouteSlotRef[] => {
    const owner = participants(r).find((q) => q.persona === p.persona);
    if (owner !== p) return [];
    return pairsOf(r)
      .filter((pair) => pair.persona === p.persona)
      .map((pair) => ({ doc_id: pair.doc_id, slot_id: pair.slot_id }));
  };

  const docsOf = (r: Route, p: Participant): string[] => [
    ...new Set(assignmentsOf(r, p).map((a) => a.doc_id)),
  ];

  const defaultMethod = (r: Route, persona: string): RouteSignMethod | null =>
    pairsOf(r).find((pair) => pair.persona === persona)?.method ?? null;

  // Расчёт состояния (упрощённый evaluate)

  const approved = (r: Route, p: Participant) =>
    p.approval !== null && p.approval.round === r.round;
  const signed = (r: Route, p: Participant) =>
    !isCrypto(p.method) || p.signedRound === r.round;

  /** Картинка или ЭП без данных плашки: его действие меняет видимый слой. */
  const canChangeVisual = (p: Participant) =>
    p.method === "image" || (isCrypto(p.method) && p.plate === null);

  const visualChangers = (r: Route) =>
    participants(r).filter((p) => !approved(r, p) && canChangeVisual(p));

  /** L: последний шаг, где кто-то может изменить видимый слой (раздел 4.2). */
  const visualStep = (r: Route): number =>
    r.steps.reduce(
      (last, step, index) => (step.some(canChangeVisual) ? index + 1 : last),
      0,
    );

  const currentStep = (r: Route): number | null => {
    if (r.status !== "active") return null;
    const index = r.steps.findIndex((step) =>
      step.some((p) => !approved(r, p)),
    );
    return index === -1 ? null : index + 1;
  };

  const stateOf = (r: Route, p: Participant): ParticipantState => {
    if (p.user_id === null && p.invitation_id !== null) return "invited";
    if (r.status === "returned" && p.returnedRound === r.round)
      return "returned";
    const live = r.status === "active" || r.status === "completed";
    if (live && approved(r, p)) {
      if (signed(r, p)) return "done";
      return r.frozen ? "to_sign" : "approved";
    }
    if (r.status !== "active") return "waiting";
    const step = r.steps.findIndex((s) => s.includes(p)) + 1;
    if (step !== currentStep(r)) return "waiting";
    return r.frozen && isCrypto(p.method) ? "to_approve_sign" : "to_approve";
  };

  const nextActionOf = (r: Route, p: Participant): SigningNextAction => {
    const state = stateOf(r, p);
    if (state === "done") return "done";
    if (state === "to_sign") return "sign";
    if (state === "to_approve_sign") return "approve_and_sign";
    if (state !== "to_approve") return "wait";
    const changers = visualChangers(r);
    // Последний, кто меняет видимый слой, совмещает согласие с подписью.
    return isCrypto(p.method) && changers.length === 1 && changers[0] === p
      ? "approve_and_sign"
      : "approve";
  };

  const membershipOf = (p: Participant): ParticipantMembership =>
    p.user_id !== null
      ? "member"
      : p.invitation_id !== null
        ? "invited"
        : "missing";

  const visibleLayer = (r: Route) =>
    sha(
      participants(r)
        .filter((p) => approved(r, p))
        .map((p) => p.id)
        .join(","),
    ).slice(0, 16);

  /** Отпечаток, который участник должен вернуть в `expected` следующего действия. */
  const tokenFor = (r: Route, p: Participant, docId: string): string | null => {
    const action = nextActionOf(r, p);
    if (action === "wait" || action === "done") return null;
    if (r.frozen) return `pdf:${r.frozen[docId] ?? ""}`;
    const build = `build:${r.build[docId] ?? ""}`;
    return action === "approve_and_sign"
      ? `${build}:${visibleLayer(r)}`
      : build;
  };

  const event = (
    r: Route,
    kind: RouteEventKind,
    who: string | null,
    extra: Partial<Pick<RouteEvent, "comment" | "reason">> = {},
  ) => {
    r.events.push({
      id: nextId("sre"),
      kind,
      round: r.round,
      at: now(),
      who,
      comment: extra.comment ?? null,
      reason: extra.reason ?? null,
    });
    r.updated_at = now();
  };

  /** Фиксация, напоминания очереди и завершение: повторный вызов ничего не меняет. */
  const settle = (r: Route) => {
    if (r.status !== "active") return;
    if (!r.frozen && visualChangers(r).length === 0) {
      r.frozen = Object.fromEntries(
        Object.entries(r.build).map(([doc, value]) => [
          doc,
          sha(`${value}:frozen:${String(r.round)}`),
        ]),
      );
      event(r, "frozen", null);
    }
    for (const p of participants(r)) {
      const action = nextActionOf(r, p);
      if (action !== "wait" && action !== "done" && p.notified_at === null)
        p.notified_at = now();
    }
    if (participants(r).every((p) => approved(r, p) && signed(r, p))) {
      r.status = "completed";
      r.completed_at = now();
      event(r, "completed", null);
    }
  };

  // Формы ответов

  const phaseOf = (r: Route): SigningRoute["phase"] => {
    if (r.status === "completed") return "done";
    if (r.status !== "active") return null;
    return r.frozen ? "signing" : "approval";
  };

  const slotStatus = (r: Route, pair: { persona: string }) => {
    const owner = participants(r).find((p) => p.persona === pair.persona);
    if (!owner || !approved(r, owner)) return "pending" as const;
    return signed(r, owner) ? ("signed" as const) : ("pending" as const);
  };

  const toParticipant = (r: Route, p: Participant): RouteParticipant => ({
    id: p.id,
    persona: p.persona,
    user_id: p.user_id,
    invitation_id: p.invitation_id,
    name: p.name,
    membership: membershipOf(p),
    assignments: assignmentsOf(r, p),
    method: assignmentsOf(r, p).length > 0 ? p.method : null,
    state: stateOf(r, p),
    next_action: nextActionOf(r, p),
    approved_at: approved(r, p) ? (p.approval?.at ?? null) : null,
    notified_at: p.notified_at,
    reminded_at: p.reminded_at,
    reminders: p.reminders,
  });

  const toRoute = (r: Route): SigningRoute => ({
    id: r.id,
    project_id: r.project_id,
    profile: { id: r.profile.id, name: r.profile.name },
    status: r.status,
    phase: phaseOf(r),
    round: r.round,
    current_step: currentStep(r),
    deadline: r.deadline,
    message: r.message,
    stop_reason: r.stop_reason,
    sent_by: r.sent_by ? { id: r.sent_by.id, name: r.sent_by.name } : null,
    sent_at: r.sent_at,
    completed_at: r.completed_at,
    created_at: r.created_at,
    updated_at: r.updated_at,
    docs: r.profile.docs.map((doc) => ({
      doc_id: doc.doc_id,
      name: doc.name,
      frozen: r.frozen !== null,
      slots: pairsOf(r)
        .filter((pair) => pair.doc_id === doc.doc_id)
        .map((pair) => ({
          slot_id: pair.slot_id,
          label: pair.label,
          participant_id:
            participants(r).find((p) => p.persona === pair.persona)?.id ?? null,
          optional: pair.optional,
          status: slotStatus(r, pair),
        })),
    })),
    steps: r.steps.map((step) => step.map((p) => toParticipant(r, p))),
    events: [...r.events],
  });

  const waitingFor = (r: Route) =>
    participants(r)
      .filter((p) => {
        const state = stateOf(r, p);
        return (
          state === "to_approve" ||
          state === "to_approve_sign" ||
          state === "to_sign" ||
          (state === "invited" &&
            r.steps.findIndex((s) => s.includes(p)) + 1 === currentStep(r))
        );
      })
      .map((p) => ({ name: p.name, persona: p.persona }));

  const toSummary = (r: Route): SigningRouteSummary => ({
    id: r.id,
    profile: { id: r.profile.id, name: r.profile.name },
    status: r.status,
    phase: phaseOf(r),
    round: r.round,
    current_step: currentStep(r),
    steps_total: r.steps.length,
    deadline: r.deadline,
    stop_reason: r.stop_reason,
    sent_at: r.sent_at,
    completed_at: r.completed_at,
    updated_at: r.updated_at,
    waiting_for: waitingFor(r),
  });

  const defaultKey = (user: SigningDemoUser): SigningKeyInfo | null =>
    serverKeys
      ? {
          id: `key-${user.id}`,
          label: "Ключ OpenPGP",
          kind: "openpgp",
          protected: false,
          signer: user.name,
        }
      : null;

  const allowedMethods = (r: Route, p: Participant): RouteSignMethod[] => {
    if (assignmentsOf(r, p).length === 0) return [];
    // После фиксации только способы без новой видимой метки.
    if (r.frozen) return isCrypto(p.method) && p.method ? [p.method] : [];
    return ["image", "detached"];
  };

  const toTask = (
    r: Route,
    p: Participant,
    user: SigningDemoUser,
  ): SigningTask => {
    const mine = assignmentsOf(r, p);
    const pdfBase = (docId: string) =>
      `/api/v1/projects/${encodeURIComponent(r.project_id)}/docs/${encodeURIComponent(docId)}`;
    return {
      route: {
        id: r.id,
        project: {
          id: r.project_id,
          name: projectName(r.project_id) ?? r.project_id,
        },
        profile: { id: r.profile.id, name: r.profile.name },
        status: r.status,
        phase: phaseOf(r),
        round: r.round,
        current_step: currentStep(r),
        deadline: r.deadline,
        message: r.message,
        sender: r.sent_by?.name ?? null,
        sent_at: r.sent_at,
        stop_reason: r.stop_reason,
      },
      steps: r.steps.map((step) =>
        step.map((q) => ({
          name: q.name,
          persona: q.persona,
          state: stateOf(r, q),
          at: approved(r, q) ? (q.approval?.at ?? null) : null,
          me: q === p,
        })),
      ),
      me: {
        participant_id: p.id,
        state: stateOf(r, p),
        next_action: nextActionOf(r, p),
        methods: allowedMethods(r, p),
        method: mine.length > 0 ? p.method : null,
        image_ready: p.imageReady,
        plate: p.plate,
        keys: {
          server_keys_allowed: serverKeys,
          default_key: defaultKey(user),
        },
      },
      docs: docsOf(r, p).map((docId) => {
        const doc = r.profile.docs.find((d) => d.doc_id === docId);
        const pairs = pairsOf(r).filter((pair) => pair.doc_id === docId);
        return {
          doc_id: docId,
          name: doc?.name ?? {},
          pdf_url: r.frozen
            ? `${pdfBase(docId)}/frozen/pdf`
            : `${pdfBase(docId)}/pdf/signed`,
          frozen: r.frozen !== null,
          token: tokenFor(r, p, docId),
          mine: pairs
            .filter((pair) => pair.persona === p.persona)
            .map((pair) => {
              const status = slotStatus(r, pair);
              return {
                slot_id: pair.slot_id,
                label: pair.label,
                page: pair.page,
                x_mm: pair.x_mm,
                y_mm: pair.y_mm,
                width_mm: pair.width_mm,
                mark:
                  p.method === "image"
                    ? ("png" as const)
                    : p.method === "detached"
                      ? ("plate" as const)
                      : ("none" as const),
                status,
                reason:
                  status === "signed"
                    ? null
                    : approved(r, p)
                      ? "no_signature_file"
                      : "awaiting_approval",
              };
            }),
          others: pairs
            .filter((pair) => pair.persona !== p.persona)
            .map((pair) => ({
              slot_id: pair.slot_id,
              label: pair.label,
              page: pair.page,
              status: slotStatus(r, pair),
            })),
        };
      }),
      events: [...r.events],
    };
  };

  const blockersOf = (r: Route): SigningRouteBlocker[] => {
    const blockers: SigningRouteBlocker[] = [];
    for (const p of participants(r)) {
      if (membershipOf(p) === "missing")
        blockers.push({
          code: "participant_missing",
          doc_id: null,
          slot_id: null,
          participant_id: p.id,
        });
    }
    for (const pair of pairsOf(r)) {
      if (!participants(r).some((p) => p.persona === pair.persona))
        blockers.push({
          code: "slot_unassigned",
          doc_id: pair.doc_id,
          slot_id: pair.slot_id,
          participant_id: null,
        });
    }
    if (participants(r).length === 0)
      blockers.push({
        code: "empty_route",
        doc_id: null,
        slot_id: null,
        participant_id: null,
      });
    return blockers;
  };

  const actionsOf = (r: Route, p: Participant, L: number): number => {
    const step = r.steps.findIndex((s) => s.includes(p)) + 1;
    const sender = step === 1 && p.persona === "author";
    if (!isCrypto(p.method)) return sender ? 0 : 1;
    if (sender) return L === 0 ? 0 : 1;
    // ЭП шагов до L согласует до фиксации и подписывает после неё; последний
    // меняющий видимый слой совмещает (раздел 4.4).
    if (step > L || (step === L && canChangeVisual(p))) return 1;
    return 2;
  };

  const toPreview = (r: Route, user: SigningDemoUser): SigningRoutePreview => {
    const blockers = blockersOf(r);
    const L = visualStep(r);
    const sender = r.steps[0]?.find((p) => p.user_id === user.id) ?? null;
    return {
      route_id: r.id,
      can_send: blockers.length === 0,
      can_send_and_sign:
        blockers.length === 0 &&
        L === 0 &&
        sender !== null &&
        isCrypto(sender.method),
      visual_step: L,
      docs: r.profile.docs.map((doc) => ({
        doc_id: doc.doc_id,
        name: doc.name,
        built: true,
        token: `build:${r.build[doc.doc_id] ?? ""}`,
      })),
      participants: r.steps.flatMap((step, index) =>
        step.map((p) => ({
          participant_id: p.id,
          step: index + 1,
          persona: p.persona,
          name: p.name,
          membership: membershipOf(p),
          method: assignmentsOf(r, p).length > 0 ? p.method : null,
          methods: allowedMethods(r, p),
          chooses_method: false,
          image_ready: p.imageReady,
          plate_ready: p.plate !== null,
          actions: actionsOf(r, p, L),
        })),
      ),
      blockers,
      sender_key: isCrypto(sender?.method ?? null) ? defaultKey(user) : null,
    };
  };

  // Создание участников

  const makeParticipant = (
    r: Route,
    persona: string,
    who: Pick<Participant, "user_id" | "invitation_id" | "name">,
    id: string | null = null,
  ): Participant => ({
    id: id ?? nextId("srp"),
    persona,
    ...who,
    method: defaultMethod(r, persona),
    approval: null,
    signedRound: null,
    returnedRound: null,
    imageReady: false,
    plate: null,
    notified_at: null,
    reminded_at: null,
    reminders: 0,
  });

  const resolvePerson = (
    userId: string | null,
    invitationId: string | null,
    author: SigningDemoUser,
  ): Pick<Participant, "user_id" | "invitation_id" | "name"> => {
    if (userId !== null) {
      const name =
        userId === author.id
          ? author.name
          : (members.find((m) => m.user_id === userId)?.name ?? null);
      return { user_id: userId, invitation_id: null, name };
    }
    if (invitationId !== null) {
      const inv = invitations.find((i) => i.invitation_id === invitationId);
      return {
        user_id: null,
        invitation_id: invitationId,
        name: inv?.hint ?? null,
      };
    }
    return { user_id: null, invitation_id: null, name: null };
  };

  const draftFromPack = (
    projectId: string,
    profile: SigningDemoProfile,
    author: SigningDemoUser,
  ): Route => {
    const r: Route = {
      id: nextId("sr"),
      project_id: projectId,
      profile,
      status: "draft",
      round: 0,
      deadline: null,
      message: null,
      stop_reason: null,
      sent_by: null,
      sent_at: null,
      completed_at: null,
      created_at: now(),
      updated_at: now(),
      steps: [],
      extra: [],
      build: Object.fromEntries(
        profile.docs.map((doc) => [
          doc.doc_id,
          sha(`${projectId}:${doc.doc_id}:1`),
        ]),
      ),
      frozen: null,
      events: [],
    };
    const personas = new Set(pairsOf(r).map((pair) => pair.persona));
    const ordered = profile.order
      .map((step) => step.filter((persona) => personas.has(persona)))
      .filter((step) => step.length > 0);
    // Слот, которого нет в порядке пака, идёт отдельным последним шагом.
    const rest = [...personas].filter(
      (persona) => !profile.order.some((step) => step.includes(persona)),
    );
    if (rest.length > 0) ordered.push(rest);
    r.steps = ordered.map((step) =>
      step.map((persona) => {
        if (persona === "author")
          return makeParticipant(r, persona, {
            user_id: author.id,
            invitation_id: null,
            name: author.name,
          });
        const member = members.find((m) => m.persona === persona);
        if (member)
          return makeParticipant(r, persona, {
            user_id: member.user_id,
            invitation_id: null,
            name: member.name,
          });
        const inv = invitations.find((i) => i.persona === persona);
        return makeParticipant(
          r,
          persona,
          inv
            ? {
                user_id: null,
                invitation_id: inv.invitation_id,
                name: inv.hint,
              }
            : { user_id: null, invitation_id: null, name: null },
        );
      }),
    );
    authors.set(r.id, author);
    return r;
  };

  // Обработчики

  type Ctx = { user: SigningDemoUser; projectId: string };

  const signedIn =
    (
      handler: (req: DemoRequest, ctx: Ctx) => DemoResponse,
    ): DemoRoute["handler"] =>
    (req) => {
      const user = options.getUser();
      if (!user)
        return demoError(401, "auth_required", "Authentication required");
      const projectId = req.params.projectId ?? "";
      if (projectId !== "" && projectName(projectId) === null)
        return notFound();
      return handler(req, { user, projectId });
    };

  const withRoute = (
    handler: (req: DemoRequest, r: Route, ctx: Ctx) => DemoResponse,
  ) =>
    signedIn((req, ctx) => {
      const r = routes.find(
        (item) =>
          item.id === req.params.routeId && item.project_id === ctx.projectId,
      );
      return r ? handler(req, r, ctx) : notFound();
    });

  const withTask = (
    handler: (
      req: DemoRequest,
      r: Route,
      p: Participant,
      ctx: Ctx,
    ) => DemoResponse,
  ) =>
    withRoute((req, r, ctx) => {
      const p = participants(r).find((q) => q.user_id === ctx.user.id);
      return p ? handler(req, r, p, ctx) : notFound();
    });

  const parse = <T>(schema: ZodType<T>, body: unknown): T | null => {
    const result = schema.safeParse(body);
    return result.success ? result.data : null;
  };

  const checkExpected = (
    r: Route,
    expected: Record<string, string>,
    tokens: Record<string, string | null>,
  ): DemoResponse | null => {
    const changed = Object.entries(tokens)
      .filter(([doc, token]) => expected[doc] !== token)
      .map(([doc]) => doc);
    return changed.length > 0
      ? conflict("doc_changed", "Document changed, open it again", {
          docs: changed,
          route_id: r.id,
        })
      : null;
  };

  const myTokens = (r: Route, p: Participant) =>
    Object.fromEntries(docsOf(r, p).map((doc) => [doc, tokenFor(r, p, doc)]));

  const needsTurn = (r: Route, p: Participant, states: ParticipantState[]) => {
    if (r.status !== "active")
      return conflict("route_not_active", "The signing route is not active");
    return states.includes(stateOf(r, p))
      ? null
      : conflict("not_your_turn", "It is not your turn in the signing route");
  };

  const formFile = (body: unknown): boolean =>
    typeof FormData !== "undefined" &&
    body instanceof FormData &&
    body.get("file") !== null;

  const handlers: DemoRoute[] = [
    {
      method: "GET",
      pattern: "/projects/:projectId/signing-routes",
      handler: signedIn((req, { projectId }) => {
        const profileId = queryString(req, "profile_id");
        const items = routes
          .filter(
            (r) =>
              r.project_id === projectId &&
              (profileId === null || r.profile.id === profileId),
          )
          .sort((a, b) => b.created_at.localeCompare(a.created_at))
          .map(toSummary);
        return demoJson({ items });
      }),
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/signing-routes",
      handler: signedIn((req, { user, projectId }) => {
        const profileId = (req.body as Body | null)?.profile_id;
        const profile = profiles.find((item) => item.id === profileId);
        if (!profile) return notFound();
        const open = routes.find(
          (r) =>
            r.project_id === projectId &&
            r.profile.id === profile.id &&
            ["draft", "active", "paused", "returned"].includes(r.status),
        );
        if (open) return demoJson(toRoute(open));
        // Новый маршрут точки снимает с контроля завершённый.
        for (const r of routes) {
          if (
            r.project_id === projectId &&
            r.profile.id === profile.id &&
            r.status === "completed"
          ) {
            r.status = "archived";
            event(r, "archived", user.name);
          }
        }
        const r = draftFromPack(projectId, profile, user);
        routes.push(r);
        return demoJson(toRoute(r), 201);
      }),
    },
    {
      method: "GET",
      pattern: "/projects/:projectId/signing-routes/:routeId",
      handler: withRoute((_req, r) => demoJson(toRoute(r))),
    },
    {
      method: "PUT",
      pattern: "/projects/:projectId/signing-routes/:routeId",
      handler: withRoute((req, r) => {
        if (!["draft", "paused", "returned", "cancelled"].includes(r.status))
          return conflict(
            "route_not_editable",
            "Cancel the signing route to change it",
          );
        const body = parse(UpdateSigningRouteRequestSchema, req.body);
        if (!body) return invalid("Invalid signing route");
        const author = authors.get(r.id) ?? { id: "", name: "" };
        const known = new Map(participants(r).map((p) => [p.id, p]));
        r.steps = body.steps.map((step) =>
          step.map((draft) => {
            const old = draft.id === null ? undefined : known.get(draft.id);
            const who = resolvePerson(
              draft.user_id,
              draft.invitation_id,
              author,
            );
            if (old?.persona === draft.persona) {
              const same =
                old.user_id === who.user_id &&
                old.invitation_id === who.invitation_id;
              return same ? old : { ...old, ...who, approval: null };
            }
            return makeParticipant(r, draft.persona, who);
          }),
        );
        r.extra = body.extra_slots;
        r.deadline = body.deadline;
        r.message = body.message;
        r.updated_at = now();
        for (const p of participants(r)) {
          if (assignmentsOf(r, p).length > 0 && p.method === null)
            p.method = defaultMethod(r, p.persona);
        }
        return demoJson(toRoute(r));
      }),
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/signing-routes/:routeId/preview",
      handler: withRoute((_req, r, { user }) => demoJson(toPreview(r, user))),
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/signing-routes/:routeId/send",
      handler: withRoute((req, r, { user }) => {
        if (!["draft", "paused", "returned", "cancelled"].includes(r.status))
          return conflict("route_not_editable", "The route is already sent");
        const body = parse(SendSigningRouteRequestSchema, req.body);
        if (!body) return invalid("Invalid send request");
        const blockers = blockersOf(r);
        if (blockers.length > 0)
          return conflict("route_blocked", "The route cannot be sent", {
            blockers,
          });
        const builds = Object.fromEntries(
          Object.entries(r.build).map(([doc, value]) => [
            doc,
            `build:${value}`,
          ]),
        );
        const mismatch = checkExpected(r, body.expected, builds);
        if (mismatch) return mismatch;
        const previous = r.round;
        r.round += 1;
        r.status = "active";
        r.stop_reason = null;
        r.frozen = null;
        r.sent_by = user;
        r.sent_at = now();
        r.completed_at = null;
        for (const p of participants(r)) {
          p.returnedRound = null;
          p.notified_at = null;
          p.reminders = 0;
          // Согласие переносится, если документы участника не менялись.
          const carried =
            p.approval !== null &&
            p.approval.round === previous &&
            docsOf(r, p).every(
              (doc) => p.approval?.tokens[doc] === builds[doc],
            );
          p.approval =
            carried && p.approval ? { ...p.approval, round: r.round } : null;
          p.signedRound = null;
        }
        // Отправка и есть согласие отправителя.
        for (const p of r.steps[0] ?? []) {
          if (p.user_id === user.id)
            p.approval = { round: r.round, at: now(), tokens: builds };
        }
        // «Отправить заново» пишет `resumed`, первая отправка `sent`.
        event(r, previous === 0 ? "sent" : "resumed", user.name);
        settle(r);
        if (body.sign !== null && isFrozen(r)) {
          for (const p of r.steps[0] ?? []) {
            if (p.user_id === user.id && isCrypto(p.method)) {
              p.signedRound = r.round;
              event(r, "signed", user.name);
            }
          }
          settle(r);
        }
        return demoJson(toRoute(r));
      }),
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/signing-routes/:routeId/cancel",
      handler: withRoute((_req, r, { user }) => {
        if (!["draft", "active", "paused", "returned"].includes(r.status))
          return conflict("route_not_active", "The route is already closed");
        r.status = "cancelled";
        r.stop_reason = null;
        event(r, "cancelled", user.name);
        return demoJson(toRoute(r));
      }),
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/signing-routes/:routeId/archive",
      handler: withRoute((_req, r, { user }) => {
        if (r.status !== "completed")
          return conflict(
            "route_not_active",
            "Only a completed route can be archived",
          );
        r.status = "archived";
        event(r, "archived", user.name);
        return demoJson(toRoute(r));
      }),
    },
    {
      method: "POST",
      pattern:
        "/projects/:projectId/signing-routes/:routeId/participants/:participantId/remind",
      handler: withRoute((req, r, { user }) => {
        const p = participants(r).find(
          (q) => q.id === req.params.participantId,
        );
        if (!p) return notFound();
        if (r.status !== "active")
          return conflict(
            "route_not_active",
            "The signing route is not active",
          );
        const state = stateOf(r, p);
        const turn =
          state === "to_approve" ||
          state === "to_approve_sign" ||
          state === "to_sign" ||
          state === "invited";
        if (!turn)
          return conflict("participant_not_waiting", "Nothing to remind about");
        const last = p.reminded_at === null ? null : Date.parse(p.reminded_at);
        const interval = 12 * 60 * 60 * 1000;
        if (last !== null && clock() - last < interval)
          return demoError(429, "rate_limited", "Too many reminders", {
            retry_after: Math.ceil((last + interval - clock()) / 1000),
          });
        p.reminded_at = now();
        p.reminders += 1;
        event(r, state === "invited" ? "invited" : "reminded", user.name);
        const reminder: SigningReminder =
          state === "invited"
            ? {
                participant_id: p.id,
                delivery: "manual",
                link: `${window.location.origin}/project-invite/hspi_demo_ok`,
              }
            : { participant_id: p.id, delivery: "inbox", link: null };
        return demoJson(reminder);
      }),
    },
    {
      method: "GET",
      pattern: "/projects/:projectId/signing-routes/:routeId/task",
      handler: withTask((_req, r, p, { user }) => demoJson(toTask(r, p, user))),
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/signing-routes/:routeId/task/approve",
      handler: withTask((req, r, p, { user }) => {
        const refused = needsTurn(r, p, ["to_approve", "to_approve_sign"]);
        if (refused) return refused;
        const body = parse(ApproveSigningTaskRequestSchema, req.body);
        if (!body) return invalid("Invalid approval");
        const mismatch = checkExpected(r, body.expected, myTokens(r, p));
        if (mismatch) return mismatch;
        if (body.method !== null) {
          if (!allowedMethods(r, p).includes(body.method))
            return invalid("Method is not allowed");
          p.method = body.method;
        }
        const combine = nextActionOf(r, p) === "approve_and_sign";
        // Данные плашки известны из ключа подписанта.
        if (isCrypto(p.method) && p.plate === null)
          p.plate = {
            owner: user.name,
            kind: "openpgp",
            cert_id: sha(user.id).slice(0, 16),
          };
        p.approval = {
          round: r.round,
          at: now(),
          tokens: Object.fromEntries(
            Object.entries(r.build).map(([doc, value]) => [
              doc,
              `build:${value}`,
            ]),
          ),
        };
        event(r, "approved", user.name);
        settle(r);
        if (
          combine &&
          body.sign !== null &&
          isFrozen(r) &&
          isCrypto(p.method)
        ) {
          p.signedRound = r.round;
          event(r, "signed", user.name);
          settle(r);
        }
        return demoJson(toTask(r, p, user));
      }),
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/signing-routes/:routeId/task/sign",
      handler: withTask((req, r, p, { user }) => {
        const refused = needsTurn(r, p, ["to_sign"]);
        if (refused) return refused;
        const body = parse(SignSigningTaskRequestSchema, req.body);
        if (!body) return invalid("Invalid signature request");
        const mismatch = checkExpected(r, body.expected, myTokens(r, p));
        if (mismatch) return mismatch;
        p.signedRound = r.round;
        event(r, "signed", user.name);
        settle(r);
        return demoJson(toTask(r, p, user));
      }),
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/signing-routes/:routeId/task/return",
      handler: withTask((req, r, p, { user }) => {
        const refused = needsTurn(r, p, [
          "to_approve",
          "to_approve_sign",
          "to_sign",
        ]);
        if (refused) return refused;
        const body = parse(ReturnSigningTaskRequestSchema, req.body);
        if (!body)
          return invalid("A comment of up to 2000 characters is required");
        r.status = "returned";
        r.stop_reason = "returned";
        p.returnedRound = r.round;
        event(r, "returned", user.name, {
          comment: body.comment,
          reason: "returned",
        });
        return demoJson(toTask(r, p, user));
      }),
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/signing-routes/:routeId/task/image",
      handler: withTask((req, r, p, { user }) => {
        const refused = needsTurn(r, p, ["to_approve", "to_approve_sign"]);
        if (refused) return refused;
        if (!formFile(req.body)) return invalid("Image file is required");
        p.imageReady = true;
        r.updated_at = now();
        return demoJson(toTask(r, p, user));
      }),
    },
    {
      method: "PUT",
      pattern: "/projects/:projectId/signing-routes/:routeId/task/plate",
      handler: withTask((req, r, p, { user }) => {
        const refused = needsTurn(r, p, ["to_approve", "to_approve_sign"]);
        if (refused) return refused;
        const body = parse(SetSigningTaskPlateRequestSchema, req.body);
        if (!body) return invalid("identity_id is required");
        p.plate = {
          owner: user.name,
          kind: "openpgp",
          cert_id: sha(body.identity_id).slice(0, 16),
        };
        r.updated_at = now();
        return demoJson(toTask(r, p, user));
      }),
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/signing-routes/:routeId/task/plate/file",
      handler: withTask((req, r, p, { user }) => {
        const refused = needsTurn(r, p, ["to_approve", "to_approve_sign"]);
        if (refused) return refused;
        if (!formFile(req.body)) return invalid("Certificate file is required");
        p.plate = {
          owner: user.name,
          kind: "x509",
          cert_id: sha(user.id).slice(0, 16),
        };
        r.updated_at = now();
        return demoJson(toTask(r, p, user));
      }),
    },
    {
      method: "GET",
      pattern: "/account/signing-tasks",
      handler: signedIn((_req, { user }) => {
        const items: SigningTaskSummary[] = [];
        for (const r of routes) {
          if (r.status !== "active") continue;
          for (const p of participants(r)) {
            if (p.user_id !== user.id) continue;
            const action = nextActionOf(r, p);
            if (action === "wait" || action === "done") continue;
            items.push({
              project: {
                id: r.project_id,
                name: projectName(r.project_id) ?? r.project_id,
              },
              route_id: r.id,
              profile: { id: r.profile.id, name: r.profile.name },
              round: r.round,
              sender: r.sent_by?.name ?? null,
              deadline: r.deadline,
              next_action: action,
              since: p.notified_at,
            });
          }
        }
        return demoJson({ items });
      }),
    },
  ];

  return {
    routes: handlers,
    reset: () => {
      routes = [];
      authors.clear();
      seq = 0;
    },
    rebuild: (projectId, docId) => {
      for (const r of routes) {
        if (r.project_id !== projectId || !(docId in r.build)) continue;
        r.build[docId] = sha(`${r.build[docId] ?? ""}:rebuilt`);
        if (r.status === "active" || r.status === "completed") {
          r.status = "paused";
          r.stop_reason = "rebuilt";
          r.frozen = null;
          event(r, "paused", null, { reason: "rebuilt" });
        }
      }
    },
    acceptInvitation: (invitationId, user) => {
      for (const r of routes) {
        for (const p of participants(r)) {
          if (p.invitation_id !== invitationId) continue;
          p.user_id = user.id;
          p.invitation_id = null;
          p.name = user.name;
        }
        settle(r);
      }
    },
  };
};
