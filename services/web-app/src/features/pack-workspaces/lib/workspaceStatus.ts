import {
  versionDirOf,
  type PackFileChange,
  type PackGit,
  type PackWorkspace,
} from "@entities/pack-studio";

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
  | { kind: "request"; number: number; unsent: number; copy: boolean }
  /**
   * Правки не отправлены. `copy`: среди них целая новая версия (копия), в git все её файлы
   * «новые», и число файлов ничего не говорит о правках человека: число не показываем.
   */
  | { kind: "unsent"; unsent: number; copy: boolean }
  /** Ветка уже на хостинге, но запрос на слияние не открыт: отправлять нечего, открыть запрос. */
  | { kind: "pushed" }
  | { kind: "clean" }
  /** Сведения о правках ещё не пришли (или не получены): статус не придумываем. */
  | { kind: "unknown" };

/**
 * Какие изменения ещё не отправлены. Когда запрос уже открыт или ветка уже отправлена на
 * хостинг (её вершина совпадает с отправленной), всё, что было до этого, там есть: считаются
 * только правки на диске после этого. Иначе это всё, что отличается от основной ветки.
 */
const unsentList = (
  git: PackGit,
  workspace: PackWorkspace,
): readonly PackFileChange[] =>
  workspace.pr_number !== null ||
  (workspace.pushed_sha !== null && git.head_sha === workspace.pushed_sha)
    ? git.uncommitted
    : git.changed;

export const unsentCount = (git: PackGit, workspace: PackWorkspace): number =>
  unsentList(git, workspace).length;

/** Среди изменений есть новая версия целиком (копия): её `version.yaml` новый. */
const hasFreshCopy = (list: readonly PackFileChange[]): boolean =>
  list.some((change) => {
    const dir = versionDirOf(change.path);
    return (
      change.status === "added" &&
      dir !== null &&
      change.path === `${dir}/version.yaml`
    );
  });

export const workspaceStatus = (
  workspace: PackWorkspace,
  git: PackGit | undefined,
): WorkspaceStatus => {
  if (workspace.state === "cloning") return { kind: "cloning" };
  if (workspace.state === "failed") return { kind: "failed" };
  if (workspace.busy) return { kind: "fetching" };
  if (workspace.kind === "folder") return { kind: "folder" };
  const list = git ? unsentList(git, workspace) : [];
  const unsent = list.length;
  const copy = hasFreshCopy(list);
  if (workspace.pr_number !== null) {
    return { kind: "request", number: workspace.pr_number, unsent, copy };
  }
  if (!git) return { kind: "unknown" };
  if (unsent > 0) return { kind: "unsent", unsent, copy };
  return git.changed.length > 0 ? { kind: "pushed" } : { kind: "clean" };
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

/** Есть ли в пространстве то, что пропадёт при удалении: неотправленные правки. */
export const hasUnsent = (status: WorkspaceStatus): boolean =>
  (status.kind === "unsent" || status.kind === "request") && status.unsent > 0;
