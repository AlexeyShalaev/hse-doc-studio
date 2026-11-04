import type { StatusDotStatus } from "@shared/ui";
import type {
  AiState,
  Device,
  DeviceActivity,
  DeviceRunner,
  LinkServer,
  SyncCode,
} from "../model/device.schema";

/** Точка присутствия устройства. */
export const presenceDot = (
  device: Pick<Device, "presence">,
): StatusDotStatus => (device.presence === "online" ? "online" : "offline");

/** Тон состояния синхронизации проекта на устройстве. */
export const SYNC_DOT: Record<SyncCode, StatusDotStatus> = {
  synced: "online",
  syncing: "info",
  ahead: "info",
  behind: "info",
  diverged: "warning",
  conflicts: "danger",
  offline: "stale",
  auth_failed: "danger",
  blocked: "warning",
  error: "danger",
  unfetched: "neutral",
};

export const RUNNER_DOT: Record<DeviceRunner["state"], StatusDotStatus> = {
  online: "online",
  stale: "stale",
  offline: "offline",
  paused: "paused",
  revoked: "neutral",
  disabled: "neutral",
};

/** Тон ИИ через Студию: готово, поправимо или нет связи. */
export const AI_DOT: Record<AiState, StatusDotStatus> = {
  ready: "online",
  not_opened: "neutral",
  runner_unpaired: "neutral",
  runner_offline: "stale",
  runner_paused: "paused",
  runner_revoked: "neutral",
  disabled: "neutral",
  endpoint_unreachable: "warning",
  no_models: "warning",
  no_provider: "warning",
  studio_offline: "offline",
  unknown: "neutral",
};

export const ACTIVITY_KEY: Record<DeviceActivity, string> = {
  idle: "activity.idle",
  syncing: "activity.syncing",
  building: "activity.building",
};

/**
 * Состояния ИИ, где человеку что-то нужно сделать: у каждого в словаре есть
 * совет (`ai.advice.<код>`). Остальные (готово, нет связи) совета не требуют.
 */
export const AI_NEEDS_ACTION: ReadonlySet<AiState> = new Set<AiState>([
  "not_opened",
  "runner_unpaired",
  "runner_offline",
  "runner_paused",
  "runner_revoked",
  "disabled",
  "endpoint_unreachable",
  "no_models",
  "no_provider",
]);

/** Первое объявленное через Студию, но не подключённое в облаке: для кнопки «Добавить в облаке». */
export const firstUnprovidedEndpoint = (device: Device) =>
  device.ai.endpoints.find((endpoint) => endpoint.state === "no_provider") ??
  null;

/** Сколько секунд назад устройство отозвалось: нужно, чтобы отличать «в сети» и «была в сети». */
export const secondsSince = (iso: string, now: number): number =>
  Math.max(0, Math.round((now - new Date(iso).getTime()) / 1000));

/** Для локальной Студии: рабочий ли вход на сервер. */
export const isServerReachable = (server: LinkServer): boolean =>
  server.state === "ok";

/** Облако видит эту Студию онлайн (по ответу сервера на вопрос «как вы меня видите»). */
export const cloudSeesOnline = (server: LinkServer): boolean =>
  server.cloud?.device?.presence === "online";
