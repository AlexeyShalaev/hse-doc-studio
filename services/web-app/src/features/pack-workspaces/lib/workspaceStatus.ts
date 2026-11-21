import type { PackGit, PackWorkspace } from "@entities/pack-studio";

/**
 * Состояние пространства в списке одним значением (pack-studio-ux.md, 5.1 и 5.10).
 * Порядок проверок и есть приоритет: пока клон идёт, про запрос не говорим.
 */
export type WorkspaceStatus =
  | { kind: "cloning" }
  | { kind: "failed" }
  | { kind: "fetching" }
  /** Пространство над папкой: git там не настроен, правки пишутся прямо в папку. */
  | { kind: "folder" }
  /** Запрос на слияние открыт; unsent это новые правки, которых в нём ещё нет. */
  | { kind: "request"; number: number; unsent: number }
  | { kind: "unsent"; unsent: number }
  | { kind: "clean" }
  /** Сведения о правках ещё не пришли (или не получены): статус не придумываем. */
  | { kind: "unknown" };

/**
 * Сколько изменений не отправлено. Когда запрос уже открыт, в нём есть всё,
 * что отправлено раньше, поэтому считаются только правки на диске после этого.
 */
export const unsentCount = (git: PackGit, workspace: PackWorkspace): number =>
  workspace.pr_number === null ? git.changed.length : git.uncommitted.length;

export const workspaceStatus = (
  workspace: PackWorkspace,
  git: PackGit | undefined,
): WorkspaceStatus => {
  if (workspace.state === "cloning") return { kind: "cloning" };
  if (workspace.state === "failed") return { kind: "failed" };
  if (workspace.busy) return { kind: "fetching" };
  if (workspace.kind === "folder") return { kind: "folder" };
  const unsent = git ? unsentCount(git, workspace) : 0;
  if (workspace.pr_number !== null) {
    return { kind: "request", number: workspace.pr_number, unsent };
  }
  if (!git) return { kind: "unknown" };
  return unsent > 0 ? { kind: "unsent", unsent } : { kind: "clean" };
};

/**
 * Пространство, которое предлагает главная кнопка «Продолжить»: сначала то, где
 * есть неотправленные изменения (из них последнее открытое, иначе самое свежее),
 * затем то, где человек был последним. Нет такого: null, и главная кнопка
 * экрана «Подключить пространство».
 */
export const pickContinueId = (
  workspaces: readonly PackWorkspace[],
  gitById: ReadonlyMap<string, PackGit>,
  lastOpenedId: string | null,
): string | null => {
  const ready = workspaces.filter((w) => w.state === "ready");
  const withUnsent = ready.filter((w) => {
    const git = gitById.get(w.id);
    return git !== undefined && unsentCount(git, w) > 0;
  });
  if (withUnsent.length > 0) {
    const last = withUnsent.find((w) => w.id === lastOpenedId);
    if (last) return last.id;
    const newest = [...withUnsent].sort((a, b) =>
      b.updated_at.localeCompare(a.updated_at),
    )[0];
    return newest?.id ?? null;
  }
  return ready.find((w) => w.id === lastOpenedId)?.id ?? null;
};
