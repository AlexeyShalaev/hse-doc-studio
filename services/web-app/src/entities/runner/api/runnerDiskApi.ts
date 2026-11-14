import type { AxiosInstance } from "axios";
import { adminClient, apiClient, parseResp } from "@shared/api";
import {
  RunnerDiskAutoSchema,
  RunnerDiskCommandSchema,
  RunnerDiskSummarySchema,
  RunnerDiskViewSchema,
  type RunnerDiskAuto,
  type RunnerDiskAutoRequest,
  type RunnerDiskCleanupRequest,
  type RunnerDiskCommand,
  type RunnerDiskSummary,
  type RunnerDiskView,
} from "../model/runnerDisk.schema";

// Диск раннера (docs/design/storage-cleanup.md, 9.1). Одни и те же адреса у админки
// (/api/admin/runners/{id}/disk*, только сессия) и у владельца (/api/v1/account/runners/{id}/disk*).
// Ошибки (409 runner_offline, runner_disk_busy и прочие) показывает сам диалог: тост не нужен.

const quiet = { silentError: true } as const;
const enc = encodeURIComponent;

/** Чей диск: админка видит любой неотозванный раннер, владелец только свой. */
export type RunnerDiskScope = "admin" | "account";

export type RunnerDiskApi = {
  get: (runnerId: string) => Promise<RunnerDiskView>;
  /** Поставить `disk.measure`; повторный запрос вернёт уже стоящую в очереди. */
  refresh: (runnerId: string) => Promise<RunnerDiskCommand>;
  cleanup: (
    runnerId: string,
    body: RunnerDiskCleanupRequest,
  ) => Promise<RunnerDiskCommand>;
  /** «Остановить после текущего шага». */
  cancel: (runnerId: string, commandId: string) => Promise<RunnerDiskCommand>;
};

const makeRunnerDiskApi = (
  client: AxiosInstance,
  base: string,
): RunnerDiskApi => {
  const disk = (id: string) => `${base}/${enc(id)}/disk`;
  return {
    get: (runnerId) =>
      client.get(disk(runnerId), quiet).then(parseResp(RunnerDiskViewSchema)),
    refresh: (runnerId) =>
      client
        .post(`${disk(runnerId)}/refresh`, {}, quiet)
        .then(parseResp(RunnerDiskCommandSchema)),
    cleanup: (runnerId, body) =>
      client
        .post(`${disk(runnerId)}/cleanup`, body, quiet)
        .then(parseResp(RunnerDiskCommandSchema)),
    cancel: (runnerId, commandId) =>
      client
        .post(`${disk(runnerId)}/commands/${enc(commandId)}/cancel`, {}, quiet)
        .then(parseResp(RunnerDiskCommandSchema)),
  };
};

/** Админка: /api/admin/runners/{id}/disk*. */
export const adminRunnerDiskApi: RunnerDiskApi & {
  summary: () => Promise<RunnerDiskSummary>;
  setAuto: (
    runnerId: string,
    body: RunnerDiskAutoRequest,
  ) => Promise<RunnerDiskAuto>;
} = {
  ...makeRunnerDiskApi(adminClient, "/runners"),
  /** Сводка общих раннеров для «Хранилища». */
  summary: () =>
    adminClient
      .get("/runners/disk-summary", quiet)
      .then(parseResp(RunnerDiskSummarySchema)),
  /** Автоочистка общего раннера по порогу места (14.5). */
  setAuto: (runnerId, body) =>
    adminClient
      .put(`/runners/${enc(runnerId)}/disk/auto`, body, quiet)
      .then(parseResp(RunnerDiskAutoSchema)),
};

/** «Мои раннеры»: /api/v1/account/runners/{id}/disk*. */
export const myRunnerDiskApi: RunnerDiskApi = makeRunnerDiskApi(
  apiClient,
  "/account/runners",
);

export const runnerDiskApi = (scope: RunnerDiskScope): RunnerDiskApi =>
  scope === "admin" ? adminRunnerDiskApi : myRunnerDiskApi;
