import {
  lintTargetOf,
  versionDirOf,
  versionRefOf,
  type PackCiStatus,
  type PackDiagnostic,
  type PackFileChange,
  type PackGit,
  type PackLint,
  type PackLocalizedList,
  type PackTree,
  type PackVersionRef,
  type PackWorkspace,
} from "@entities/pack-studio";
import { mineOf } from "./copyEdits";
import type { CopyScan } from "./useCopyScan";
import {
  NO_CHANGES,
  type ChangesChecks,
  type ChangesRequest,
  type ChangesStatus,
} from "./types";

// Сборка `ChangesStatus` из сырых ответов сервера (pack-studio-ux.md, 4.3). Чистая функция без
// запросов и без React: хук `useChangesStatus` только читает кэш и отдаёт сюда.
//
// Правила, сверху вниз (первое подходящее заканчивает разбор):
//  1. Папка на диске или подключение не готово: git нет, изменений не считаем, всё по нулям.
//  2. git ещё читается или не прочитался: `load`, остальное «ничего не изменено».
//  3. Иначе: файлы по `git.changed`; ошибки из проверок изменённых мест (замечания панель берёт
//     из «Проверки», см. `ChangesPanel`); заметки по манифесту открытой версии; запрос по
//     карточке пространства и проверкам хостинга.

/** Сколько мест проверяем линтером сразу: на каждое отдельный запрос, расчёт идёт секунды. */
export const MAX_LINT_TARGETS = 3;

/** Всё, что нужно для статуса; хук кладёт сюда то, что есть в кэше. */
export type ChangesRaw = {
  workspace: PackWorkspace;
  tree: PackTree;
  /** Открытая версия. */
  open: PackVersionRef;
  git: PackGit | null;
  gitLoad: "loading" | "ready" | "failed";
  /** Проверки хостинга отправленной вершины; `null`: не запрошены или ещё не пришли. */
  ci: PackCiStatus | null;
  /**
   * Открытая версия это копия, сверенная с версией-основой: какие её файлы совпали и потому не
   * считаются правкой. `null`: версия не копия (или сверять не нужно), счёт по git как есть.
   */
  copy?: CopyScan | null;
  /** Ответы линтера по `lintTargets`; ещё не пришедшие просто отсутствуют. */
  lint: readonly PackLint[];
  /** Заметки открытой версии (`changes` манифеста); `null`: манифест ещё не прочитан. */
  notes: PackLocalizedList | null;
};

const keyOf = (ref: PackVersionRef): string =>
  `${ref.pack}/${ref.template}/${ref.version}`;

const sameVersion = (a: PackVersionRef, b: PackVersionRef): boolean =>
  keyOf(a) === keyOf(b);

const isReleased = (tree: PackTree, ref: PackVersionRef): boolean =>
  tree.packs
    .find((pack) => pack.id === ref.pack)
    ?.templates.find((template) => template.id === ref.template)
    ?.versions.find((version) => version.version === ref.version)?.released ??
  false;

/** Версии, где что-то изменено, по ключу. */
const changedVersions = (
  changed: readonly PackFileChange[],
): Map<string, PackVersionRef> => {
  const found = new Map<string, PackVersionRef>();
  for (const change of changed) {
    const ref = versionRefOf(change.path);
    if (ref) found.set(keyOf(ref), ref);
  }
  return found;
};

/**
 * Другая версия с изменениями: сначала черновики, из них самая новая по номеру; выпущенная
 * только если черновиков нет.
 */
const pickElsewhere = (
  tree: PackTree,
  open: PackVersionRef,
  changed: readonly PackFileChange[],
): PackVersionRef | null => {
  const others = [...changedVersions(changed).values()].filter(
    (ref) => !sameVersion(ref, open),
  );
  const rank = (ref: PackVersionRef) => (isReleased(tree, ref) ? 1 : 0);
  others.sort(
    (a, b) =>
      rank(a) - rank(b) ||
      b.version.localeCompare(a.version, "en", { numeric: true }),
  );
  const [first] = others;
  return first ? { ...first } : null;
};

/**
 * Что проверять линтером: открытая версия, если в ней есть правки, затем остальные изменённые
 * версии и манифесты пака, шаблона и реестра выпусков (по алфавиту), не больше
 * `MAX_LINT_TARGETS`. Удалённые файлы не проверяются.
 */
export const lintTargets = (
  changed: readonly PackFileChange[],
  open: PackVersionRef,
): string[] => {
  const targets = new Set<string>();
  for (const change of changed) {
    if (change.status === "deleted") continue;
    const target = lintTargetOf(change.path);
    if (target) targets.add(target);
  }
  const openDir = [...targets].find((target) => {
    const ref = versionRefOf(target);
    return (
      ref !== null && sameVersion(ref, open) && versionDirOf(target) === target
    );
  });
  const rest = [...targets].filter((target) => target !== openDir).sort();
  return (openDir ? [openDir, ...rest] : rest).slice(0, MAX_LINT_TARGETS);
};

/** Находка про заметки версии (`changes.ru`, `changes.en`, `changes`): это шаг, не ошибка. */
const NOTES_FINDING = /`changes(\.[a-z]+)?`/;

export const isNotesFinding = (finding: PackDiagnostic): boolean =>
  finding.severity === "error" && NOTES_FINDING.test(finding.message);

/**
 * Находка про номер версии: «release: номер 2026.1.3 после 2026.1.2 это patch, а изменения
 * требуют не меньше minor». Это тоже шаг, а не тупик: номер подбирается сам (`resolveNumberFix`),
 * поэтому в ошибки она не идёт. Находка про `release.kind` мягче класса сюда не относится: номером
 * её не исправить.
 */
const NUMBER_FINDING =
  /^release: номер \S+ после \S+ это (patch|minor|major), а изменения/u;

/** Текст находки про номер версии (из линтера и из отказа отправки). */
export const isNumberMessage = (message: string): boolean =>
  NUMBER_FINDING.test(message);

export const isNumberFinding = (finding: PackDiagnostic): boolean =>
  finding.severity === "error" && isNumberMessage(finding.message);

/** Заметки версии из данных манифеста (`changes: {ru: [...], en: [...]}`); нет блока: пусто. */
export const readNotes = (manifest: unknown): PackLocalizedList => {
  const block =
    manifest !== null && typeof manifest === "object"
      ? (manifest as { changes?: unknown }).changes
      : undefined;
  const list = (lang: "ru" | "en"): string[] => {
    const items =
      block !== null && typeof block === "object"
        ? (block as Record<string, unknown>)[lang]
        : undefined;
    return Array.isArray(items)
      ? items.filter(
          (item): item is string =>
            typeof item === "string" && item.trim() !== "",
        )
      : [];
  };
  return { ru: list("ru"), en: list("en") };
};

const notesMissing = (notes: PackLocalizedList | null): boolean =>
  notes !== null && (notes.ru.length === 0 || notes.en.length === 0);

const checksOf = (ci: PackCiStatus | null): ChangesChecks => {
  switch (ci?.state) {
    case "pending":
      return "pending";
    case "success":
      return "passed";
    case "failure":
      return "failed";
    case "awaiting_approval":
      return "awaiting_approval";
    default:
      return "unknown";
  }
};

const FINISHED = new Set([
  "success",
  "failure",
  "neutral",
  "skipped",
  "cancelled",
]);

const progressOf = (
  ci: PackCiStatus | null,
): { done: number; total: number } | null =>
  ci && ci.checks.length > 0
    ? {
        done: ci.checks.filter((check) => FINISHED.has(check.state)).length,
        total: ci.checks.length,
      }
    : null;

const requestOf = (git: PackGit, ci: PackCiStatus | null): ChangesRequest => {
  const ws = git.workspace;
  const number = ws.pr_number;
  if (number === null) return { kind: "none" };
  const label = `${git.provider === "gitlab" ? "!" : "#"}${String(number)}`;
  if (ci?.pr_state === "merged") return { kind: "merged", number, label };
  if (ci?.pr_state === "closed") return { kind: "closed", number, label };
  return {
    kind: "open",
    number,
    label,
    url: ws.pr_url,
    checks: checksOf(ci),
    progress: progressOf(ci),
    // Правки на диске или коммиты после последней отправки.
    newEdits:
      git.dirty || (ws.pushed_sha !== null && git.head_sha !== ws.pushed_sha),
  };
};

/** Что человек изменил: список git без файлов копии, совпавших с основой. */
export const changedOf = (raw: ChangesRaw): PackFileChange[] =>
  mineOf(raw.git?.changed ?? [], raw.copy?.same ?? null);

export const deriveChangesStatus = (raw: ChangesRaw): ChangesStatus => {
  const { workspace, tree, open, git } = raw;
  const base: ChangesStatus = {
    ...NO_CHANGES,
    connection:
      workspace.state === "ready"
        ? "ready"
        : workspace.state === "cloning"
          ? "cloning"
          : "failed",
    workspaceKind: workspace.kind,
    released: isReleased(tree, open),
  };
  if (workspace.kind === "folder" || base.connection !== "ready") return base;
  if (raw.gitLoad !== "ready" || !git) {
    return { ...base, load: raw.gitLoad === "failed" ? "failed" : "loading" };
  }

  const changed = changedOf(raw);
  const changedInVersion = changed.filter((change) => {
    const ref = versionRefOf(change.path);
    return ref !== null && sameVersion(ref, open);
  }).length;

  let errors = 0;
  let notesFinding = false;
  for (const report of raw.lint) {
    const notes = report.findings.filter(isNotesFinding).length;
    const number = report.findings.filter(isNumberFinding).length;
    // Для выпущенной версии заметки и номер уже не поменяешь: это обычные ошибки.
    const skipNotes = report.released ? 0 : notes;
    const skip = skipNotes + (report.released ? 0 : number);
    const target = report.target ? versionRefOf(report.target) : null;
    notesFinding ||=
      skipNotes > 0 && target !== null && sameVersion(target, open);
    errors += Math.max(0, report.errors - skip);
  }

  return {
    ...base,
    changedFiles: changed.length,
    changedInVersion,
    changedElsewhere: pickElsewhere(tree, open, changed),
    errors,
    notesNeeded:
      !base.released &&
      ((changedInVersion > 0 && notesMissing(raw.notes)) || notesFinding),
    request: requestOf(git, raw.ci),
    behind: git.behind,
  };
};
