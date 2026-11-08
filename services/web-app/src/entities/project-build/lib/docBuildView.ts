import type {
  Build,
  DocumentBuildStatus,
  DocumentBuilds,
  FetchBlocked,
} from "../model/build.schema";
import { RELATION_TONE } from "./buildLib";

/** Что сказать про сборку документа: ключ строки в словаре `devices` и времена для подстановки. */
export type DocBuildView = {
  /** Ключ в `builds.*`. */
  key: string;
  /** Времена для подписей: первое и второе (облако и Студия, когда нужны оба). */
  at: string | null;
  at2: string | null;
  tone: "ok" | "info" | "warn" | "muted";
  /** Свежая ли сборка относительно текущей версии проекта; null: коммит неизвестен. */
  fresh: boolean | null;
  commit: string | null;
  /** Локально: PDF получен из облака, а не собран здесь. */
  fromCloud: boolean;
  /** Локальная Студия может скачать облачную сборку. */
  canFetch: boolean;
  /** В облаке сборка свежее, но получить её нельзя: почему (документ не в PDF и т. п.). */
  fetchBlocked: FetchBlocked | null;
  /** У облачной сборки есть более свежая локальная: «Получить» заменит её только с подтверждением. */
  localNewer: boolean;
  running: boolean;
};

const newest = (a: Build | null, b: Build | null): Build | null => {
  if (a === null) return b;
  if (b === null) return a;
  return a.at >= b.at ? a : b;
};

/** Облако: по документу видно, где и когда он собран (облако, Студия) и из какого коммита. */
export const describeCloudDoc = (doc: DocumentBuilds): DocBuildView => {
  const base = {
    at: null,
    at2: null,
    fresh: null,
    commit: null,
    fromCloud: false,
    canFetch: false,
    fetchBlocked: null,
    localNewer: false,
    running: false,
  } as const;
  const latest = newest(doc.cloud, doc.studio);
  const shared = {
    fresh: latest?.fresh ?? null,
    commit: latest?.commit ?? null,
  };
  if (doc.cloud_running) {
    return { ...base, ...shared, key: "running", tone: "info", running: true };
  }
  if (doc.cloud !== null && doc.studio !== null) {
    return {
      ...base,
      ...shared,
      key: "both",
      at: doc.cloud.at,
      at2: doc.studio.at,
      tone: shared.fresh === false ? "warn" : "ok",
    };
  }
  if (doc.cloud !== null) {
    return {
      ...base,
      ...shared,
      key: "cloudOnly",
      at: doc.cloud.at,
      tone: shared.fresh === false ? "warn" : "info",
    };
  }
  if (doc.studio !== null) {
    return {
      ...base,
      ...shared,
      key: "studioOnly",
      at: doc.studio.at,
      tone: shared.fresh === false ? "warn" : "info",
    };
  }
  return { ...base, key: "none", tone: "muted" };
};

const LOCAL_KEY = {
  none: "local.none",
  cloud_only: "local.cloudOnly",
  local_only: "local.localOnly",
  same: "local.same",
  cloud_newer: "local.cloudNewer",
  local_newer: "local.localNewer",
} as const;

/** Локальная Студия: то же вместе с локальной стороной и признаком «в облаке собрано, у вас нет». */
export const describeLocalDoc = (status: DocumentBuildStatus): DocBuildView => {
  const running = status.cloud_running && status.cloud === null;
  const relation = status.relation;
  const at =
    relation === "cloud_only" || relation === "cloud_newer"
      ? (status.cloud?.at ?? null)
      : relation === "local_newer"
        ? (status.local?.at ?? null)
        : (status.local?.at ?? status.cloud?.at ?? null);
  const showing =
    relation === "cloud_only" || relation === "cloud_newer"
      ? status.cloud
      : null;
  return {
    key: running ? "running" : LOCAL_KEY[relation],
    at,
    at2: null,
    tone: running ? "info" : RELATION_TONE[relation],
    fresh: showing?.fresh ?? status.local?.fresh ?? status.cloud?.fresh ?? null,
    commit:
      showing?.commit ?? status.local?.commit ?? status.cloud?.commit ?? null,
    fromCloud: status.local?.from_cloud === true,
    canFetch: status.can_fetch,
    fetchBlocked: status.fetch_blocked ?? null,
    localNewer: relation === "local_newer",
    running,
  };
};
