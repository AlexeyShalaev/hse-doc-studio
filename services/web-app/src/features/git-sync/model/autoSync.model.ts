import type { SyncViewState } from "./syncUi.model";

// Решение автосинхронизации одной функцией без таймеров и запросов:
// docs/design/local-sync.md, раздел 1. Хук `useAutoSync` лишь подаёт сюда
// текущие факты и исполняет ответ.

/** Пауза после последней правки, по её окончании проект уходит на сервер. */
export const AUTO_SYNC_DEBOUNCE_MS = 20_000;
/** Не чаще одного автозапуска в этот срок (кроме первого). */
export const AUTO_SYNC_MIN_GAP_MS = 60_000;
/** Между двумя запусками, если нужно лишь забрать чужое: свои правки при этом не страдают. */
export const AUTO_SYNC_PULL_GAP_MS = 15_000;
/** Через сколько забираем чужие изменения, если своих правок нет. */
export const AUTO_SYNC_PULL_DELAY_MS = 3_000;
/** Задержка после первой неудачи; дальше вдвое дольше, но не больше потолка. */
export const AUTO_SYNC_BACKOFF_MS = 30_000;
export const AUTO_SYNC_BACKOFF_MAX_MS = 600_000;
/** После стольких неудач подряд автосинхронизация останавливается до ручного действия. */
export const AUTO_SYNC_MAX_FAILURES = 3;

export type AutoSyncStop =
  | "disabled"
  | "read_only"
  | "conflicts"
  | "auth_failed"
  | "blocked"
  | "no_remote"
  | "busy"
  | "offline"
  | "failed"
  | "unknown";

export type AutoSyncFacts = {
  /** Настройка проекта (status.auto_sync.enabled). */
  enabled: boolean;
  readOnly: boolean;
  /** navigator.onLine. */
  online: boolean;
  state: SyncViewState;
  ahead: number;
  behind: number;
  now: number;
  /** Последняя правка в этом окне или null. */
  lastEditAt: number | null;
  /**
   * Когда хук впервые увидел, что синхронизировать нужно (появились неотправленное
   * или чужое). Якорь ожидания, когда правок в этом окне не было: без него срок
   * уезжал бы вперёд с каждой проверкой.
   */
  needSince: number;
  /** Когда автосинхронизация стартовала в последний раз (любой исход) или null. */
  lastRunAt: number | null;
  /** Неудачи подряд и момент последней из них. */
  failures: number;
  lastFailureAt: number | null;
};

export type AutoSyncDecision =
  /** Запустить синхронизацию сейчас. */
  | { kind: "run"; reason: "push" | "pull" }
  /** Подождать `delayMs` и спросить снова. */
  | { kind: "wait"; delayMs: number; reason: "push" | "pull" | "retry" }
  /** Делать нечего (`reason: null`) или нельзя (`reason`). */
  | { kind: "idle"; reason: AutoSyncStop | null };

const STOPPED_BY_STATE: Partial<Record<SyncViewState, AutoSyncStop>> = {
  conflicts: "conflicts",
  auth_failed: "auth_failed",
  blocked: "blocked",
  no_remote: "no_remote",
  syncing: "busy",
  unknown: "unknown",
};

/** Через сколько после неудачи число `failures` разрешает следующую попытку. */
export const backoffMs = (failures: number): number =>
  Math.min(
    AUTO_SYNC_BACKOFF_MAX_MS,
    AUTO_SYNC_BACKOFF_MS * 2 ** Math.max(0, failures - 1),
  );

/** Есть правки, которых ещё не касалась синхронизация. */
export const hasUnsyncedEdits = (facts: AutoSyncFacts): boolean =>
  facts.lastEditAt !== null &&
  (facts.lastRunAt === null || facts.lastEditAt > facts.lastRunAt);

const stopReason = (facts: AutoSyncFacts): AutoSyncStop | null => {
  if (!facts.enabled) return "disabled";
  if (facts.readOnly) return "read_only";
  const byState = STOPPED_BY_STATE[facts.state];
  if (byState) return byState;
  if (!facts.online || facts.state === "offline") return "offline";
  if (facts.failures >= AUTO_SYNC_MAX_FAILURES) return "failed";
  return null;
};

/** Время тут не нужно: по этим фактам и строится подпись состояния, и решается, делать ли что-то. */
export type AutoSyncWork = {
  stop: AutoSyncStop | null;
  /** Что нужно сделать: отправить своё (с забором чужого заодно), только забрать чужое или ничего. */
  wants: "push" | "pull" | null;
};

export const autoSyncWork = (
  facts: Omit<AutoSyncFacts, "now" | "needSince">,
): AutoSyncWork => {
  const stop = stopReason({ ...facts, now: 0, needSince: 0 });
  const dirty = hasUnsyncedEdits({ ...facts, now: 0, needSince: 0 });
  const wantsPush = dirty || facts.ahead > 0;
  const wants = wantsPush ? "push" : facts.behind > 0 ? "pull" : null;
  return { stop, wants };
};

export const decideAutoSync = (facts: AutoSyncFacts): AutoSyncDecision => {
  const { stop, wants } = autoSyncWork(facts);
  if (stop) return { kind: "idle", reason: stop };
  if (wants === null) return { kind: "idle", reason: null };

  // Самый поздний из сроков: пауза после правки, зазор между запусками, откат после неудачи.
  const earliest: number[] = [];
  if (wants === "push") {
    earliest.push(
      (facts.lastEditAt ?? facts.needSince) + AUTO_SYNC_DEBOUNCE_MS,
    );
  } else {
    earliest.push(facts.needSince + AUTO_SYNC_PULL_DELAY_MS);
  }
  if (facts.lastRunAt !== null) {
    earliest.push(
      facts.lastRunAt +
        (wants === "push" ? AUTO_SYNC_MIN_GAP_MS : AUTO_SYNC_PULL_GAP_MS),
    );
  }
  const retryAt =
    facts.failures > 0 && facts.lastFailureAt !== null
      ? facts.lastFailureAt + backoffMs(facts.failures)
      : null;
  if (retryAt !== null) earliest.push(retryAt);

  const at = Math.max(facts.now, ...earliest);
  if (at <= facts.now) return { kind: "run", reason: wants };
  return {
    kind: "wait",
    delayMs: at - facts.now,
    // Любое ожидание после неудачи это повтор, даже если дольше всего ждать зазор между запусками.
    reason: retryAt !== null ? "retry" : wants,
  };
};

/** Что показать рядом с переключателем (ключ в gitSync:autoSync.state.*). */
export type AutoSyncPhase =
  "off" | "watching" | "waiting" | "running" | "retrying" | "stopped";

export const autoSyncPhase = (
  work: AutoSyncWork,
  failures: number,
): { phase: AutoSyncPhase; stop: AutoSyncStop | null } => {
  if (work.stop === "disabled") return { phase: "off", stop: null };
  if (work.stop === "busy") return { phase: "running", stop: null };
  if (work.stop) return { phase: "stopped", stop: work.stop };
  if (work.wants === null) return { phase: "watching", stop: null };
  return { phase: failures > 0 ? "retrying" : "waiting", stop: null };
};
