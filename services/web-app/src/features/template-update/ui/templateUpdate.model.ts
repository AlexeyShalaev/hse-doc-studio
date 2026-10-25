import type {
  AvailableUpdate,
  ConflictResolution,
  TemplateFileOp,
} from "@entities/template-update";

// Порядок строк в предпросмотре: сначала то, что требует решения, потом то,
// что задевает правки пользователя, в конце — молчаливые обновления.
const ACTION_ORDER = [
  "conflict",
  "merge",
  "orphan",
  "user_deleted",
  "update",
  "add",
  "delete",
  "ignored",
] as const;

export const sortOps = (ops: TemplateFileOp[]): TemplateFileOp[] =>
  [...ops].sort((a, b) => {
    const byAction =
      ACTION_ORDER.indexOf(a.action as (typeof ACTION_ORDER)[number]) -
      ACTION_ORDER.indexOf(b.action as (typeof ACTION_ORDER)[number]);
    return byAction !== 0 ? byAction : a.path.localeCompare(b.path);
  });

export const countOrder = (
  counts: Record<string, number>,
): [string, number][] =>
  ACTION_ORDER.filter((action) => (counts[action] ?? 0) > 0).map((action) => [
    action,
    counts[action] ?? 0,
  ]);

// Цвет метки действия: красный — решение за пользователем, жёлтый — правки
// пользователя участвуют, приглушённый — обновление молча.
export const actionTone = (action: string): string => {
  if (action === "conflict") return "var(--c-err)";
  if (action === "merge" || action === "orphan" || action === "user_deleted")
    return "var(--c-warn)";
  if (action === "add") return "var(--c-ok)";
  return "var(--fg-2)";
};

export const classTone = (updateClass: string | null | undefined): string =>
  updateClass === "major"
    ? "var(--c-err)"
    : updateClass === "minor"
      ? "var(--c-warn)"
      : "var(--c-ok)";

export const notesOf = (update: AvailableUpdate, lang: string): string[] => {
  const changes = update.version.changes;
  return changes[lang] ?? changes.ru ?? changes.en ?? [];
};

export const breakingOf = (update: AvailableUpdate, lang: string): string[] => {
  const notes = update.version.breaking_changes;
  return notes[lang] ?? notes.ru ?? notes.en ?? [];
};

export const defaultResolution = (op: TemplateFileOp): ConflictResolution =>
  op.resolutions.includes("mine") ? "mine" : "theirs";

// Карточка «Исправления шаблона» на обзоре: скрытая версия больше не
// предлагается, следующая — снова. Хранится в браузере: это удобство, а не данные.
const DISMISS_KEY = "hse-studio.template-update.dismissed";

const readDismissed = (): Record<string, string> => {
  try {
    const raw = localStorage.getItem(DISMISS_KEY);
    return raw ? (JSON.parse(raw) as Record<string, string>) : {};
  } catch {
    return {};
  }
};

export const isDismissed = (projectId: string, version: string): boolean =>
  readDismissed()[projectId] === version;

export const dismiss = (projectId: string, version: string): void => {
  try {
    localStorage.setItem(
      DISMISS_KEY,
      JSON.stringify({ ...readDismissed(), [projectId]: version }),
    );
  } catch {
    // Хранилище недоступно (приватный режим) — карточка просто вернётся.
  }
};
