import {
  isGitBlockedReason,
  isGitOperationPhase,
  isGitUiState,
  type GitBlockedReason,
  type GitOperationPhase,
  type GitUiState,
  type SyncStatusView,
} from "@entities/git-sync";

// Чистая функция «состояние от сервера -> как это показать». Все визуальные
// решения (значок, тон, подпись, главное действие) принимаются здесь одной
// таблицей, поэтому элемент в заголовке, строка состояния, бейдж рейки и
// скринридер всегда говорят одно и то же.

export type SyncTone = "muted" | "ok" | "info" | "warn" | "err" | "accent";

export type SyncIcon =
  | "cloud_off"
  | "cloud"
  | "cloud_check"
  | "cloud_upload"
  | "cloud_download"
  | "git_merge"
  | "spinner"
  | "alert_triangle"
  | "key"
  | "wifi_off"
  | "alert_circle"
  | "lock";

// Что делает щелчок по основной части элемента.
export type SyncPrimaryAction =
  "connect" | "sync" | "resolve" | "fix_access" | "retry" | "details" | "none";

// Состояние, как его показывает интерфейс: серверные плюс то, что решает сам
// клиент (браузер без сети, проект только для чтения), и «неизвестное».
export type SyncViewState = GitUiState | "unknown";

// Причина, по которой синхронизировать нельзя: серверные причины плюс сеть.
export type SyncBlockReason = GitBlockedReason | "offline_browser" | "unknown";

export type SyncUiContext = {
  /** navigator.onLine: без сети синхронизацию не запускаем. */
  online: boolean;
  /** Проект открыт только для чтения (доступ не полный). */
  readOnly: boolean;
};

export type SyncUi = {
  /** false: бэкенд не умеет синхронизацию, элемент прячется. */
  visible: boolean;
  state: SyncViewState;
  tone: SyncTone;
  icon: SyncIcon;
  primary: SyncPrimaryAction;
  /** Ключ короткой подписи на кнопке (gitSync:state.* и control.label.*). */
  labelKey: string;
  /** Ключ полной фразы состояния (gitSync:control.status.*) и её параметры. */
  statusKey: string;
  statusParams: Record<string, string | number>;
  /** Числа на кнопке: сколько получено (к нам) и сколько не отправлено (от нас). */
  incoming: number;
  outgoing: number;
  /** Сколько файлов ждут решения (только при конфликтах). */
  conflictFiles: number;
  /** Время, к которому относится «N минут назад» в подписи состояния. */
  since: string | null;
  busy: boolean;
  phase: GitOperationPhase | null;
  percent: number | null;
  /** Операция, не относящаяся к синхронизации (клонирование, импорт файла). */
  operationKind: string | null;
  blockReason: SyncBlockReason | null;
  /** Требуемая версия Студии (remote_schema_newer). */
  requiredStudio: string | null;
  canSync: boolean;
  canCheck: boolean;
  /** Как громко сообщить о входе в это состояние. */
  announce: "polite" | "assertive" | null;
  /** Бейдж рейки «История»: null, когда сказать нечего. */
  railBadge: { tone: "err" | "warn" | "info"; count: number } | null;
};

const HIDDEN: SyncUi = {
  visible: false,
  state: "no_remote",
  tone: "muted",
  icon: "cloud_off",
  primary: "none",
  labelKey: "control.label.no_remote",
  statusKey: "control.status.no_remote",
  statusParams: {},
  incoming: 0,
  outgoing: 0,
  conflictFiles: 0,
  since: null,
  busy: false,
  phase: null,
  percent: null,
  operationKind: null,
  blockReason: null,
  requiredStudio: null,
  canSync: false,
  canCheck: false,
  announce: null,
  railBadge: null,
};

type Row = Pick<SyncUi, "tone" | "icon" | "primary">;

// Одна таблица «состояние -> вид». Значок, подпись и тон вместе: цвет никогда
// не несёт смысл в одиночку.
const TABLE: Record<SyncViewState, Row> = {
  no_remote: { tone: "muted", icon: "cloud_off", primary: "connect" },
  unfetched: { tone: "muted", icon: "cloud", primary: "sync" },
  up_to_date: { tone: "ok", icon: "cloud_check", primary: "sync" },
  ahead: { tone: "info", icon: "cloud_upload", primary: "sync" },
  behind: { tone: "accent", icon: "cloud_download", primary: "sync" },
  diverged: { tone: "info", icon: "git_merge", primary: "sync" },
  syncing: { tone: "info", icon: "spinner", primary: "details" },
  conflicts: { tone: "err", icon: "alert_triangle", primary: "resolve" },
  auth_failed: { tone: "err", icon: "key", primary: "fix_access" },
  offline: { tone: "warn", icon: "wifi_off", primary: "retry" },
  error: { tone: "err", icon: "alert_circle", primary: "details" },
  blocked: { tone: "muted", icon: "lock", primary: "details" },
  unknown: { tone: "err", icon: "alert_circle", primary: "details" },
};

const ANNOUNCE: Partial<Record<SyncViewState, "polite" | "assertive">> = {
  up_to_date: "polite",
  behind: "polite",
  conflicts: "assertive",
  auth_failed: "assertive",
  error: "assertive",
  unknown: "assertive",
};

const STATE_NO_OPERATION = new Set<SyncViewState>([
  "syncing",
  "conflicts",
  "no_remote",
]);

const serverState = (status: SyncStatusView): SyncViewState =>
  isGitUiState(status.ui_state) ? status.ui_state : "unknown";

const operationKind = (status: SyncStatusView): string | null => {
  const kind = status.operation?.kind ?? null;
  return kind === null || kind === "sync" ? null : kind;
};

export const deriveSyncUi = (
  status: SyncStatusView | undefined,
  context: SyncUiContext,
): SyncUi => {
  if (!status?.supported) return HIDDEN;

  let state = serverState(status);
  let blockReason: SyncBlockReason | null = null;
  let requiredStudio: string | null = null;

  if (state === "blocked") {
    blockReason = isGitBlockedReason(status.blocked?.reason)
      ? status.blocked.reason
      : "unknown";
    requiredStudio = status.blocked?.required_studio ?? null;
  }

  // Клиентские поправки: проект открыт только для чтения, а сервер ещё не
  // успел это сказать, либо у браузера нет сети. Идущую операцию и конфликты
  // эти поправки не затирают: о них пользователь должен знать в любом случае.
  if (status.connected && !STATE_NO_OPERATION.has(state)) {
    if (context.readOnly && state !== "blocked") {
      state = "blocked";
      blockReason = "read_only";
    } else if (
      !context.online &&
      state !== "blocked" &&
      state !== "auth_failed"
    ) {
      state = "offline";
      blockReason = "offline_browser";
    }
  }
  if (!status.connected && context.readOnly) {
    blockReason = "read_only";
  }

  const row = TABLE[state];
  const incoming = status.behind;
  const outgoing = status.ahead;
  const conflictFiles = status.pending?.files_open ?? 0;
  const operation = status.operation ?? null;
  const phase =
    operation && isGitOperationPhase(operation.phase) ? operation.phase : null;
  const busy = state === "syncing";

  const canSyncState =
    state === "unfetched" ||
    state === "up_to_date" ||
    state === "ahead" ||
    state === "behind" ||
    state === "diverged" ||
    // Сервер сам скажет, получилось ли: после сбоя повторить можно.
    state === "error" ||
    (state === "offline" && blockReason !== "offline_browser");
  const canSync = canSyncState && context.online && !context.readOnly;
  const canCheck =
    status.connected &&
    context.online &&
    !busy &&
    state !== "conflicts" &&
    (state !== "blocked" ||
      blockReason === "read_only" ||
      blockReason === "off_branch");

  let primary = row.primary;
  if (state === "offline" && blockReason === "offline_browser") {
    primary = "details";
  }
  if (state === "no_remote") {
    primary = context.readOnly ? "details" : "connect";
  }
  if (state === "blocked") {
    primary = "details";
  }
  if ((primary === "sync" || primary === "retry") && !canSync && !canCheck) {
    primary = "details";
  }

  const since =
    status.last_sync_at ??
    status.last_sync?.at ??
    status.last_fetch_ok_at ??
    null;

  const statusParams: Record<string, string | number> = {
    count: state === "conflicts" ? conflictFiles : incoming,
    incoming,
    outgoing,
  };
  const statusKey = (() => {
    if (state === "blocked") {
      return `control.status.blocked_${blockReason ?? "unknown"}`;
    }
    if (state === "offline" && blockReason === "offline_browser") {
      return "control.status.offline_browser";
    }
    if (state === "ahead") {
      statusParams.count = outgoing;
      return "control.status.ahead";
    }
    if (state === "up_to_date" && since === null) {
      return "control.status.up_to_date_plain";
    }
    return `control.status.${state}`;
  })();

  let railBadge: SyncUi["railBadge"] = null;
  if (state === "conflicts") {
    railBadge = { tone: "err", count: Math.max(conflictFiles, 1) };
  } else if (state === "auth_failed" || state === "error") {
    railBadge = { tone: "warn", count: 1 };
  } else if ((state === "behind" || state === "diverged") && incoming > 0) {
    railBadge = { tone: "info", count: incoming };
  }

  return {
    visible: true,
    state,
    tone: row.tone,
    icon: row.icon,
    primary,
    labelKey: ((): string => {
      if (state === "no_remote") return "control.label.no_remote";
      if (state === "blocked") {
        return `control.label.blocked_${blockReason ?? "unknown"}`;
      }
      return `state.${state}`;
    })(),
    statusKey,
    statusParams,
    incoming,
    outgoing,
    conflictFiles,
    since,
    busy,
    phase,
    percent: operation?.percent ?? null,
    operationKind: operationKind(status),
    blockReason,
    requiredStudio,
    canSync,
    canCheck,
    announce: ANNOUNCE[state] ?? null,
    railBadge,
  };
};
