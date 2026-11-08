import type {
  BuildRelation,
  DocumentBuildStatus,
  DocumentBuilds,
  FetchStatus,
} from "../model/build.schema";

/** Сеть, на которой фоновые загрузки не нужны: мобильная или с включённой экономией трафика. */
export const isMeteredConnection = (): boolean => {
  if (typeof navigator === "undefined") return false;
  const connection = (
    navigator as Navigator & {
      connection?: { type?: string; saveData?: boolean };
    }
  ).connection;
  return connection?.type === "cellular" || connection?.saveData === true;
};

/** Не чаще раза в `minGapMs` на проект: автополучение идёт после синхронизации, а не на каждый её тик. */
export const AUTO_FETCH_GAP_MS = 5 * 60_000;

const lastAutoFetch = new Map<string, number>();

export const shouldAutoFetch = (
  projectId: string,
  now: number,
  gapMs: number = AUTO_FETCH_GAP_MS,
): boolean => {
  if (isMeteredConnection()) return false;
  const last = lastAutoFetch.get(projectId);
  return last === undefined || now - last >= gapMs;
};

export const markAutoFetched = (projectId: string, now: number): void => {
  lastAutoFetch.set(projectId, now);
};

export const resetAutoFetchMemo = (): void => {
  lastAutoFetch.clear();
};

/** Короткий вид коммита для подписи. */
export const shortCommit = (commit: string | null): string | null =>
  commit ? commit.slice(0, 7) : null;

/** Результаты получения, о которых молчим при автоматическом заходе: ничего не изменилось или это не по правилам. */
export const QUIET_FETCH_STATUSES: ReadonlySet<FetchStatus> =
  new Set<FetchStatus>([
    "unchanged",
    "skipped_stale",
    "no_cloud_build",
    "not_pdf",
  ]);

/** Какие строки показывает документ в облаке: одна запись по облаку и Студии. */
export type CloudDocState =
  "none" | "cloud_only" | "studio_only" | "both" | "running";

export const cloudDocState = (doc: DocumentBuilds): CloudDocState => {
  if (doc.cloud_running) return "running";
  if (doc.cloud && doc.studio) return "both";
  if (doc.cloud) return "cloud_only";
  if (doc.studio) return "studio_only";
  return "none";
};

/** Нужно ли внимание человека к документу (чип светится): расхождение сборок или устаревший результат. */
export const needsAttention = (status: DocumentBuildStatus): boolean =>
  status.relation === "cloud_only" ||
  status.relation === "cloud_newer" ||
  status.cloud?.fresh === false ||
  status.local?.fresh === false;

export const RELATION_TONE: Record<
  BuildRelation,
  "ok" | "info" | "warn" | "muted"
> = {
  none: "muted",
  cloud_only: "info",
  local_only: "info",
  same: "ok",
  cloud_newer: "warn",
  local_newer: "info",
};
