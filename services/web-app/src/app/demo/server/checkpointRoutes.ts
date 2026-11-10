import { demoError, demoJson } from "@shared/api/demo";
import type { DemoRoute } from "@shared/api/demo";
import { DEMO_SIGNING_PROFILE } from "@entities/signing-route/testing";
import { effectiveRole } from "./projectAccess";
import type { ServerDemoWorld } from "./world";

// Точка сдачи «Заявка на тему КП» в серверном демо: профиль сдачи, подписи проекта и места
// слотов на странице. Без них экран точки пуст, и карточку «Подписание» (W3) и блок «Где
// подписи» редактора маршрута (W2) в браузере не открыть. Профиль тот же, что у демо маршрута
// (`DEMO_SIGNING_PROFILE`). Место подписи научрука сначала выключено: так в демо видна помеха
// отправки «подпись не размещена» и переход от неё к размещению.

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
  required_by: slot.optional
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
        .filter((slot) => !slot.optional)
        .map((slot) => slot.slot_id),
      skip_if_nda: false,
      supported_kinds: ["research", "project"],
    })),
    extra_items: [],
  },
];

export type CheckpointDemo = {
  routes: DemoRoute[];
  /** Включено ли место слота на странице документа (помеха отправки `placement_off`). */
  isPlaced: (projectId: string, docId: string, slotId: string) => boolean;
  reset: () => void;
};

export const createCheckpointDemo = (
  getWorld: () => ServerDemoWorld,
): CheckpointDemo => {
  let placements = new Map<string, Record<string, Record<string, Placement>>>();
  const placementsOf = (projectId: string) => {
    const found = placements.get(projectId);
    if (found) return found;
    const fresh = seedPlacements();
    placements.set(projectId, fresh);
    return fresh;
  };

  /** Проект виден вошедшему: иначе 404, как у остальных адресов проекта. */
  const visible = (projectId: string): boolean => {
    const world = getWorld();
    const project = world.projects.find((p) => p.summary.id === projectId);
    return (
      project !== undefined &&
      effectiveRole(world, project, world.bootstrap.user?.id) !== null
    );
  };

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
          runtime_slots: RUNTIME_SLOTS,
          // Демо картинок не придерживает: маршрут демо их не прячет.
          withheld: {},
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
  ];

  return {
    routes,
    isPlaced: (projectId, docId, slotId) =>
      placementsOf(projectId)[docId]?.[slotId]?.enabled === true,
    reset: () => {
      placements = new Map();
    },
  };
};
