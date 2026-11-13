import { demoError, demoJson } from "@shared/api/demo";
import type { DemoRoute } from "@shared/api/demo";
import {
  DATE_MARKS_MAX,
  RestorePlacementRequestSchema,
  SetDateMarksRequestSchema,
  formatDateMark,
  type DateMarkInput,
  type PlacementOrigin,
  type SignedAt,
} from "@entities/signature";
import type {
  RouteSlotRef,
  SigningTaskDateMark,
} from "@entities/signing-route";
import {
  DEMO_SIGNING_PROFILE,
  type SigningRouteDemo,
} from "@entities/signing-route/testing";
import type { NextDeadline } from "@entities/session";
import {
  SetCheckpointDeadlineRequestSchema,
  daysUntilDeadline,
  toMoscowIso,
  type DeadlineState,
} from "@entities/submission";
import { effectiveRole } from "./projectAccess";
import type { ServerDemoWorld } from "./world";

// Точка сдачи «Заявка на тему КП» в серверном демо: профиль сдачи, подписи проекта и места
// слотов на странице. Без них экран точки пуст, и карточку «Подписание» (W3) и блок «Где
// подписи» редактора маршрута (W2) в браузере не открыть. Профиль тот же, что у демо маршрута
// (`DEMO_SIGNING_PROFILE`). Место подписи научрука сначала выключено: так в демо видна помеха
// отправки «подпись не размещена» и переход от неё к размещению.
// Необязательные подписи (signing-route.md, 13): «Подпись необязательна» хранится здесь, в
// состоянии подписей проекта (`optional`), пропуски и слоты сверх точки берутся у демо маршрута.
// Подпись автора пак требует (`required`): отметить её нельзя.
// Дата подписания (signing-route.md, 14): метки даты и ручная дата хранятся в размещении, текст
// метки считается при чтении: у пары маршрута по моменту согласия (демо маршрута), вне маршрута по
// ручной дате. `PUT .../dates` отвечает кодами 14.7: на документе под маршрутом с ЭП над B без
// `confirm_reset` 409 `resets_signatures`, с ним B фиксируется заново и ЭП сбрасываются.
// Маршрут из шаблона (signing-route.md, 15): у слота место из пака по документу и метки даты
// (`default_placements`, `default_dates`), у размещения пометка «из шаблона» (`fromPack`) и
// происхождение в ответе (`origin`: как в шаблоне, затравка, изменено). Любая правка места или
// меток снимает пометку, «Вернуть место из шаблона» (`POST .../restore`) ставит место и метки из
// пака с теми же кодами, что у меток даты. Метки даты пака есть только у проекта на версии
// шаблона с пресетом (`hasPreset`).
// Сроки контрольных точек (signing-route.md, 16): срок точки хранится здесь по проектам, состояние
// считается при чтении правилами 16.6 (пакетов в демо нет, поэтому прошедший срок «просрочен»).
// У «Bertie» срок через 3 дня, у чужого проекта рецензента сегодня, у проекта читателя прошёл
// позавчера; у архивной «Практики» срока нет: на её точке видна строка «Срок сдачи не указан».

type StoredMark = Omit<DateMarkInput, "id"> & { id: string };

type Placement = {
  enabled: boolean;
  page: number;
  x_mm: number;
  y_mm: number;
  width_mm: number;
  sign_date: string | null;
  dates: StoredMark[];
  /** Ручная дата автора («2026-11-13»); у пары маршрута дату даёт согласие. */
  manual: string | null;
  /** Место поставил шаблон (`from_pack`, 15.4); правка человеком снимает пометку. */
  fromPack: boolean;
};

type Place = { page: number; x_mm: number; y_mm: number; width_mm: number };
type PackMark = Omit<DateMarkInput, "id">;

// Лист A4 документа демо и число страниц: рамки меток проверяются по ним (`bad_date_mark`).
const PAGE_W_MM = 210;
const PAGE_H_MM = 297;
const DOC_PAGES = 2;

type Body = Record<string, unknown>;

const DOC = DEMO_SIGNING_PROFILE.docs[0];
const UNPLACED = new Set(["supervisor", "academic_supervisor"]);

const notFound = () =>
  demoError(404, "not_found", "Project not found or no access");

/** Место слота на документе из пака (`placements` слота, иначе `default_placement`). */
const PACK_PLACES: Record<string, Record<string, Place>> = Object.fromEntries(
  (DOC?.slots ?? []).map((slot) => [
    slot.slot_id,
    Object.fromEntries(
      DEMO_SIGNING_PROFILE.docs.map((doc) => [
        doc.doc_id,
        {
          page: slot.page,
          x_mm: slot.x_mm,
          y_mm: slot.y_mm,
          width_mm: slot.width_mm,
        },
      ]),
    ),
  ]),
);

/**
 * Метки даты пака (`default_dates`, 14.10): «« 13 » ноября 2026 г.» под строкой научрука, как в
 * образце PDF демо. Только у версии шаблона с пресетом.
 */
const PACK_DATES: Record<string, Record<string, PackMark[]>> = {
  supervisor: {
    topic_application: [
      {
        page: 1,
        x_mm: 111.6,
        y_mm: 150,
        width_mm: 6.4,
        height_mm: 5,
        format: "day",
        align: "center",
      },
      {
        page: 1,
        x_mm: 122,
        y_mm: 150,
        width_mm: 23,
        height_mm: 5,
        format: "month_word",
        align: "center",
      },
      {
        page: 1,
        x_mm: 151.3,
        y_mm: 150,
        width_mm: 5,
        height_mm: 5,
        format: "year_short",
        align: "left",
      },
    ],
  },
};

const seedPlacements = (): Record<string, Record<string, Placement>> =>
  Object.fromEntries(
    DEMO_SIGNING_PROFILE.docs.map((doc) => [
      doc.doc_id,
      Object.fromEntries(
        doc.slots.map((slot) => [
          slot.slot_id,
          {
            enabled: !UNPLACED.has(slot.slot_id),
            page: slot.page,
            x_mm: slot.x_mm,
            y_mm: slot.y_mm,
            width_mm: slot.width_mm,
            sign_date: null,
            dates: [],
            manual: null,
            // Включённое место автора когда-то поставил шаблон; остальные затравки из пака.
            fromPack: !UNPLACED.has(slot.slot_id),
          },
        ]),
      ),
    ]),
  );

const round1 = (value: number): number => Math.round(value * 10) / 10;
const samePlace = (a: Place, b: Place): boolean =>
  a.page === b.page &&
  round1(a.x_mm) === round1(b.x_mm) &&
  round1(a.y_mm) === round1(b.y_mm) &&
  round1(a.width_mm) === round1(b.width_mm);
/** Метки без id в каноническом виде: порядок не важен, как у отпечатка сервера (15.4). */
const marksKey = (marks: readonly PackMark[]): string =>
  JSON.stringify(
    marks
      .map((m) =>
        [
          m.page,
          round1(m.x_mm),
          round1(m.y_mm),
          round1(m.width_mm),
          round1(m.height_mm),
          m.format,
          m.align,
        ].join(":"),
      )
      .sort(),
  );

const SLOTS = Object.fromEntries(
  (DOC?.slots ?? []).map((slot) => [
    slot.slot_id,
    {
      // Картинка автора уже загружена: демо маршрута считает её готовой.
      png_path:
        slot.persona === "author" ? ".hse-studio/signatures/author.png" : null,
      natural_width_px: slot.persona === "author" ? 600 : null,
      natural_height_px: slot.persona === "author" ? 240 : null,
      signing_identity_id: null,
      sign_mode: slot.method === "detached" ? "detached_text" : "image",
      sign_reason: "",
      signer: null,
    },
  ]),
);

const RUNTIME_SLOTS = (DOC?.slots ?? []).map((slot) => ({
  id: slot.slot_id,
  label: slot.label,
  applies_to: DEMO_SIGNING_PROFILE.docs.map((doc) => doc.doc_id),
  required: slot.required ?? false,
  required_by: slot.extra
    ? {}
    : Object.fromEntries(
        DEMO_SIGNING_PROFILE.docs.map((doc) => [
          doc.doc_id,
          [{ id: DEMO_SIGNING_PROFILE.id, name: DEMO_SIGNING_PROFILE.name }],
        ]),
      ),
  default_placement: {
    page: slot.page,
    x_mm: slot.x_mm,
    y_mm: slot.y_mm,
    width_mm: slot.width_mm,
  },
  default_placements: PACK_PLACES[slot.slot_id] ?? {},
  owner: null,
}));

const DAY_MS = 24 * 60 * 60 * 1000;
const MOSCOW_MS = 3 * 60 * 60 * 1000;

/** Подсказка пака к точке (16.4): текстом, без дат. */
const DEADLINE_HINT = {
  ru: "Обычно в середине ноября, точную дату объявляют в SmartLMS",
  en: "Usually mid-November; the exact date is announced in SmartLMS",
};

/** 23:59 по Москве через `days` календарных дней от `now`. */
const endOfMoscowDay = (now: number, days: number): string => {
  const day = Math.floor((now + MOSCOW_MS) / DAY_MS) + days;
  return toMoscowIso((day + 1) * DAY_MS - MOSCOW_MS - 60_000);
};

const seedDeadlines = (now: number): Map<string, Record<string, string>> =>
  new Map([
    ["p_01hxa1c4de", { [DEMO_SIGNING_PROFILE.id]: endOfMoscowDay(now, 3) }],
    ["p_01hxa2f8gh", { [DEMO_SIGNING_PROFILE.id]: endOfMoscowDay(now, 0) }],
    ["p_01hxa3k2jm", { [DEMO_SIGNING_PROFILE.id]: endOfMoscowDay(now, -2) }],
  ]);

/** Состояние срока по таблице 16.6: дни по календарю Москвы, пакет к сроку из `packagedAt`. */
export const demoDeadlineState = (
  deadline: string | null,
  packagedAt: string | null,
  now: number,
): DeadlineState => {
  if (deadline === null) return "none";
  const at = Date.parse(deadline);
  if (at <= now) return packagedAt === null ? "overdue" : "packaged";
  const days = daysUntilDeadline(deadline, now) ?? 0;
  if (days === 0) return "today";
  return days <= 3 ? "soon" : "upcoming";
};

/** Срок с поясом не раньше 2000 года, как требует сервер (`bad_deadline`, 16.8). */
const ZONED = /T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/;
const goodDeadline = (value: string): boolean => {
  const at = Date.parse(value);
  return (
    ZONED.test(value) &&
    !Number.isNaN(at) &&
    new Date(at).getUTCFullYear() >= 2000
  );
};

const PROFILE = {
  id: DEMO_SIGNING_PROFILE.id,
  name: DEMO_SIGNING_PROFILE.name,
};

const PROFILES = [
  {
    id: DEMO_SIGNING_PROFILE.id,
    name: DEMO_SIGNING_PROFILE.name,
    description: {
      ru: "Заявление о выборе темы с подписями студента и научного руководителя.",
      en: "Topic application signed by the student and the supervisor.",
    },
    items: DEMO_SIGNING_PROFILE.docs.map((doc) => ({
      doc_id: doc.doc_id,
      signatures: doc.slots
        .filter((slot) => !slot.extra)
        .map((slot) => slot.slot_id),
      skip_if_nda: false,
      supported_kinds: ["research", "project"],
      methods: Object.fromEntries(
        doc.slots
          .filter((slot) => !slot.extra)
          .map((slot) => [slot.slot_id, [slot.method]]),
      ),
    })),
    extra_items: [],
    deadline_hint: DEADLINE_HINT,
  },
];

export type CheckpointDemo = {
  routes: DemoRoute[];
  /** «Подпись необязательна» у слота документа на точке. */
  isOptional: (
    projectId: string,
    profileId: string,
    docId: string,
    slotId: string,
  ) => boolean;
  /** Отметить слот необязательным заранее, как будто автор уже поставил галочку. */
  setOptional: (
    projectId: string,
    profileId: string,
    docId: string,
    slotId: string,
    optional: boolean,
  ) => void;
  /** Включено ли место слота на странице документа (помеха отправки `placement_off`). */
  isPlaced: (projectId: string, docId: string, slotId: string) => boolean;
  /** Включить место слота заранее, как будто автор уже разместил подпись. */
  place: (projectId: string, docId: string, slotId: string) => void;
  /** Метки даты слота документа заранее; `manual` ручная дата слота вне маршрута. */
  setDates: (
    projectId: string,
    docId: string,
    slotId: string,
    marks: Omit<DateMarkInput, "id">[],
    manual?: string | null,
  ) => void;
  /**
   * Места пар из шаблона (15.5): там, где места нет, оно как в шаблоне или затравка, ставятся
   * место и метки даты пака, место включается; ручные места не трогаются.
   */
  placeFromPack: (projectId: string, pairs: RouteSlotRef[]) => void;
  /** Передвинуть место руками, как будто автор потянул рамку: место становится ручным. */
  move: (
    projectId: string,
    docId: string,
    slotId: string,
    place: Partial<Place>,
  ) => void;
  /** Метки даты для задачи подписанта: текст по моменту согласия `signedAt`. */
  datesOf: (
    projectId: string,
    docId: string,
    slotId: string,
    signedAt: string | null,
  ) => SigningTaskDateMark[];
  /** Срок точки проекта (16.3); null, если не указан. */
  deadlineOf: (projectId: string, profileId: string) => string | null;
  /** Поставить или снять срок заранее, как будто автор уже указал его. */
  setDeadline: (
    projectId: string,
    profileId: string,
    deadline: string | null,
  ) => void;
  /** Ближайший срок проекта для списка (16.6): `ProjectSummary.next_deadline`. */
  nextDeadlineOf: (projectId: string) => NextDeadline | null;
  reset: () => void;
};

type OptionalMap = Record<string, Record<string, string[]>>;

export const createCheckpointDemo = (
  getWorld: () => ServerDemoWorld,
  getRoutes: () => SigningRouteDemo,
  /** Проект на версии шаблона с пресетом: у слотов метки даты из пака. */
  hasPreset: (projectId: string) => boolean = () => false,
): CheckpointDemo => {
  let placements = new Map<string, Record<string, Record<string, Placement>>>();
  // Проект → точка → срок (ISO с поясом Москвы).
  let deadlines = seedDeadlines(Date.now());
  const deadlineOf = (projectId: string, profileId: string): string | null =>
    deadlines.get(projectId)?.[profileId] ?? null;
  const setDeadline = (
    projectId: string,
    profileId: string,
    deadline: string | null,
  ): void => {
    const { [profileId]: _old, ...rest } = deadlines.get(projectId) ?? {};
    deadlines.set(
      projectId,
      deadline === null ? rest : { ...rest, [profileId]: deadline },
    );
  };
  /** Точка со сроком в ответе: пакетов в демо нет, `packaged_at` всегда null. */
  const profilesOut = (projectId: string) =>
    PROFILES.map((profile) => {
      const deadline = deadlineOf(projectId, profile.id);
      return {
        ...profile,
        deadline,
        deadline_state: demoDeadlineState(deadline, null, Date.now()),
        packaged_at: null,
      };
    });
  const nextDeadlineOf = (projectId: string): NextDeadline | null => {
    const now = Date.now();
    const deadline = deadlineOf(projectId, PROFILE.id);
    if (deadline === null) return null;
    const state = demoDeadlineState(deadline, null, now);
    const at = Date.parse(deadline);
    // Ближайший будущий в 30 днях, иначе просрочка не старше 7 дней (16.6).
    const shown =
      state === "overdue"
        ? now - at <= 7 * DAY_MS
        : state !== "packaged" && at - now <= 30 * DAY_MS;
    return shown
      ? { profile_id: PROFILE.id, name: PROFILE.name, deadline, state }
      : null;
  };
  // Проект → документ → точка → необязательные слоты.
  let optional = new Map<string, OptionalMap>();
  const optionalOf = (projectId: string): OptionalMap => {
    const found = optional.get(projectId);
    if (found) return found;
    const fresh: OptionalMap = {};
    optional.set(projectId, fresh);
    return fresh;
  };
  const isOptional = (
    projectId: string,
    profileId: string,
    docId: string,
    slotId: string,
  ): boolean =>
    optionalOf(projectId)[docId]?.[profileId]?.includes(slotId) ?? false;
  const setOptional = (
    projectId: string,
    profileId: string,
    docId: string,
    slotId: string,
    value: boolean,
  ): void => {
    const byDoc = (optionalOf(projectId)[docId] ??= {});
    const rest = (byDoc[profileId] ?? []).filter((id) => id !== slotId);
    byDoc[profileId] = value ? [...rest, slotId] : rest;
  };
  const placementsOf = (projectId: string) => {
    const found = placements.get(projectId);
    if (found) return found;
    const fresh = seedPlacements();
    placements.set(projectId, fresh);
    return fresh;
  };

  const packDates = (
    projectId: string,
    docId: string,
    slotId: string,
  ): PackMark[] =>
    hasPreset(projectId) ? (PACK_DATES[slotId]?.[docId] ?? []) : [];
  /** Происхождение места (15.4): как в шаблоне, затравка из пака или изменено. */
  const originOf = (
    projectId: string,
    docId: string,
    slotId: string,
    p: Placement,
  ): PlacementOrigin => {
    const place = PACK_PLACES[slotId]?.[docId];
    if (!place || !samePlace(p, place)) return "manual";
    if (
      p.fromPack &&
      marksKey(p.dates) === marksKey(packDates(projectId, docId, slotId))
    )
      return "pack";
    return !p.fromPack &&
      !p.enabled &&
      p.dates.length === 0 &&
      p.sign_date === null &&
      p.manual === null
      ? "seed"
      : "manual";
  };
  /** Место и метки даты пака у размещения; `enabled` и ручная дата не меняются. */
  const fromPackOf = (
    projectId: string,
    docId: string,
    slotId: string,
    current: Placement,
  ): Placement | null => {
    const place = PACK_PLACES[slotId]?.[docId];
    if (!place) return null;
    return {
      ...current,
      ...place,
      dates: nextIds(
        packDates(projectId, docId, slotId).map((mark) => ({
          ...mark,
          id: null,
        })),
      ),
      fromPack: true,
    };
  };

  const langOf = (projectId: string): string =>
    getWorld().projects.find((p) => p.summary.id === projectId)?.summary.lang ??
    "ru";
  /** Момент подписи слота документа: согласие по маршруту или ручная дата. */
  const signedAtOf = (
    projectId: string,
    docId: string,
    slotId: string,
    placement: Placement,
  ): SignedAt | null => {
    const approved = getRoutes().approvedAt(projectId, docId, slotId);
    if (approved !== null) return { at: approved, source: "approval" };
    if (getRoutes().inRoute(projectId, docId, slotId)) return null;
    return placement.manual === null
      ? null
      : { at: placement.manual, source: "manual" };
  };
  /** Размещение в ответе: метки с текстом и момент подписи. */
  const placementOut = (
    projectId: string,
    docId: string,
    slotId: string,
    placement: Placement,
  ) => {
    const { manual: _manual, fromPack: _fromPack, ...rest } = placement;
    const signedAt = signedAtOf(projectId, docId, slotId, placement);
    const lang = langOf(projectId);
    return {
      ...rest,
      dates: placement.dates.map((mark) => ({
        ...mark,
        text:
          signedAt === null
            ? null
            : formatDateMark(signedAt.at, mark.format, lang),
      })),
      signed_at: signedAt,
      origin: originOf(projectId, docId, slotId, placement),
      preset_available: PACK_PLACES[slotId]?.[docId] !== undefined,
    };
  };
  const placementsOut = (projectId: string) =>
    Object.fromEntries(
      Object.entries(placementsOf(projectId)).map(([docId, slots]) => [
        docId,
        Object.fromEntries(
          Object.entries(slots).map(([slotId, placement]) => [
            slotId,
            placementOut(projectId, docId, slotId, placement),
          ]),
        ),
      ]),
    );
  /** Свободный id метки: d1, d2, … в пределах слота документа. */
  const nextIds = (marks: DateMarkInput[]): StoredMark[] => {
    const used = new Set(marks.flatMap((m) => (m.id === null ? [] : [m.id])));
    let n = 1;
    return marks.map((mark) => {
      if (mark.id !== null) return { ...mark, id: mark.id };
      while (used.has(`d${String(n)}`)) n += 1;
      const id = `d${String(n)}`;
      used.add(id);
      return { ...mark, id };
    });
  };
  /** Размещение без учёта порядка ключей: правка без изменений не пишется (14.6). */
  const canonical = (value: Placement): string =>
    JSON.stringify(value, (_key, item: unknown) =>
      item !== null && typeof item === "object" && !Array.isArray(item)
        ? Object.fromEntries(
            Object.entries(item).sort(([a], [b]) => (a < b ? -1 : 1)),
          )
        : item,
    );
  const badMark = (mark: DateMarkInput): boolean =>
    mark.page > DOC_PAGES ||
    mark.x_mm < 0 ||
    mark.y_mm < 0 ||
    mark.width_mm <= 0 ||
    mark.height_mm <= 0 ||
    mark.x_mm + mark.width_mm > PAGE_W_MM ||
    mark.y_mm + mark.height_mm > PAGE_H_MM;

  const roleIn = (projectId: string) => {
    const world = getWorld();
    const project = world.projects.find((p) => p.summary.id === projectId);
    return project === undefined
      ? null
      : effectiveRole(world, project, world.bootstrap.user?.id);
  };
  /** Проект виден вошедшему: иначе 404, как у остальных адресов проекта. */
  const visible = (projectId: string): boolean => roleIn(projectId) !== null;

  const guarded =
    (
      handler: (
        projectId: string,
        req: Parameters<DemoRoute["handler"]>[0],
      ) => ReturnType<DemoRoute["handler"]>,
    ): DemoRoute["handler"] =>
    (req) => {
      const projectId = req.params.projectId ?? "";
      return visible(projectId) ? handler(projectId, req) : notFound();
    };

  const routes: DemoRoute[] = [
    {
      method: "GET",
      pattern: "/projects/:projectId/submissions/profiles",
      handler: guarded((projectId) => demoJson(profilesOut(projectId))),
    },
    {
      // Срок контрольной точки (16.8): права как у сборки пакета, коды как у сервера.
      method: "PUT",
      pattern: "/projects/:projectId/submissions/profiles/:profileId/deadline",
      handler: guarded((projectId, req) => {
        const role = roleIn(projectId);
        if (role !== "owner" && role !== "editor")
          return demoError(403, "forbidden", "Not allowed to submit");
        const profileId = req.params.profileId ?? "";
        if (!PROFILES.some((p) => p.id === profileId))
          return demoError(404, "not_found", "Unknown checkpoint");
        const parsed = SetCheckpointDeadlineRequestSchema.safeParse(req.body);
        if (!parsed.success)
          return demoError(422, "validation_error", "Invalid request");
        const value = parsed.data.deadline;
        if (value !== null && !goodDeadline(value))
          return demoError(400, "bad_deadline", "Bad deadline");
        // Ответ в поясе Москвы, как у сервера.
        const deadline = value === null ? null : toMoscowIso(Date.parse(value));
        setDeadline(projectId, profileId, deadline);
        return demoJson({
          profile_id: profileId,
          deadline,
          state: demoDeadlineState(deadline, null, Date.now()),
          packaged_at: null,
        });
      }),
    },
    {
      method: "GET",
      pattern: "/projects/:projectId/submissions",
      handler: guarded(() => demoJson([])),
    },
    {
      method: "GET",
      pattern: "/projects/:projectId/forms",
      handler: guarded(() => demoJson({ forms: [] })),
    },
    {
      method: "GET",
      pattern: "/projects/:projectId/signatures",
      handler: guarded((projectId) =>
        demoJson({
          slots: SLOTS,
          placements: placementsOut(projectId),
          frozen: {},
          detached: {},
          runtime_slots: RUNTIME_SLOTS.map((slot) => ({
            ...slot,
            extra_by: getRoutes().extraBy(projectId)[slot.id] ?? {},
            default_dates: Object.fromEntries(
              slot.applies_to.flatMap((docId) => {
                const marks = packDates(projectId, docId, slot.id);
                return marks.length > 0 ? [[docId, marks]] : [];
              }),
            ),
          })),
          // Демо картинок не придерживает: маршрут демо их не прячет.
          withheld: {},
          optional: optionalOf(projectId),
          skipped: getRoutes().skippedOf(projectId),
        }),
      ),
    },
    {
      method: "PATCH",
      pattern: "/projects/:projectId/signatures/placements/:docId/:slotId",
      handler: guarded((projectId, req) => {
        const doc = placementsOf(projectId)[req.params.docId ?? ""];
        const current = doc?.[req.params.slotId ?? ""];
        if (!doc || !current) return notFound();
        const patch = (req.body ?? {}) as Body;
        const next: Placement = { ...current };
        if (typeof patch.enabled === "boolean") next.enabled = patch.enabled;
        for (const key of ["page", "x_mm", "y_mm", "width_mm"] as const) {
          const value = patch[key];
          if (typeof value === "number") next[key] = value;
        }
        if (typeof patch.sign_date === "string")
          next.sign_date = patch.sign_date === "" ? null : patch.sign_date;
        // Правка человеком снимает пометку «из шаблона»; запрос без изменений её сохраняет.
        if (canonical(next) !== canonical(current)) next.fromPack = false;
        const slotId = req.params.slotId ?? "";
        doc[slotId] = next;
        return demoJson(
          placementOut(projectId, req.params.docId ?? "", slotId, next),
        );
      }),
    },
    {
      // Метки даты слота документа целиком и ручная дата (14.7).
      method: "PUT",
      pattern:
        "/projects/:projectId/signatures/placements/:docId/:slotId/dates",
      handler: guarded((projectId, req) => {
        const role = roleIn(projectId);
        if (role !== "owner" && role !== "editor")
          return demoError(
            403,
            "forbidden",
            "Not allowed to change signatures",
          );
        const docId = req.params.docId ?? "";
        const slotId = req.params.slotId ?? "";
        const current = placementsOf(projectId)[docId]?.[slotId];
        if (!current) return notFound();
        const parsed = SetDateMarksRequestSchema.safeParse({
          confirm_reset: false,
          ...((req.body ?? {}) as Body),
        });
        if (!parsed.success)
          return demoError(422, "validation_error", "Invalid request");
        const body = parsed.data;
        if (body.dates.length > DATE_MARKS_MAX || body.dates.some(badMark))
          return demoError(400, "bad_date_mark", "Bad date mark");
        const routes = getRoutes();
        if (body.signed_at != null && routes.inRoute(projectId, docId, slotId))
          return demoError(
            409,
            "date_from_route",
            "The date of a route slot comes from its approval",
          );
        const next: Placement = {
          ...current,
          dates: nextIds(body.dates),
          manual:
            body.signed_at === undefined
              ? current.manual
              : (body.signed_at?.date ?? null),
        };
        // Без изменений сервер ничего не пишет: ни сброса подписей, ни события.
        if (canonical(next) === canonical(current))
          return demoJson(placementOut(projectId, docId, slotId, current));
        next.fromPack = false;
        const resets = routes.signedOver(projectId, docId);
        if (resets.length > 0 && !body.confirm_reset)
          return demoError(
            409,
            "resets_signatures",
            "Saving resets signatures over the frozen PDF",
            { resets },
          );
        placementsOf(projectId)[docId] = {
          ...placementsOf(projectId)[docId],
          [slotId]: next,
        };
        // Документ под маршрутом: правка идёт сценарием маршрута, в истории «изменил метки даты»
        // перед перефиксацией и завершением.
        routes.marksEdited(
          projectId,
          docId,
          slotId,
          getWorld().bootstrap.user?.name ?? null,
          resets.length > 0,
        );
        if (resets.length > 0) routes.refreeze(projectId, docId);
        return demoJson(placementOut(projectId, docId, slotId, next));
      }),
    },
    {
      // «Вернуть место из шаблона» (15.6, 15.11): права и коды как у меток даты.
      method: "POST",
      pattern:
        "/projects/:projectId/signatures/placements/:docId/:slotId/restore",
      handler: guarded((projectId, req) => {
        const role = roleIn(projectId);
        if (role !== "owner" && role !== "editor")
          return demoError(
            403,
            "forbidden",
            "Not allowed to change signatures",
          );
        const docId = req.params.docId ?? "";
        const slotId = req.params.slotId ?? "";
        const parsed = RestorePlacementRequestSchema.safeParse({
          confirm_reset: false,
          ...((req.body ?? {}) as Body),
        });
        if (!parsed.success)
          return demoError(422, "validation_error", "Invalid request");
        const current = placementsOf(projectId)[docId]?.[slotId];
        const next = current
          ? fromPackOf(projectId, docId, slotId, current)
          : null;
        if (!current || !next)
          return demoError(
            400,
            "unknown_slot",
            "The slot does not go on this document",
          );
        // Повтор без изменений ничего не пишет.
        if (originOf(projectId, docId, slotId, current) === "pack")
          return demoJson(placementOut(projectId, docId, slotId, current));
        const routes = getRoutes();
        const resets = routes.signedOver(projectId, docId);
        if (resets.length > 0 && !parsed.data.confirm_reset)
          return demoError(
            409,
            "resets_signatures",
            "Restoring resets signatures over the frozen PDF",
            { resets },
          );
        placementsOf(projectId)[docId] = {
          ...placementsOf(projectId)[docId],
          [slotId]: next,
        };
        if (resets.length > 0) routes.refreeze(projectId, docId);
        return demoJson(placementOut(projectId, docId, slotId, next));
      }),
    },
    {
      // «Подпись необязательна» (13.6): права как у отправки маршрута, коды как у сервера.
      method: "PUT",
      pattern: "/projects/:projectId/signatures/optional/:docId/:slotId",
      handler: guarded((projectId, req) => {
        const role = roleIn(projectId);
        if (role !== "owner" && role !== "editor")
          return demoError(
            403,
            "forbidden",
            "Not allowed to change signatures",
          );
        const body = (req.body ?? {}) as Body;
        const profileId = body.profile_id;
        const value = body.optional;
        if (typeof profileId !== "string" || typeof value !== "boolean")
          return demoError(422, "validation_error", "Invalid request");
        const docId = req.params.docId ?? "";
        const slotId = req.params.slotId ?? "";
        const slot = RUNTIME_SLOTS.find((s) => s.id === slotId);
        const routes = getRoutes();
        const onPoint =
          slot !== undefined &&
          slot.applies_to.includes(docId) &&
          ((slot.required_by[docId] ?? []).some((p) => p.id === profileId) ||
            (routes.extraBy(projectId)[slotId]?.[docId] ?? []).some(
              (p) => p.id === profileId,
            ));
        if (!onPoint)
          return demoError(
            400,
            "unknown_slot",
            "The slot is not on this checkpoint",
          );
        if (value && slot.required)
          return demoError(
            409,
            "optional_forbidden",
            "The template requires this signature",
          );
        if (value && routes.isSlotSigned(projectId, profileId, docId, slotId))
          return demoError(409, "slot_signed", "The slot is already signed");
        setOptional(projectId, profileId, docId, slotId, value);
        const skipped =
          routes.skippedOf(projectId)[docId]?.[slotId]?.profile_id ===
          profileId;
        return demoJson({
          doc_id: docId,
          slot_id: slotId,
          profile_id: profileId,
          optional: value,
          skipped,
          returns_next_round:
            !value && skipped && routes.holdsDoc(projectId, profileId, docId),
        });
      }),
    },
  ];

  return {
    routes,
    isOptional,
    setOptional,
    isPlaced: (projectId, docId, slotId) =>
      placementsOf(projectId)[docId]?.[slotId]?.enabled === true,
    place: (projectId, docId, slotId) => {
      const current = placementsOf(projectId)[docId]?.[slotId];
      if (!current) return;
      // Включённая затравка: место как будто поставил шаблон.
      if (originOf(projectId, docId, slotId, current) === "seed")
        current.fromPack = true;
      current.enabled = true;
    },
    setDates: (projectId, docId, slotId, marks, manual = null) => {
      const current = placementsOf(projectId)[docId]?.[slotId];
      if (!current) return;
      current.dates = nextIds(marks.map((mark) => ({ ...mark, id: null })));
      current.manual = manual;
      current.fromPack = false;
    },
    placeFromPack: (projectId, pairs) => {
      for (const pair of pairs) {
        const doc = (placementsOf(projectId)[pair.doc_id] ??= {});
        const current = doc[pair.slot_id];
        if (
          current &&
          originOf(projectId, pair.doc_id, pair.slot_id, current) === "manual"
        )
          continue;
        const base: Placement = current ?? {
          enabled: false,
          page: 1,
          x_mm: 0,
          y_mm: 0,
          width_mm: 40,
          sign_date: null,
          dates: [],
          manual: null,
          fromPack: false,
        };
        const next = fromPackOf(projectId, pair.doc_id, pair.slot_id, base);
        if (next) doc[pair.slot_id] = { ...next, enabled: true };
      }
    },
    move: (projectId, docId, slotId, place) => {
      const current = placementsOf(projectId)[docId]?.[slotId];
      if (!current) return;
      Object.assign(current, place, { fromPack: false });
    },
    datesOf: (projectId, docId, slotId, signedAt) => {
      const lang = langOf(projectId);
      return (placementsOf(projectId)[docId]?.[slotId]?.dates ?? []).map(
        (mark) => ({
          page: mark.page,
          x_mm: mark.x_mm,
          y_mm: mark.y_mm,
          width_mm: mark.width_mm,
          height_mm: mark.height_mm,
          text:
            signedAt === null
              ? null
              : formatDateMark(signedAt, mark.format, lang),
        }),
      );
    },
    deadlineOf,
    setDeadline,
    nextDeadlineOf,
    reset: () => {
      placements = new Map();
      optional = new Map();
      deadlines = seedDeadlines(Date.now());
    },
  };
};
