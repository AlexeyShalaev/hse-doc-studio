import { demoError, demoJson } from "@shared/api/demo";
import type { DemoRoute } from "@shared/api/demo";
import {
  DATE_MARKS_MAX,
  SetDateMarksRequestSchema,
  formatDateMark,
  type DateMarkInput,
  type SignedAt,
} from "@entities/signature";
import type { SigningTaskDateMark } from "@entities/signing-route";
import {
  DEMO_SIGNING_PROFILE,
  type SigningRouteDemo,
} from "@entities/signing-route/testing";
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
};

// Лист A4 документа демо и число страниц: рамки меток проверяются по ним (`bad_date_mark`).
const PAGE_W_MM = 210;
const PAGE_H_MM = 297;
const DOC_PAGES = 2;

type Body = Record<string, unknown>;

const DOC = DEMO_SIGNING_PROFILE.docs[0];
const UNPLACED = new Set(["supervisor", "academic_supervisor"]);

const notFound = () =>
  demoError(404, "not_found", "Project not found or no access");

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
          },
        ]),
      ),
    ]),
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
  owner: null,
}));

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
    })),
    extra_items: [],
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
  /** Метки даты для задачи подписанта: текст по моменту согласия `signedAt`. */
  datesOf: (
    projectId: string,
    docId: string,
    slotId: string,
    signedAt: string | null,
  ) => SigningTaskDateMark[];
  reset: () => void;
};

type OptionalMap = Record<string, Record<string, string[]>>;

export const createCheckpointDemo = (
  getWorld: () => ServerDemoWorld,
  getRoutes: () => SigningRouteDemo,
): CheckpointDemo => {
  let placements = new Map<string, Record<string, Record<string, Placement>>>();
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
    const { manual: _manual, ...rest } = placement;
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
      handler: guarded(() => demoJson(PROFILES)),
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
        const resets = routes.signedOver(projectId, docId);
        if (resets.length > 0 && !body.confirm_reset)
          return demoError(
            409,
            "resets_signatures",
            "Saving resets signatures over the frozen PDF",
            { resets },
          );
        const next: Placement = {
          ...current,
          dates: nextIds(body.dates),
          manual:
            body.signed_at === undefined
              ? current.manual
              : (body.signed_at?.date ?? null),
        };
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
      if (current) current.enabled = true;
    },
    setDates: (projectId, docId, slotId, marks, manual = null) => {
      const current = placementsOf(projectId)[docId]?.[slotId];
      if (!current) return;
      current.dates = nextIds(marks.map((mark) => ({ ...mark, id: null })));
      current.manual = manual;
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
    reset: () => {
      placements = new Map();
      optional = new Map();
    },
  };
};
