import { useStaleBuildStore } from "./staleBuildStore";

export const VERSION_URL = "/version.json";
export const VERSION_POLL_MS = 5 * 60_000;
/** Возврат на вкладку не чаще раза в это время запрашивает версию снова. */
export const VERSION_MIN_GAP_MS = 60_000;

type BuildInfo = { version?: unknown; build?: unknown };

// Идентификатор сборки это время сборки в base36: при выкатке старый под может ещё отвечать, а вкладка уже
// на новой сборке, поэтому «новой» считаем только более позднюю сборку, а не просто другую.
const isNewerBuild = (remote: BuildInfo): boolean => {
  if (typeof remote.build === "string") {
    const theirs = Number.parseInt(remote.build, 36);
    const ours = Number.parseInt(__BUILD_ID__, 36);
    if (Number.isNaN(theirs) || Number.isNaN(ours)) return false;
    return theirs > ours;
  }
  if (typeof remote.version === "string") {
    return remote.version !== __APP_VERSION__;
  }
  return false;
};

/** Сервер отдаёт version.json без кэша; любой сбой или чужой ответ означает «не знаем» и ничего не меняет. */
export const fetchHasNewBuild = async (
  fetchImpl: typeof fetch = fetch,
): Promise<boolean> => {
  try {
    const response = await fetchImpl(VERSION_URL, {
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    if (!response.ok) return false;
    const type = response.headers.get("content-type") ?? "";
    if (!type.includes("json")) return false;
    return isNewerBuild((await response.json()) as BuildInfo);
  } catch {
    return false;
  }
};

/** Раз в несколько минут и при возврате на вкладку; скрытая вкладка сервер не нагружает. */
export const startVersionWatch = (
  fetchImpl: typeof fetch = fetch,
): (() => void) => {
  let lastCheck = Date.now();
  let busy = false;
  const check = async (): Promise<void> => {
    const store = useStaleBuildStore.getState();
    if (busy || store.reason !== null) return;
    busy = true;
    lastCheck = Date.now();
    try {
      if (await fetchHasNewBuild(fetchImpl)) store.markStale("version");
    } finally {
      busy = false;
    }
  };
  const timer = window.setInterval(() => {
    if (!document.hidden) void check();
  }, VERSION_POLL_MS);
  const onVisible = (): void => {
    if (!document.hidden && Date.now() - lastCheck >= VERSION_MIN_GAP_MS) {
      void check();
    }
  };
  document.addEventListener("visibilitychange", onVisible);
  return () => {
    window.clearInterval(timer);
    document.removeEventListener("visibilitychange", onVisible);
  };
};
