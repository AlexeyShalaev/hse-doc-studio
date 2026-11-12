import { demoError, demoJson } from "@shared/api/demo";
import type { DemoRoute } from "@shared/api/demo";
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

type Placement = {
  enabled: boolean;
  page: number;
  x_mm: number;
  y_mm: number;
  width_mm: number;
  sign_date: string | null;
};

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
          placements: placementsOf(projectId),
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
        doc[req.params.slotId ?? ""] = next;
        return demoJson(next);
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
    reset: () => {
      placements = new Map();
      optional = new Map();
    },
  };
};
