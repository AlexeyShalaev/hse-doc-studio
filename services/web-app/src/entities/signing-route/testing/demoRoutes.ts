import type { ZodType } from "zod";
import {
  demoError,
  demoJson,
  demoNoContent,
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
  type RouteDocChange,
  type RouteDocVersion,
  type RouteEvent,
  type RouteEventKind,
  type RouteParticipant,
  type RoutePersonaCandidates,
  type RouteSignMethod,
  type RouteSlotRef,
  type SigningKeyInfo,
  type SigningLink,
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
// - частота отправки не ограничивается, напоминание раз в 12 часов (429 `rate_limited`);
// - приглашённому без почты на сервере (`mailEnabled`) «Напомнить» и «Скопировать ссылку» отдают
//   новую ссылку приглашения без пауз и отметок; с почтой ссылка уходит письмом (409 `link_by_mail`);
// - слот с видимой меткой без места на странице (`isPlaced`) мешает отправке: `placement_off`;
// - подпись ключом Студии: ключ с паролем без пароля даёт 400 `passphrase_required`, пароль
//   `wrong` даёт 400 `passphrase_invalid`, чужой ключ 409 `key_not_found`, при запрете
//   ключей на сервере 403 `server_keys_forbidden`; пароль `broken` в «Отправить и подписать»
//   отправляет маршрут и отвечает 400 `sign_failed` с `sent: true`;
// - готовая подпись и подпись КриптоПро приходят существующим адресом
//   `.../docs/{doc}/detached/{slot}`: только участнику в его очередь подписывать (6.10);
// - версия на подписи (раздел 12): отправка снимает её с рабочей сборки, пересборка маршрут не
//   останавливает, а только даёт «есть изменения»; новая версия из `active` и `completed`
//   (без изменений 409 `nothing_changed`) меняет версию только у изменившихся документов, согласия
//   и ЭП по остальным остаются; отмена снимает версии; «Подписывать текущую сборку»
//   (`DELETE .../docs/{doc}/pinned`) только у документа, который маршрут не держит;
// - необязательные подписи и пропуск (раздел 13): флаг «Подпись необязательна» живёт в состоянии
//   подписей (`isOptional`), пропустить можно участника в очереди, у которого все оставшиеся пары
//   необязательны (`POST .../participants/{pid}/skip`, коды 13.6); пропущенный проходит шаг, его
//   метка уходит из видимого слоя, а B без ЭП над ним фиксируется заново; новый раунд переносит
//   пропуск, пока пары необязательны, иначе участник возвращается в маршрут.

type Localized = Record<string, string>;

export type SigningDemoUser = { id: string; name: string };

export type SigningDemoMember = {
  user_id: string;
  name: string;
  persona: string;
  /** Известные данные плашки (открытый ключ в профиле, срез R10); без них ЭП-подписант задаёт их сам. */
  plate?: SigningPlate | null;
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
  /** Слот не требует точка: в маршрут попадает только через `extra_slots` (сверх точки). */
  extra: boolean;
  /** Пак запрещает отмечать подпись необязательной (`required: true` слота каталога, 13.3). */
  required?: boolean;
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
  serverKeysAllowed?: boolean | (() => boolean);
  /**
   * Ключи Студии подписанта, ключ по умолчанию первым. Без функции у каждого один ключ
   * без пароля (пока ключи на сервере разрешены).
   */
  keysOf?: (user: SigningDemoUser) => SigningKeyInfo[];
  /** «Запомнить для других проектов»: картинка уходит в профиль подписанта. */
  onRememberImage?: (user: SigningDemoUser, image: Blob) => void;
  /** Включено ли место слота на странице документа; без функции места есть у всех слотов. */
  isPlaced?: (projectId: string, docId: string, slotId: string) => boolean;
  /** На сервере настроена почта: приглашения и напоминания уходят письмом. По умолчанию нет. */
  mailEnabled?: () => boolean;
  /**
   * «Подпись необязательна» на точке (состояние подписей проекта, 13.3); без функции все подписи
   * обязательны.
   */
  isOptional?: (
    projectId: string,
    profileId: string,
    docId: string,
    slotId: string,
  ) => boolean;
  now?: () => number;
};

/** Чужой маршрут, в котором вошедший подписант: чтобы в демо были задачи «На подпись». */
export type SigningDemoSeed = {
  projectId: string;
  profileId?: string;
  /** Кто отправил маршрут: автор проекта. */
  sender: SigningDemoUser;
  /** Кто подписывает вторым шагом и в какой роли. */
  signer: SigningDemoUser;
  persona: string;
  deadline?: string | null;
  message?: string | null;
  /**
   * В каком виде маршрут (раздел 12): `sent` только что отправлен; `diverged` автор потом
   * пересобрал документы, рабочая сборка ушла от версии на подписи; `new_version` подписант уже
   * согласовал, затем автор отправил новую версию; `migrated` маршрут 0.20.0, перенос нашёл
   * сборку (версия от `sent_at`, снаружи не отличить); `migration_lost` маршрут 0.20.0, версию не
   * восстановить: стоит с `sent_changed`, нужна новая версия.
   */
  state?: SigningDemoSeedState;
};

export type SigningDemoSeedState =
  "sent" | "diverged" | "new_version" | "migrated" | "migration_lost";

export type SigningRouteDemo = {
  routes: DemoRoute[];
  /** Сбросить все маршруты. */
  reset: () => void;
  /**
   * Пересборка документа с другим PDF: маршрут идёт дальше, у документа «есть изменения после
   * отправки» (раздел 12.5).
   */
  rebuild: (projectId: string, docId: string) => void;
  /**
   * Версию на подписи подменили мимо маршрута (git, восстановление `.hse-studio`): идущий или
   * завершённый маршрут встаёт с `sent_changed` (12.5).
   */
  tamper: (projectId: string, docId: string) => void;
  /** Приглашение принято: участник получает аккаунт. */
  acceptInvitation: (invitationId: string, user: SigningDemoUser) => void;
  /** Сколько задач «На подпись» у человека: для `InboxSummary.signing_tasks` демо «Входящих». */
  taskCount: (userId: string) => number;
  /** Отправленный маршрут чужого проекта с подписантом `signer`; возвращает id маршрута. */
  seed: (input: SigningDemoSeed) => string | null;
  /**
   * Свой маршрут автора с академруком сверх точки (13.2): научрук `signer` согласовал, очередь
   * академрука `academic`. Возвращает id маршрута.
   */
  seedOptional: (input: {
    projectId: string;
    sender: SigningDemoUser;
    signer: SigningDemoUser;
    academic: SigningDemoUser;
  }) => string | null;
  /** Пропущенные пары проекта для `SignaturesState.skipped`: маршруты, которые держат документы. */
  skippedOf: (projectId: string) => Record<string, Record<string, SkippedPair>>;
  /** Точки, чей маршрут включил слот сверх точки, для `RuntimeSlot.extra_by`. */
  extraBy: (projectId: string) => Record<string, Record<string, ProfileRef[]>>;
  /** Слот документа на точке подписан в маршруте, который держит документ (`slot_signed`). */
  isSlotSigned: (
    projectId: string,
    profileId: string,
    docId: string,
    slotId: string,
  ) => boolean;
  /** Маршрут точки держит документ (снятая отметка пропущенной пары вернётся следующим раундом). */
  holdsDoc: (projectId: string, profileId: string, docId: string) => boolean;
};

type ProfileRef = { id: string; name: Localized };

/** Пропуск пары в состоянии подписей (`SkippedSlot`, 13.3). */
export type SkippedPair = {
  profile_id: string;
  route_id: string;
  round: number;
  at: string;
  keep_mark: boolean;
};

const SLOT_LABEL = {
  author: { ru: "Студент", en: "Student" },
  supervisor: { ru: "Научный руководитель", en: "Supervisor" },
  academic: { ru: "Академический руководитель", en: "Academic supervisor" },
};

/**
 * «Заявка на тему КП»: автор картинкой, научрук открепленной ЭП, академрук сверх точки. Подпись
 * автора пак требует (`required`): отметить её необязательной нельзя.
 */
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
          extra: false,
          required: true,
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
          extra: false,
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
          extra: true,
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
  {
    user_id: "u_demo_petrov",
    name: "Петров П. П.",
    persona: "supervisor",
    plate: {
      owner: "Петров П. П.",
      kind: "openpgp",
      cert_id: "1A2B 3C4D 5E6F 7A8B",
    },
  },
];

type Participant = {
  id: string;
  persona: string;
  user_id: string | null;
  invitation_id: string | null;
  name: string | null;
  method: RouteSignMethod | null;
  /**
   * Согласие: отпечатки `build:<sha>` версии на подписи по документам. Новая версия переносит
   * его в новый раунд всегда, а действует оно по каждому документу отдельно (12.6).
   */
  approval: {
    round: number;
    at: string;
    tokens: Record<string, string>;
  } | null;
  /** ЭП по документам: отпечаток B, над которым поставлена. */
  signed: Record<string, string>;
  returnedRound: number | null;
  imageReady: boolean;
  plate: SigningPlate | null;
  notified_at: string | null;
  reminded_at: string | null;
  reminders: number;
  /**
   * Пропуск автором (13.3): раунд, время, пропущенные пары (оставшиеся неподписанными) и
   * документы, где метка осталась в B с ЭП над ним. Новый раунд переносит его или снимает.
   */
  skipped: {
    round: number;
    at: string;
    pairs: RouteSlotRef[];
    kept: string[];
  } | null;
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
  /** Рабочая сборка каждого документа точки. */
  build: Record<string, string>;
  /** Версия на подписи по документам (12.3); пусто у черновика и после отмены. */
  pinned: Record<string, RouteDocVersion>;
  /** Снимок маршрута 0.20.0 без перенесённой версии (12.11): с ним сравнивается рабочая сборка. */
  legacy: Record<string, string>;
  /** Документы, у которых последняя отправка сменила версию на подписи (новая версия). */
  lastChanged: string[];
  /** Зафиксированный PDF (B) по документам; документа нет, пока он не зафиксирован. */
  frozen: Record<string, string>;
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
  const serverKeysOption = options.serverKeysAllowed ?? true;
  const serverKeysAllowed = (): boolean =>
    typeof serverKeysOption === "function"
      ? serverKeysOption()
      : serverKeysOption;
  const now = () => new Date(clock()).toISOString();
  const isPlaced = options.isPlaced ?? (() => true);
  const mailEnabled = options.mailEnabled ?? (() => false);
  const isOptionalOption = options.isOptional ?? (() => false);

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
            !slot.extra ||
            r.extra.some(
              (e) => e.doc_id === doc.doc_id && e.slot_id === slot.slot_id,
            ),
        )
        .map((slot) => ({ ...slot, doc_id: doc.doc_id })),
    );

  const participants = (r: Route): Participant[] => r.steps.flat();
  const routeDocs = (r: Route): string[] => r.profile.docs.map((d) => d.doc_id);
  const isDocFrozen = (r: Route, docId: string): boolean => docId in r.frozen;
  /** Снять B документа: его подписывают заново после новой фиксации. */
  const unfreeze = (r: Route, docId: string): void => {
    r.frozen = Object.fromEntries(
      Object.entries(r.frozen).filter(([doc]) => doc !== docId),
    );
  };
  /** Все документы маршрута зафиксированы: фаза подписи. */
  const isFrozen = (r: Route): boolean =>
    routeDocs(r).every((doc) => isDocFrozen(r, doc));
  const sentToken = (r: Route, docId: string): string =>
    `build:${r.pinned[docId]?.sha256 ?? r.build[docId] ?? ""}`;
  /** Рабочая сборка ушла от отправленного: от версии на подписи, а без неё от снимка 0.20.0. */
  const isChanged = (r: Route, docId: string): boolean => {
    if (r.status === "draft" || r.status === "cancelled") return false;
    const sent = r.pinned[docId]?.sha256 ?? r.legacy[docId];
    return sent !== undefined && r.build[docId] !== sent;
  };
  const changedDocs = (r: Route): string[] =>
    routeDocs(r).filter((doc) => isChanged(r, doc));

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

  /** Документы, которые участник согласует: свои, у согласующего без слотов все документы маршрута. */
  const approvalDocs = (r: Route, p: Participant): string[] => {
    const own = docsOf(r, p);
    return own.length > 0 ? own : routeDocs(r);
  };

  const defaultMethod = (r: Route, persona: string): RouteSignMethod | null =>
    pairsOf(r).find((pair) => pair.persona === persona)?.method ?? null;

  // Расчёт состояния (упрощённый evaluate)

  /** Согласие по документу действует, пока его отпечаток равен версии на подписи (12.6). */
  const approvedDoc = (r: Route, p: Participant, docId: string) =>
    p.approval !== null &&
    p.approval.round === r.round &&
    p.approval.tokens[docId] === sentToken(r, docId);
  /** Пропущен автором в этом раунде (13.3): шаг пройден, подписывать ему нечего. */
  const isSkipped = (r: Route, p: Participant): boolean =>
    p.skipped !== null && p.skipped.round === r.round;
  /** Согласовал для хода шагов: совпали отпечатки всех его документов; пропущенный тоже прошёл. */
  const approved = (r: Route, p: Participant) =>
    isSkipped(r, p) ||
    approvalDocs(r, p).every((doc) => approvedDoc(r, p, doc));
  const signedDoc = (r: Route, p: Participant, docId: string) =>
    isDocFrozen(r, docId) && p.signed[docId] === r.frozen[docId];
  const signed = (r: Route, p: Participant) =>
    isSkipped(r, p) ||
    !isCrypto(p.method) ||
    docsOf(r, p).every((doc) => signedDoc(r, p, doc));

  /** «Подпись необязательна» у пары на точке маршрута. */
  const pairOptional = (r: Route, pair: RouteSlotRef): boolean =>
    isOptionalOption(r.project_id, r.profile.id, pair.doc_id, pair.slot_id);
  /** ЭП участника над текущими B всех его документов. */
  const signAll = (r: Route, p: Participant) => {
    for (const doc of docsOf(r, p)) {
      const frozen = r.frozen[doc];
      if (frozen !== undefined) p.signed[doc] = frozen;
    }
  };

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
    const live = r.status === "active" || r.status === "completed";
    if (live && isSkipped(r, p)) return "skipped";
    if (p.user_id === null && p.invitation_id !== null) return "invited";
    if (r.status === "returned" && p.returnedRound === r.round)
      return "returned";
    if (live && approved(r, p)) {
      if (signed(r, p)) return "done";
      // Согласовал до фиксации и ждёт её: `waiting` с `approved_at`, как в ядре.
      return isFrozen(r) ? "to_sign" : "waiting";
    }
    if (r.status !== "active") return "waiting";
    const step = r.steps.findIndex((s) => s.includes(p)) + 1;
    if (step !== currentStep(r)) return "waiting";
    return isFrozen(r) && isCrypto(p.method) ? "to_approve_sign" : "to_approve";
  };

  const nextActionOf = (r: Route, p: Participant): SigningNextAction => {
    const state = stateOf(r, p);
    if (state === "done" || state === "skipped") return "done";
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

  /**
   * Отпечаток, который участник должен вернуть в `expected` следующего действия; null у
   * документа, где делать нечего (в раунде новой версии: согласие и подпись по нему остались).
   */
  const tokenFor = (r: Route, p: Participant, docId: string): string | null => {
    const action = nextActionOf(r, p);
    if (action === "wait" || action === "done") return null;
    if (isFrozen(r))
      return signedDoc(r, p, docId) && approvedDoc(r, p, docId)
        ? null
        : `pdf:${r.frozen[docId] ?? ""}`;
    if (approvedDoc(r, p, docId)) return null;
    const build = sentToken(r, docId);
    return action === "approve_and_sign"
      ? `${build}:${visibleLayer(r)}`
      : build;
  };

  const event = (
    r: Route,
    kind: RouteEventKind,
    who: string | null,
    extra: Partial<
      Pick<RouteEvent, "comment" | "reason" | "participant_id" | "changed_docs">
    > = {},
  ) => {
    r.events.push({
      id: nextId("sre"),
      kind,
      round: r.round,
      at: now(),
      who,
      participant_id: extra.participant_id ?? null,
      comment: extra.comment ?? null,
      reason: extra.reason ?? null,
      changed_docs: extra.changed_docs ?? null,
    });
    r.updated_at = now();
  };

  /** Фиксация, напоминания очереди и завершение: повторный вызов ничего не меняет. */
  const settle = (r: Route) => {
    if (r.status !== "active") return;
    // Фиксируются документы без B из версии на подписи; B документов без изменений остаются.
    if (!isFrozen(r) && visualChangers(r).length === 0) {
      for (const doc of routeDocs(r)) {
        if (isDocFrozen(r, doc)) continue;
        // Слой в отпечатке: перефиксация после пропуска даёт другой B (13.5).
        r.frozen[doc] = sha(
          `${r.pinned[doc]?.sha256 ?? ""}:frozen:${String(r.round)}:${visibleLayer(r)}`,
        );
      }
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
    return isFrozen(r) ? "signing" : "approval";
  };

  /** Слот по своему документу: картинка открыта после согласия, ЭП над текущим B (12.6). */
  const slotStatus = (
    r: Route,
    pair: { persona: string; doc_id: string; slot_id: string },
  ) => {
    const owner = participants(r).find((p) => p.persona === pair.persona);
    if (
      owner &&
      isSkipped(r, owner) &&
      owner.skipped?.pairs.some(
        (s) => s.doc_id === pair.doc_id && s.slot_id === pair.slot_id,
      )
    )
      return "skipped" as const;
    if (!owner || !approvedDoc(r, owner, pair.doc_id))
      return "pending" as const;
    if (!isCrypto(owner.method)) return "signed" as const;
    return signedDoc(r, owner, pair.doc_id)
      ? ("signed" as const)
      : ("pending" as const);
  };

  /** Как `changes_visible` расчёта: не согласовал, а видимый слой (картинка, плашка) ещё ставит. */
  const changesVisible = (r: Route, p: Participant): boolean =>
    !isFrozen(r) &&
    !approved(r, p) &&
    assignmentsOf(r, p).length > 0 &&
    p.method !== "pades";

  /** Метка участника стоит в B документа: картинка открыта согласием, плашка с данными (13.5). */
  const markInFrozen = (r: Route, p: Participant, docId: string): boolean =>
    isDocFrozen(r, docId) &&
    p.method !== "pades" &&
    (approvedDoc(r, p, docId) || (p.method === "detached" && p.plate !== null));

  /** Над B документа уже есть чужая ЭП: перефиксация её сбросила бы, метка остаётся (13.5). */
  const othersSignedOver = (r: Route, p: Participant, docId: string): boolean =>
    participants(r).some(
      (q) => q !== p && isCrypto(q.method) && signedDoc(r, q, docId),
    );

  /** Оставшиеся (неподписанные) пары участника. */
  const remainingPairs = (r: Route, p: Participant): RouteSlotRef[] =>
    assignmentsOf(r, p).filter(
      (pair) => slotStatus(r, { ...pair, persona: p.persona }) !== "signed",
    );

  /** Его очередь: действие ждут сейчас или приглашение не принято, а шаг ждёт его (13.3). */
  const isTurn = (r: Route, p: Participant): boolean => {
    const state = stateOf(r, p);
    if (
      state === "to_approve" ||
      state === "to_approve_sign" ||
      state === "to_sign"
    )
      return true;
    return (
      state === "invited" &&
      r.steps.findIndex((s) => s.includes(p)) + 1 === currentStep(r)
    );
  };

  /** Можно ли пропустить участника сейчас и что будет с метками (`ParticipantView.skip`). */
  const skipOf = (r: Route, p: Participant) => {
    const view = (
      blocker: "not_turn" | "required_slots" | "no_slots" | "done" | null,
      docs: { keeps: string[]; refreezes: string[] } = {
        keeps: [],
        refreezes: [],
      },
    ) => ({
      available: blocker === null,
      blocker,
      keeps_marks: docs.keeps,
      refreezes: docs.refreezes,
    });
    const state = stateOf(r, p);
    if (state === "done" || state === "skipped") return view("done");
    if (assignmentsOf(r, p).length === 0) return view("no_slots");
    if (!isTurn(r, p)) return view("not_turn");
    const left = remainingPairs(r, p);
    if (left.length === 0) return view("done");
    if (!left.every((pair) => pairOptional(r, pair)))
      return view("required_slots");
    const marked = [
      ...new Set(
        left
          .map((pair) => pair.doc_id)
          .filter((doc) => markInFrozen(r, p, doc)),
      ),
    ];
    return view(null, {
      keeps: marked.filter((doc) => othersSignedOver(r, p, doc)),
      refreezes: marked.filter((doc) => !othersSignedOver(r, p, doc)),
    });
  };

  /** Тот, кто управляет маршрутом: автор черновика или отправитель. */
  const manages = (r: Route, user: SigningDemoUser | null): boolean =>
    user !== null &&
    (authors.get(r.id)?.id === user.id || r.sent_by?.id === user.id);

  const toParticipant = (
    r: Route,
    p: Participant,
    viewer: SigningDemoUser | null,
  ): RouteParticipant => ({
    id: p.id,
    persona: p.persona,
    user_id: p.user_id,
    invitation_id: p.invitation_id,
    name: p.name,
    membership: membershipOf(p),
    card_name: p.name,
    assignments: assignmentsOf(r, p),
    method: assignmentsOf(r, p).length > 0 ? p.method : null,
    state: stateOf(r, p),
    next_action: nextActionOf(r, p),
    changes_visible: changesVisible(r, p),
    approved_at: approved(r, p) ? (p.approval?.at ?? null) : null,
    notified_at: p.notified_at,
    reminded_at: p.reminded_at,
    reminders: p.reminders,
    skipped_at: isSkipped(r, p) ? (p.skipped?.at ?? null) : null,
    skip: r.status === "active" && manages(r, viewer) ? skipOf(r, p) : null,
  });

  /** Как R5: из кого выбирать на персоны маршрута и всех его слотов (участники проекта, затем приглашения). */
  const candidatesOf = (r: Route): RoutePersonaCandidates[] => {
    const author = authors.get(r.id);
    const personas = [
      ...new Set([
        ...participants(r).map((p) => p.persona),
        ...r.profile.docs.flatMap((doc) =>
          doc.slots.map((slot) => slot.persona),
        ),
      ]),
    ];
    return personas.map((persona) => ({
      persona,
      people: [
        ...(persona === "author" && author
          ? [{ kind: "member" as const, id: author.id, name: author.name }]
          : []),
        ...members
          .filter((m) => m.persona === persona)
          .map((m) => ({
            kind: "member" as const,
            id: m.user_id,
            name: m.name,
          })),
        ...invitations
          .filter((i) => i.persona === persona)
          .map((i) => ({
            kind: "invitation" as const,
            id: i.invitation_id,
            name: i.hint,
          })),
      ],
    }));
  };

  const toRoute = (
    r: Route,
    viewer: SigningDemoUser | null = null,
  ): SigningRoute => ({
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
      frozen: isDocFrozen(r, doc.doc_id),
      sent: r.pinned[doc.doc_id] ?? null,
      changed: isChanged(r, doc.doc_id),
      slots: pairsOf(r)
        .filter((pair) => pair.doc_id === doc.doc_id)
        .map((pair) => ({
          slot_id: pair.slot_id,
          label: pair.label,
          participant_id:
            participants(r).find((p) => p.persona === pair.persona)?.id ?? null,
          extra: pair.extra,
          optional: pairOptional(r, pair),
          status: slotStatus(r, pair),
        })),
    })),
    steps: r.steps.map((step) => step.map((p) => toParticipant(r, p, viewer))),
    events: [...r.events],
    candidates: candidatesOf(r),
    changed_docs: changedDocs(r),
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
    docs: routeDocs(r),
    changed_docs: changedDocs(r),
  });

  const keysOf = (user: SigningDemoUser): SigningKeyInfo[] => {
    if (!serverKeysAllowed()) return [];
    return options.keysOf
      ? options.keysOf(user)
      : [
          {
            id: `key-${user.id}`,
            label: "Ключ OpenPGP",
            kind: "openpgp",
            protected: false,
            signer: user.name,
          },
        ];
  };

  const defaultKey = (user: SigningDemoUser): SigningKeyInfo | null =>
    keysOf(user)[0] ?? null;

  /** Ключ актора по id. Без своего списка ключей (`keysOf`) подходит любой id. */
  const findKey = (
    user: SigningDemoUser,
    identityId: string | null,
  ): SigningKeyInfo | null => {
    const fallback = defaultKey(user);
    if (identityId === null) return fallback;
    if (!options.keysOf) return fallback && { ...fallback, id: identityId };
    return keysOf(user).find((item) => item.id === identityId) ?? null;
  };

  /** Можно ли подписать этим ключом Студии; null: можно. */
  const refuseKey = (
    user: SigningDemoUser,
    key: { identity_id: string | null; passphrase: string | null },
  ): DemoResponse | null => {
    if (!serverKeysAllowed())
      return demoError(
        403,
        "server_keys_forbidden",
        "Private keys are not stored on this server",
      );
    const found = findKey(user, key.identity_id);
    if (!found) return conflict("key_not_found", "Signing key not found");
    if (found.protected && !key.passphrase)
      return demoError(
        400,
        "passphrase_required",
        "The key needs its passphrase",
      );
    if (key.passphrase === "wrong")
      return demoError(400, "passphrase_invalid", "Wrong key passphrase");
    return null;
  };

  const allowedMethods = (r: Route, p: Participant): RouteSignMethod[] => {
    if (assignmentsOf(r, p).length === 0) return [];
    // После фиксации только способы без новой видимой метки.
    if (isFrozen(r)) return isCrypto(p.method) && p.method ? [p.method] : [];
    // Картинке и плашке нужно место на странице: без него остаётся только текущий способ (6.3).
    const placed = assignmentsOf(r, p).every((pair) =>
      isPlaced(r.project_id, pair.doc_id, pair.slot_id),
    );
    if (!placed) return p.method ? [p.method] : [];
    return ["image", "detached"];
  };

  /** Место слота и его метка: высота как у сервера, по способу (картинка 0.4 ширины, плашка 0.55). */
  const slotPlace = (
    pair: ReturnType<typeof pairsOf>[number],
    method: RouteSignMethod | null,
  ) => {
    const mark =
      method === "image"
        ? ("png" as const)
        : method === "detached"
          ? ("plate" as const)
          : ("none" as const);
    const aspect = { png: 0.4, plate: 0.55 } as const;
    return {
      slot_id: pair.slot_id,
      label: pair.label,
      page: pair.page,
      x_mm: pair.x_mm,
      y_mm: pair.y_mm,
      width_mm: pair.width_mm,
      height_mm:
        mark === "none"
          ? null
          : Math.round(pair.width_mm * aspect[mark] * 100) / 100,
      mark,
    };
  };

  const toTask = (
    r: Route,
    p: Participant,
    user: SigningDemoUser,
  ): SigningTask => {
    const mine = assignmentsOf(r, p);
    // Изменившиеся документы видят автор и тот, кто отправил маршрут; остальным null.
    const managing = manages(r, user);
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
        new_version: r.lastChanged.some((doc) =>
          approvalDocs(r, p).includes(doc),
        ),
      },
      steps: r.steps.map((step) =>
        step.map((q) => ({
          name: q.name,
          persona: q.persona,
          state: stateOf(r, q),
          at: approved(r, q) ? (q.approval?.at ?? null) : null,
          me: q === p,
          card_name: q.name,
          changes_visible: changesVisible(r, q),
        })),
      ),
      me: {
        participant_id: p.id,
        state: stateOf(r, p),
        next_action: nextActionOf(r, p),
        methods: allowedMethods(r, p),
        method: mine.length > 0 ? p.method : null,
        image_ready: p.imageReady,
        image_url: p.imageReady
          ? `/api/v1/projects/${encodeURIComponent(r.project_id)}/signing-routes/${encodeURIComponent(r.id)}/task/image`
          : null,
        plate: p.plate,
        keys: {
          server_keys_allowed: serverKeysAllowed(),
          default_key: defaultKey(user),
        },
        optional:
          remainingPairs(r, p).length > 0 &&
          remainingPairs(r, p).every((pair) => pairOptional(r, pair)),
      },
      docs: docsOf(r, p).map((docId) => {
        const doc = r.profile.docs.find((d) => d.doc_id === docId);
        const pairs = pairsOf(r).filter((pair) => pair.doc_id === docId);
        return {
          doc_id: docId,
          name: doc?.name ?? {},
          pdf_url: isDocFrozen(r, docId)
            ? `${pdfBase(docId)}/frozen/pdf`
            : `${pdfBase(docId)}/pdf/signed`,
          frozen: isDocFrozen(r, docId),
          token: tokenFor(r, p, docId),
          mine: pairs
            .filter((pair) => pair.persona === p.persona)
            .map((pair) => {
              const status = slotStatus(r, pair);
              return {
                ...slotPlace(pair, p.method),
                status,
                optional: pairOptional(r, pair),
                reason:
                  status === "signed" || status === "skipped"
                    ? null
                    : approvedDoc(r, p, docId)
                      ? "no_signature_file"
                      : "awaiting_approval",
              };
            }),
          others: pairs
            .filter((pair) => pair.persona !== p.persona)
            .map((pair) => ({
              ...slotPlace(
                pair,
                participants(r).find((q) => q.persona === pair.persona)
                  ?.method ?? pair.method,
              ),
              status: slotStatus(r, pair),
            })),
          sent_at: r.pinned[docId]?.at ?? null,
          changed_since_mine:
            p.approval?.tokens[docId] !== undefined &&
            p.approval.tokens[docId] !== sentToken(r, docId),
          changed: managing ? isChanged(r, docId) : null,
        };
      }),
      events: [...r.events],
    };
  };

  const blockersOf = (
    r: Route,
    user: SigningDemoUser,
  ): SigningRouteBlocker[] => {
    const blockers: SigningRouteBlocker[] = [];
    // Отправка и есть согласие отправителя: его картинка или данные плашки нужны заранее.
    const sender = r.steps[0]?.find((p) => p.user_id === user.id);
    if (
      sender &&
      assignmentsOf(r, sender).length > 0 &&
      ((sender.method === "image" && !sender.imageReady) ||
        (isCrypto(sender.method) && sender.plate === null))
    )
      blockers.push({
        code: "sender_not_ready",
        doc_id: null,
        slot_id: null,
        participant_id: sender.id,
        other_route: null,
      });
    for (const p of participants(r)) {
      if (membershipOf(p) === "missing")
        blockers.push({
          code: "participant_missing",
          doc_id: null,
          slot_id: null,
          participant_id: p.id,
          other_route: null,
        });
    }
    for (const pair of pairsOf(r)) {
      if (!participants(r).some((p) => p.persona === pair.persona))
        blockers.push({
          code: "slot_unassigned",
          doc_id: pair.doc_id,
          slot_id: pair.slot_id,
          participant_id: null,
          other_route: null,
        });
    }
    if (participants(r).length === 0)
      blockers.push({
        code: "no_participants",
        doc_id: null,
        slot_id: null,
        participant_id: null,
        other_route: null,
      });
    // Картинке и плашке нужно место на странице: без него слот не подписать.
    for (const p of participants(r)) {
      if (p.method === "pades") continue;
      for (const pair of assignmentsOf(r, p)) {
        if (!isPlaced(r.project_id, pair.doc_id, pair.slot_id))
          blockers.push({
            code: "placement_off",
            doc_id: pair.doc_id,
            slot_id: pair.slot_id,
            participant_id: p.id,
            other_route: null,
          });
      }
    }
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

  /** Кандидат отправки (12.6): рабочая сборка каждого документа. */
  const candidateOf = (r: Route): Record<string, string> =>
    Object.fromEntries(
      routeDocs(r).map((doc) => [doc, `build:${r.build[doc] ?? ""}`]),
    );

  const changeOf = (r: Route, docId: string): RouteDocChange => {
    const sent = r.pinned[docId];
    if (!sent) return "new";
    return sent.sha256 === r.build[docId] ? "same" : "changed";
  };

  /**
   * Пропущенные, чьи пары уже не все необязательны (отметку сняли после пропуска): новый раунд
   * вернёт их в маршрут (13.3).
   */
  const returning = (r: Route): Participant[] =>
    participants(r).filter(
      (p) =>
        p.skipped !== null &&
        !assignmentsOf(r, p).every((pair) => pairOptional(r, pair)),
    );

  /**
   * Идущий и завершённый маршрут отправляют только новую версию: без изменений нечего, если
   * некого вернуть из пропуска.
   */
  const nothingToSend = (r: Route): boolean =>
    (r.status === "active" || r.status === "completed") &&
    changedDocs(r).length === 0 &&
    returning(r).length === 0;

  const toPreview = (r: Route, user: SigningDemoUser): SigningRoutePreview => {
    const candidate = candidateOf(r);
    const blockers = blockersOf(r, user);
    if (nothingToSend(r))
      blockers.push({
        code: "nothing_changed",
        doc_id: null,
        slot_id: null,
        participant_id: null,
        other_route: null,
      });
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
        token: candidate[doc.doc_id] ?? null,
        change: changeOf(r, doc.doc_id),
        sent: r.pinned[doc.doc_id] ?? null,
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
          keeps_approval:
            p.approval !== null &&
            approvalDocs(r, p).every(
              (doc) => p.approval?.tokens[doc] === candidate[doc],
            ),
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
    signed: {},
    returnedRound: null,
    // Картинка автора уже стоит в его слоте проекта; данные плашки известны из профиля.
    imageReady: who.user_id !== null && who.user_id === authors.get(r.id)?.id,
    plate: members.find((m) => m.user_id === who.user_id)?.plate ?? null,
    notified_at: null,
    reminded_at: null,
    reminders: 0,
    skipped: null,
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

  /** Человек персоны, как `pick_person` сервера: автор, участник проекта, приглашение или никто. */
  const byPersona = (
    persona: string,
    author: SigningDemoUser,
  ): Pick<Participant, "user_id" | "invitation_id" | "name"> => {
    if (persona === "author")
      return { user_id: author.id, invitation_id: null, name: author.name };
    const member = members.find((m) => m.persona === persona);
    if (member)
      return {
        user_id: member.user_id,
        invitation_id: null,
        name: member.name,
      };
    const inv = invitations.find((i) => i.persona === persona);
    return inv
      ? { user_id: null, invitation_id: inv.invitation_id, name: inv.hint }
      : { user_id: null, invitation_id: null, name: null };
  };

  /** Как R5 в PUT: человек персоны, которого ещё нет среди людей правки; никого: «нет в проекте». */
  const unusedByPersona = (
    persona: string,
    author: SigningDemoUser,
    drafts: { user_id: string | null; invitation_id: string | null }[],
  ): Pick<Participant, "user_id" | "invitation_id" | "name"> => {
    const users = new Set(drafts.map((d) => d.user_id).filter(Boolean));
    const invited = new Set(drafts.map((d) => d.invitation_id).filter(Boolean));
    if (persona === "author" && !users.has(author.id))
      return { user_id: author.id, invitation_id: null, name: author.name };
    const member = members.find(
      (m) => m.persona === persona && !users.has(m.user_id),
    );
    if (member)
      return {
        user_id: member.user_id,
        invitation_id: null,
        name: member.name,
      };
    const inv = invitations.find(
      (i) => i.persona === persona && !invited.has(i.invitation_id),
    );
    return inv
      ? { user_id: null, invitation_id: inv.invitation_id, name: inv.hint }
      : { user_id: null, invitation_id: null, name: null };
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
      pinned: {},
      legacy: {},
      lastChanged: [],
      frozen: {},
      events: [],
    };
    authors.set(r.id, author);
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
      step.map((persona) =>
        makeParticipant(r, persona, byPersona(persona, author)),
      ),
    );
    return r;
  };

  /** Задачи «На подпись»: идущие маршруты, где сейчас ждут действия человека. */
  const tasksOf = (userId: string): SigningTaskSummary[] => {
    const items: SigningTaskSummary[] = [];
    for (const r of routes) {
      if (r.status !== "active") continue;
      for (const p of participants(r)) {
        if (p.user_id !== userId) continue;
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
    return items;
  };

  /**
   * Отправить, отправить заново или отправить новую версию (12.6); `sign`: отправитель сразу
   * подписывает свои слоты ЭП, `note`: «Что изменилось» вместо сообщения маршрута.
   */
  const sendRoute = (
    r: Route,
    user: SigningDemoUser,
    sign: boolean,
    note: string | null = null,
  ): void => {
    const previous = r.round;
    // Версия на подписи снимается только у изменившихся документов; у остальных остаются
    // `pinned_at`, B и подписи над ним.
    const changed = routeDocs(r).filter(
      (doc) =>
        r.pinned[doc] !== undefined && r.pinned[doc].sha256 !== r.build[doc],
    );
    r.round += 1;
    for (const doc of routeDocs(r)) {
      if (r.pinned[doc]?.sha256 === r.build[doc]) continue;
      r.pinned[doc] = { sha256: r.build[doc] ?? "", at: now(), round: r.round };
      unfreeze(r, doc);
    }
    r.legacy = {};
    r.lastChanged = changed;
    r.status = "active";
    r.stop_reason = null;
    r.sent_by = user;
    r.sent_at = now();
    r.completed_at = null;
    if (note !== null) r.message = note;
    // Пропуск переносится, пока все пары участника необязательны; иначе он возвращается в маршрут,
    // и документы с его видимой меткой фиксируются заново, уже с ней.
    const back = new Set(returning(r));
    for (const p of participants(r)) {
      if (p.skipped === null) continue;
      if (back.has(p)) {
        p.skipped = null;
        if (canChangeVisual(p))
          for (const doc of docsOf(r, p)) unfreeze(r, doc);
      } else p.skipped = { ...p.skipped, round: r.round };
    }
    for (const p of participants(r)) {
      p.returnedRound = null;
      p.notified_at = null;
      p.reminders = 0;
      p.reminded_at = null;
      // Согласие переносится всегда, действует по документам с прежними отпечатками.
      if (p.approval) p.approval = { ...p.approval, round: r.round };
    }
    // Отправка и есть согласие отправителя.
    const tokens = Object.fromEntries(
      routeDocs(r).map((doc) => [doc, sentToken(r, doc)]),
    );
    for (const p of r.steps[0] ?? []) {
      if (p.user_id === user.id)
        p.approval = { round: r.round, at: now(), tokens };
    }
    // Первая отправка и новая версия пишут `sent`, «Отправить заново» без изменений `resumed`.
    if (previous === 0) event(r, "sent", user.name);
    else if (changed.length > 0)
      event(r, "sent", user.name, { changed_docs: changed });
    else event(r, "resumed", user.name);
    settle(r);
    if (sign && isFrozen(r)) {
      for (const p of r.steps[0] ?? []) {
        if (p.user_id === user.id && isCrypto(p.method)) {
          signAll(r, p);
          event(r, "signed", user.name, { participant_id: p.id });
        }
      }
      settle(r);
    }
  };

  /** Ссылка приглашения с переходом на страницу подписи; каждый раз новая, как у сервера. */
  const invitationLink = (r: Route): string => {
    seq += 1;
    const next = encodeURIComponent(`/sign/${r.project_id}/${r.id}`);
    return `${window.location.origin}/project-invite/hspi_demo_ok${String(seq)}?next=${next}`;
  };

  /** Пересборка с другим PDF: маршрут идёт дальше, версия на подписи та же (12.5). */
  const rebuildDoc = (r: Route, docId: string): void => {
    r.build[docId] = sha(`${r.build[docId] ?? ""}:rebuilt`);
    r.updated_at = now();
  };

  /**
   * Перенос маршрута 0.20.0 (12.11): сборка с отпечатком снимка становится версией на подписи от
   * `sent_at`; иначе версию не восстановить (архива сборок в демо нет), идущий маршрут встаёт
   * с `sent_changed`.
   */
  const migrate = (r: Route): void => {
    const lost: string[] = [];
    for (const [doc, snapshot] of Object.entries(r.legacy)) {
      if (r.build[doc] !== snapshot) {
        lost.push(doc);
        continue;
      }
      r.pinned[doc] = {
        sha256: snapshot,
        at: r.sent_at ?? now(),
        round: Math.max(r.round, 1),
      };
    }
    r.legacy = Object.fromEntries(
      Object.entries(r.legacy).filter(([doc]) => lost.includes(doc)),
    );
    if (
      lost.length > 0 &&
      (r.status === "active" || r.status === "completed")
    ) {
      r.status = "paused";
      r.stop_reason = "sent_changed";
      r.frozen = {};
      event(r, "paused", null, { reason: "sent_changed" });
    }
  };

  /** Последняя версия на подписи документа в проекте: её отдаёт план и снимает «Подписывать текущую сборку». */
  const pinnedOf = (
    projectId: string,
    docId: string,
  ): { route: Route; version: RouteDocVersion } | null => {
    const holder = routes
      .filter((r) => r.project_id === projectId && r.pinned[docId])
      .sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
    const version = holder?.pinned[docId];
    return holder && version ? { route: holder, version } : null;
  };

  const HOLDING: SigningRouteStatus[] = [
    "active",
    "paused",
    "returned",
    "completed",
  ];

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
    // Документ без отпечатка (делать по нему нечего) не сверяется.
    const changed = Object.entries(tokens)
      .filter(([doc, token]) => token !== null && expected[doc] !== token)
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
    return r.status === "active" && states.includes(stateOf(r, p))
      ? null
      : conflict("not_your_turn", "It is not your turn in the signing route");
  };

  /** После фиксации картинку и данные плашки менять нельзя: это изменило бы зафиксированный PDF. */
  const layerFinal = () =>
    conflict(
      "visible_layer_final",
      "The documents are already frozen: the image and the plate cannot be changed",
    );

  const formFile = (body: unknown): boolean =>
    typeof FormData !== "undefined" &&
    body instanceof FormData &&
    body.get("file") !== null;

  const handlers: DemoRoute[] = [
    {
      // Маршрут документа в его плане подписей (раздел 6.1): по нему редактор документа
      // показывает плашку «на подписании». Сам план демо маршрутов не считает, поэтому
      // отвечает только на запрос по документу.
      method: "GET",
      pattern: "/projects/:projectId/signature-plan",
      handler: signedIn((req, { projectId }) => {
        const docId = queryString(req, "doc_id");
        if (docId === null) return notFound();
        const holder = routes.find(
          (r) =>
            r.project_id === projectId &&
            HOLDING.includes(r.status) &&
            routeDocs(r).includes(docId),
        );
        // Версия на подписи переживает маршрут (12.4): план документа отдаёт её и без него.
        const pinned = pinnedOf(projectId, docId);
        return demoJson({
          profile_id: null,
          total: 0,
          signed: 0,
          crypto_total: 0,
          crypto_signed: 0,
          waiting_for_me: 0,
          docs: pinned
            ? [
                {
                  doc_id: docId,
                  built: true,
                  frozen: null,
                  slots: [],
                  held_by_route: holder?.status === "active",
                  pinned: {
                    sha256: pinned.version.sha256,
                    pinned_at: pinned.version.at,
                    route_id: pinned.route.id,
                    round: pinned.version.round,
                  },
                  working_differs:
                    pinned.route.build[docId] !== pinned.version.sha256,
                },
              ]
            : [],
          route: holder
            ? {
                id: holder.id,
                profile_id: holder.profile.id,
                status: holder.status,
                phase: toRoute(holder).phase,
                round: holder.round,
                current_step: currentStep(holder),
                steps_total: holder.steps.length,
                stop_reason: holder.stop_reason,
                changed_docs: changedDocs(holder),
              }
            : null,
        });
      }),
    },
    {
      // «Подписывать текущую сборку» (12.4): только пока документ не держит маршрут.
      method: "DELETE",
      pattern: "/projects/:projectId/docs/:docId/pinned",
      handler: signedIn((req, { projectId }) => {
        const docId = req.params.docId ?? "";
        const held = routes.some(
          (r) =>
            r.project_id === projectId &&
            HOLDING.includes(r.status) &&
            routeDocs(r).includes(docId),
        );
        if (held)
          return conflict(
            "route_locked",
            "The document is held by a signing route",
          );
        for (const r of routes) {
          if (r.project_id !== projectId) continue;
          const { [docId]: _dropped, ...rest } = r.pinned;
          r.pinned = rest;
        }
        return demoNoContent();
      }),
    },
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
        if (open) return demoJson(toRoute(open, user));
        // Новый маршрут точки снимает с контроля завершённый и отменённый (5.3).
        for (const r of routes) {
          if (
            r.project_id === projectId &&
            r.profile.id === profile.id &&
            (r.status === "completed" || r.status === "cancelled")
          ) {
            r.status = "archived";
            r.updated_at = now();
          }
        }
        const r = draftFromPack(projectId, profile, user);
        routes.push(r);
        return demoJson(toRoute(r, user), 201);
      }),
    },
    {
      method: "GET",
      pattern: "/projects/:projectId/signing-routes/:routeId",
      handler: withRoute((_req, r, { user }) => demoJson(toRoute(r, user))),
    },
    {
      method: "PUT",
      pattern: "/projects/:projectId/signing-routes/:routeId",
      handler: withRoute((req, r, { user }) => {
        if (!["draft", "paused", "returned", "cancelled"].includes(r.status))
          return conflict(
            "invalid_transition",
            "Cancel the signing route to change it",
          );
        const body = parse(UpdateSigningRouteRequestSchema, req.body);
        if (!body) return invalid("Invalid signing route");
        const author = authors.get(r.id) ?? { id: "", name: "" };
        const known = new Map(participants(r).map((p) => [p.id, p]));
        r.steps = body.steps.map((step) =>
          step.map((draft) => {
            const old = draft.id === null ? undefined : known.get(draft.id);
            const who =
              draft.user_id === null && draft.invitation_id === null
                ? unusedByPersona(draft.persona, author, body.steps.flat())
                : resolvePerson(draft.user_id, draft.invitation_id, author);
            if (old?.persona === draft.persona) {
              const same =
                old.user_id === who.user_id &&
                old.invitation_id === who.invitation_id;
              return same
                ? old
                : makeParticipant(r, draft.persona, who, old.id);
            }
            return makeParticipant(r, draft.persona, who);
          }),
        );
        r.extra = body.extra_slots;
        r.deadline = body.deadline;
        r.message = body.message;
        r.updated_at = now();
        // Как R5: необязательному слоту без участника с его персоной правка добавляет
        // участника отдельным последним шагом, человека находит по персоне.
        const lacking = [
          ...new Set(
            pairsOf(r)
              .filter((pair) => pair.extra)
              .map((pair) => pair.persona),
          ),
        ].filter(
          (persona) => !participants(r).some((p) => p.persona === persona),
        );
        for (const persona of lacking)
          r.steps.push([
            makeParticipant(r, persona, byPersona(persona, author)),
          ]);
        for (const p of participants(r)) {
          if (assignmentsOf(r, p).length > 0 && p.method === null)
            p.method = defaultMethod(r, p.persona);
        }
        return demoJson(toRoute(r, user));
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
        if (r.status === "archived")
          return conflict("invalid_transition", "The route is archived");
        const body = parse(SendSigningRouteRequestSchema, req.body);
        if (!body) return invalid("Invalid send request");
        if (nothingToSend(r))
          return conflict(
            "nothing_changed",
            "The documents have not changed since they were sent",
          );
        const blockers = blockersOf(r, user);
        if (blockers.length > 0)
          return conflict("route_blocked", "The route cannot be sent", {
            blockers,
          });
        const mismatch = checkExpected(r, body.expected, candidateOf(r));
        if (mismatch) return mismatch;
        // Ключ проверяется до отправки: отказ на этом этапе ничего не меняет.
        const refused = body.sign === null ? null : refuseKey(user, body.sign);
        if (refused) return refused;
        // Подпись отказала уже после отправки: маршрут ушёл, подписи отправителя нет.
        const broken = body.sign?.passphrase === "broken";
        const note = body.note?.trim() ? body.note.trim() : null;
        sendRoute(r, user, body.sign !== null && !broken, note);
        if (broken && isFrozen(r))
          return demoError(400, "sign_failed", "The key refused to sign", {
            sent: true,
          });
        return demoJson(toRoute(r, user));
      }),
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/signing-routes/:routeId/cancel",
      handler: withRoute((_req, r, { user }) => {
        if (!["draft", "active", "paused", "returned"].includes(r.status))
          return conflict("invalid_transition", "The route is already closed");
        r.status = "cancelled";
        r.stop_reason = null;
        // Отмена снимает версии на подписи (12.4): документ снова подписывается по текущей сборке.
        r.pinned = {};
        r.legacy = {};
        r.frozen = {};
        event(r, "cancelled", user.name);
        return demoJson(toRoute(r, user));
      }),
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/signing-routes/:routeId/archive",
      handler: withRoute((_req, r, { user }) => {
        if (r.status !== "completed")
          return conflict(
            "invalid_transition",
            "Only a completed route can be archived",
          );
        r.status = "archived";
        r.updated_at = now();
        return demoJson(toRoute(r, user));
      }),
    },
    {
      // Пропуск участника автором (13.6): без тела, коды `participant_not_skippable` с `reason`.
      method: "POST",
      pattern:
        "/projects/:projectId/signing-routes/:routeId/participants/:participantId/skip",
      handler: withRoute((req, r, { user }) => {
        const p = participants(r).find(
          (q) => q.id === req.params.participantId,
        );
        if (!p) return notFound();
        if (!manages(r, user))
          return demoError(403, "forbidden", "Only the route author can skip");
        if (r.status !== "active")
          return conflict("invalid_transition", "The route is not running");
        const view = skipOf(r, p);
        if (view.blocker !== null) {
          const slots =
            view.blocker === "required_slots"
              ? remainingPairs(r, p).filter((pair) => !pairOptional(r, pair))
              : [];
          return conflict(
            "participant_not_skippable",
            "This participant cannot be skipped",
            { reason: view.blocker, slots },
          );
        }
        // Метка уходит из B без ЭП над ним: документ фиксируется заново тем же расчётом.
        for (const doc of view.refreezes) unfreeze(r, doc);
        p.skipped = {
          round: r.round,
          at: now(),
          pairs: remainingPairs(r, p),
          kept: view.keeps_marks,
        };
        event(r, "skipped", user.name, { participant_id: p.id });
        settle(r);
        return demoJson(toRoute(r, user));
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
        const state = stateOf(r, p);
        const turn =
          r.status === "active" &&
          (state === "to_approve" ||
            state === "to_approve_sign" ||
            state === "to_sign" ||
            state === "invited");
        if (!turn)
          return conflict("participant_not_waiting", "Nothing to remind about");
        // Без почты приглашённому напомнить нечем: автор получает ссылку, без пауз и отметок.
        if (state === "invited" && !mailEnabled()) {
          const manual: SigningReminder = {
            participant_id: p.id,
            delivery: "manual",
            link: invitationLink(r),
          };
          return demoJson(manual);
        }
        const last = p.reminded_at === null ? null : Date.parse(p.reminded_at);
        const interval = 12 * 60 * 60 * 1000;
        if (last !== null && clock() - last < interval)
          return demoError(429, "rate_limited", "Too many reminders", {
            retry_after: Math.ceil((last + interval - clock()) / 1000),
          });
        p.reminded_at = now();
        p.reminders += 1;
        event(r, state === "invited" ? "invited" : "reminded", user.name);
        const reminder: SigningReminder = {
          participant_id: p.id,
          delivery: state === "invited" || mailEnabled() ? "email" : "inbox",
          link: null,
        };
        return demoJson(reminder);
      }),
    },
    {
      method: "POST",
      pattern:
        "/projects/:projectId/signing-routes/:routeId/participants/:participantId/link",
      handler: withRoute((req, r) => {
        const p = participants(r).find(
          (q) => q.id === req.params.participantId,
        );
        if (!p) return notFound();
        if (p.user_id !== null) {
          const page: SigningLink = {
            participant_id: p.id,
            kind: "page",
            link: `${window.location.origin}/sign/${r.project_id}/${r.id}`,
          };
          return demoJson(page);
        }
        if (p.invitation_id === null)
          return conflict(
            "participant_not_waiting",
            "Nobody to send a link to",
          );
        if (mailEnabled())
          return conflict(
            "link_by_mail",
            "The invitation link is sent by email: press “Remind” to send it again",
          );
        const invitation: SigningLink = {
          participant_id: p.id,
          kind: "invitation",
          link: invitationLink(r),
        };
        return demoJson(invitation);
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
        // Как в ядре: без картинки или данных плашки согласие не сдвинуло бы маршрут.
        if (p.method === "image" && !p.imageReady)
          return conflict("image_required", "Upload the signature image");
        if (isCrypto(p.method) && p.plate === null)
          return conflict(
            "plate_required",
            "Set the key or certificate for the plate",
          );
        // Ключ и пароль проверяются до согласия: отказ подписи ничего не меняет.
        if (combine && body.sign !== null && isCrypto(p.method)) {
          const refusedKey = refuseKey(user, body.sign);
          if (refusedKey) return refusedKey;
        }
        p.approval = {
          round: r.round,
          at: now(),
          tokens: Object.fromEntries(
            routeDocs(r).map((doc) => [doc, sentToken(r, doc)]),
          ),
        };
        event(r, "approved", user.name, { participant_id: p.id });
        settle(r);
        if (
          combine &&
          body.sign !== null &&
          isFrozen(r) &&
          isCrypto(p.method)
        ) {
          signAll(r, p);
          event(r, "signed", user.name, { participant_id: p.id });
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
        const refusedKey = refuseKey(user, body);
        if (refusedKey) return refusedKey;
        signAll(r, p);
        event(r, "signed", user.name, { participant_id: p.id });
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
          participant_id: p.id,
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
        if (isFrozen(r)) return layerFinal();
        if (!formFile(req.body)) return invalid("Image file is required");
        const form = req.body as FormData;
        const image = form.get("file");
        if (form.get("remember") === "true" && image instanceof Blob)
          options.onRememberImage?.(user, image);
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
        if (isFrozen(r)) return layerFinal();
        const body = parse(SetSigningTaskPlateRequestSchema, req.body);
        if (!body) return invalid("identity_id is required");
        const key = findKey(user, body.identity_id);
        if (!key) return conflict("key_not_found", "Signing key not found");
        p.plate = {
          owner: key.signer,
          kind: key.kind === "openpgp" ? "openpgp" : "x509",
          cert_id: sha(body.identity_id).slice(0, 16).toUpperCase(),
        };
        r.updated_at = now();
        // Плашка с данными меняет видимый слой: возможно, менять его больше некому.
        settle(r);
        return demoJson(toTask(r, p, user));
      }),
    },
    {
      method: "POST",
      pattern: "/projects/:projectId/signing-routes/:routeId/task/plate/file",
      handler: withTask((req, r, p, { user }) => {
        const refused = needsTurn(r, p, ["to_approve", "to_approve_sign"]);
        if (refused) return refused;
        if (isFrozen(r)) return layerFinal();
        if (!formFile(req.body)) return invalid("Certificate file is required");
        p.plate = {
          owner: user.name,
          kind: "x509",
          cert_id: sha(user.id).slice(0, 16).toUpperCase(),
        };
        r.updated_at = now();
        settle(r);
        return demoJson(toTask(r, p, user));
      }),
    },
    {
      // Итоговый PDF для подписи у себя или плагином КриптоПро.
      method: "GET",
      pattern: "/projects/:projectId/docs/:docId/frozen/pdf",
      handler: signedIn((req, { projectId }) => {
        const docId = req.params.docId ?? "";
        const r = routes.find(
          (item) => item.project_id === projectId && isDocFrozen(item, docId),
        );
        if (!r) return notFound();
        const text = `%PDF-1.7 demo ${r.frozen[docId] ?? ""}`;
        return demoJson(new TextEncoder().encode(text).buffer);
      }),
    },
    {
      // Готовая открепленная подпись или подпись КриптоПро (существующий адрес плана
      // подписей): слот маршрута принимает её только от участника в его очередь (6.10).
      method: "POST",
      pattern: "/projects/:projectId/docs/:docId/detached/:slotId",
      handler: signedIn((req, { user, projectId }) => {
        const pair = {
          doc_id: req.params.docId ?? "",
          slot_id: req.params.slotId ?? "",
        };
        const owned = (r: Route, p: Participant) =>
          assignmentsOf(r, p).some(
            (a) => a.doc_id === pair.doc_id && a.slot_id === pair.slot_id,
          );
        const r = routes.find(
          (item) =>
            item.project_id === projectId &&
            item.status === "active" &&
            participants(item).some((p) => owned(item, p)),
        );
        if (!r) return notFound();
        const p = participants(r).find(
          (q) => q.user_id === user.id && owned(r, q),
        );
        if (!p || stateOf(r, p) !== "to_sign" || !isCrypto(p.method))
          return conflict(
            "not_your_turn",
            "It is not your turn in the signing route",
          );
        const form = req.body;
        const file =
          typeof FormData !== "undefined" && form instanceof FormData
            ? form.get("file")
            : null;
        if (!(file instanceof File))
          return invalid("Signature file is required");
        // Имя с «bad»: подпись сделана над другим файлом, слот остаётся без подписи.
        const valid = !/bad/i.test(file.name);
        if (valid) {
          const frozen = r.frozen[pair.doc_id];
          if (frozen !== undefined) p.signed[pair.doc_id] = frozen;
          event(r, "signed", user.name, { participant_id: p.id });
          settle(r);
        }
        return demoJson({
          signature: {
            format: /\.asc$/i.test(file.name) ? "openpgp" : "cms",
            origin: "uploaded",
            verdict: valid ? "valid" : "invalid",
            signer: p.plate?.owner ?? user.name,
            signer_id: sha(user.id),
            issuer: "",
            algorithm: "",
            signed_at: now(),
            not_before: null,
            not_after: null,
            chain: null,
            notes: [],
            added_at: now(),
            file_name: file.name,
            current: valid,
          },
        });
      }),
    },
    {
      method: "GET",
      pattern: "/account/signing-tasks",
      handler: signedIn((_req, { user }) =>
        demoJson({ items: tasksOf(user.id) }),
      ),
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
        if (r.project_id === projectId && docId in r.build)
          rebuildDoc(r, docId);
      }
    },
    tamper: (projectId, docId) => {
      for (const r of routes) {
        const version = r.pinned[docId];
        if (r.project_id !== projectId || !version) continue;
        r.pinned[docId] = { ...version, sha256: sha(`${version.sha256}:git`) };
        if (r.status !== "active" && r.status !== "completed") continue;
        r.status = "paused";
        r.stop_reason = "sent_changed";
        unfreeze(r, docId);
        event(r, "paused", null, { reason: "sent_changed" });
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
    taskCount: (userId) => tasksOf(userId).length,
    skippedOf: (projectId) => {
      const out: Record<string, Record<string, SkippedPair>> = {};
      for (const r of routes) {
        if (r.project_id !== projectId || !HOLDING.includes(r.status)) continue;
        for (const p of participants(r)) {
          if (!isSkipped(r, p) || p.skipped === null) continue;
          for (const pair of p.skipped.pairs) {
            out[pair.doc_id] = {
              ...out[pair.doc_id],
              [pair.slot_id]: {
                profile_id: r.profile.id,
                route_id: r.id,
                round: p.skipped.round,
                at: p.skipped.at,
                keep_mark: p.skipped.kept.includes(pair.doc_id),
              },
            };
          }
        }
      }
      return out;
    },
    extraBy: (projectId) => {
      const out: Record<string, Record<string, ProfileRef[]>> = {};
      for (const r of routes) {
        if (r.project_id !== projectId || r.status === "archived") continue;
        for (const pair of r.extra) {
          const byDoc = (out[pair.slot_id] ??= {});
          const refs = (byDoc[pair.doc_id] ??= []);
          if (!refs.some((ref) => ref.id === r.profile.id))
            refs.push({ id: r.profile.id, name: r.profile.name });
        }
      }
      return out;
    },
    isSlotSigned: (projectId, profileId, docId, slotId) =>
      routes.some(
        (r) =>
          r.project_id === projectId &&
          r.profile.id === profileId &&
          HOLDING.includes(r.status) &&
          pairsOf(r).some(
            (pair) =>
              pair.doc_id === docId &&
              pair.slot_id === slotId &&
              slotStatus(r, pair) === "signed",
          ),
      ),
    holdsDoc: (projectId, profileId, docId) =>
      routes.some(
        (r) =>
          r.project_id === projectId &&
          r.profile.id === profileId &&
          HOLDING.includes(r.status) &&
          routeDocs(r).includes(docId),
      ),
    seedOptional: ({ projectId, sender, signer, academic }) => {
      const profile = profiles[0];
      if (!profile) return null;
      const r = draftFromPack(projectId, profile, sender);
      for (const p of participants(r)) {
        if (p.persona !== "supervisor") continue;
        p.user_id = signer.id;
        p.invitation_id = null;
        p.name = signer.name;
      }
      // Академрук сверх точки: автор добавил его подпись сам, он идёт отдельным последним шагом.
      r.extra = profile.docs.flatMap((doc) =>
        doc.slots
          .filter((slot) => slot.extra)
          .map((slot) => ({ doc_id: doc.doc_id, slot_id: slot.slot_id })),
      );
      const persona = "academic_supervisor";
      r.steps.push([
        makeParticipant(r, persona, {
          user_id: academic.id,
          invitation_id: null,
          name: academic.name,
        }),
      ]);
      r.deadline = new Date(clock() + 2 * 24 * 60 * 60 * 1000).toISOString();
      r.message = "Прошу подписать заявление до пятницы.";
      routes.push(r);
      sendRoute(r, sender, false);
      const sup = participants(r).find((q) => q.persona === "supervisor");
      if (sup) {
        sup.approval = {
          round: r.round,
          at: now(),
          tokens: Object.fromEntries(
            routeDocs(r).map((doc) => [doc, sentToken(r, doc)]),
          ),
        };
        event(r, "approved", sup.name, { participant_id: sup.id });
        settle(r);
      }
      return r.id;
    },
    seed: ({
      projectId,
      profileId,
      sender,
      signer,
      persona,
      deadline,
      message,
      state = "sent",
    }) => {
      const profile =
        profiles.find((item) => item.id === profileId) ?? profiles[0];
      if (!profile) return null;
      const r = draftFromPack(projectId, profile, sender);
      // Подписант встаёт на свою персону вместо человека из заготовки.
      for (const p of participants(r)) {
        if (p.persona !== persona) continue;
        p.user_id = signer.id;
        p.invitation_id = null;
        p.name = signer.name;
        p.plate = null;
      }
      r.deadline = deadline ?? null;
      r.message = message ?? null;
      routes.push(r);
      sendRoute(r, sender, false);
      if (state === "diverged") {
        for (const doc of routeDocs(r)) rebuildDoc(r, doc);
      } else if (state === "new_version") {
        // Подписант согласовал (данные плашки уже известны), затем автор поправил документы и
        // отправил новую версию: подписант согласует заново изменившиеся документы.
        const p = participants(r).find((q) => q.user_id === signer.id);
        if (p) {
          p.plate = {
            owner: signer.name,
            kind: "openpgp",
            cert_id: sha(signer.id).slice(0, 16).toUpperCase(),
          };
          p.approval = {
            round: r.round,
            at: now(),
            tokens: Object.fromEntries(
              routeDocs(r).map((doc) => [doc, sentToken(r, doc)]),
            ),
          };
          event(r, "approved", signer.name, { participant_id: p.id });
          settle(r);
        }
        for (const doc of routeDocs(r)) rebuildDoc(r, doc);
        sendRoute(r, sender, false, message ?? null);
      } else if (state === "migrated" || state === "migration_lost") {
        // Маршрут 0.20.0: снимок вместо версии на подписи, затем перенос (12.11).
        r.legacy = Object.fromEntries(
          routeDocs(r).map((doc) => [doc, r.pinned[doc]?.sha256 ?? ""]),
        );
        r.pinned = {};
        if (state === "migration_lost")
          for (const doc of routeDocs(r)) rebuildDoc(r, doc);
        migrate(r);
      }
      return r.id;
    },
  };
};
