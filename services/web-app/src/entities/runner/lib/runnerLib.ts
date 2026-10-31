import type { StatusDotStatus } from "@shared/ui";
import {
  ENDPOINT_NAME_RE,
  type MyRunnerState,
  type OwnerRunnerState,
  type RemoteRunnerState,
} from "../model/runner.schema";

/** Точка состояния раннера: та же форма, что у раннеров установки в админке. */
export const RUNNER_STATE_DOT: Record<
  MyRunnerState | OwnerRunnerState,
  StatusDotStatus
> = {
  online: "online",
  stale: "stale",
  offline: "offline",
  paused: "paused",
  revoked: "neutral",
  disabled: "neutral",
};

/** Точка состояния облачных сборок локальной Студии. */
export const REMOTE_STATE_DOT: Record<RemoteRunnerState, StatusDotStatus> = {
  off: "neutral",
  unpaired: "neutral",
  pairing: "info",
  connecting: "info",
  online: "online",
  paused: "paused",
  offline: "stale",
  revoked: "danger",
  disabled: "neutral",
  error: "danger",
};

/**
 * Код сопряжения из ввода человека и маска поля ввода: те же правила, что у
 * входа устройства в git сервера, поэтому реализация общая (shared/ui/DeviceCodeCard).
 */
export {
  maskDeviceCode as maskUserCode,
  normalizeDeviceCode as normalizeUserCode,
} from "@shared/ui/DeviceCodeCard";

/** Сравнение версий вида 0.3.0: по числам, а не по строкам. */
export const compareVersions = (a: string, b: string): number => {
  const pa = a.split(".").map((x) => Number.parseInt(x, 10) || 0);
  const pb = b.split(".").map((x) => Number.parseInt(x, 10) || 0);
  for (let i = 0; i < Math.max(pa.length, pb.length); i += 1) {
    const d = (pa[i] ?? 0) - (pb[i] ?? 0);
    if (d !== 0) return d;
  }
  return 0;
};

/** Раннер старше сервера: стоит обновить. Пустая версия сервера ничего не говорит. */
export const isRunnerOutdated = (
  runnerVersion: string,
  serverVersion: string,
): boolean =>
  serverVersion !== "" &&
  runnerVersion !== "" &&
  compareVersions(runnerVersion, serverVersion) < 0;

const LOOPBACK = new Set(["localhost", "127.0.0.1"]);

/**
 * Адрес сервера для облачных сборок: https, а http только для localhost и
 * 127.0.0.1 (так же проверяет локальный api, remote_runner_url_invalid).
 */
export const isValidServerUrl = (value: string): boolean => {
  try {
    const url = new URL(value.trim());
    if (url.hostname === "") return false;
    if (url.protocol === "https:") return true;
    return url.protocol === "http:" && LOOPBACK.has(url.hostname);
  } catch {
    return false;
  }
};

const MAX_NAME = 32;

/** Имя ИИ-адреса по умолчанию из имени провайдера: латиница, цифры, дефис. */
export const endpointSlug = (name: string): string => {
  const slug = name
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/^[-_]+|[-_]+$/g, "")
    .slice(0, MAX_NAME);
  return ENDPOINT_NAME_RE.test(slug) ? slug : "model";
};

export const isValidEndpointName = (name: string): boolean =>
  ENDPOINT_NAME_RE.test(name);
