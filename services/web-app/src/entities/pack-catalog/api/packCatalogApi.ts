import { adminClient, apiClient, parseResp } from "@shared/api";
import { archiveQuery, type ArchiveUploadFields } from "../lib/archiveQuery";
import {
  CatalogApplySchema,
  CatalogCheckSchema,
  CatalogEventListSchema,
  CatalogOverviewSchema,
  CatalogSourceSchema,
  WorkspaceCatalogSchema,
  type CatalogApply,
  type CatalogCheck,
  type CatalogEvent,
  type CatalogOverview,
  type CatalogSource,
  type CreateGitSourceRequest,
  type UpdateSourceRequest,
  type WorkspaceCatalog,
} from "./schemas";

// API «Каталогов паков» (contracts/pack-catalog/README.md): админка установки
// /api/admin/pack-catalog и папка рабочего пространства локально
// /api/v1/pack-studio/workspaces/{id}/catalog. Ошибки разбирает вызывающий: тосты молчат.

const quiet = { silentError: true } as const;
const enc = encodeURIComponent;
const BASE = "/pack-catalog";
const source = (id: string) => `${BASE}/sources/${enc(id)}`;
const workspaceCatalog = (id: string) =>
  `/pack-studio/workspaces/${enc(id)}/catalog`;

// Проверка тянет ревизию и разбирает паки в отдельном процессе (до двух минут на сервере),
// загрузка архива идёт сотнями мегабайт: запасы времени больше обычных 30 секунд.
const CHECK_TIMEOUT = 300_000;
const UPLOAD_TIMEOUT = 600_000;

const RAW = { "Content-Type": "application/octet-stream" } as const;

export const packCatalogApi = {
  overview: (): Promise<CatalogOverview> =>
    adminClient.get(BASE, quiet).then(parseResp(CatalogOverviewSchema)),
  addGit: (body: CreateGitSourceRequest): Promise<CatalogSource> =>
    adminClient
      .post(`${BASE}/sources`, body, quiet)
      .then(parseResp(CatalogSourceSchema)),
  /** Архив целиком телом запроса, поля строкой запроса. */
  addArchive: (
    file: Blob,
    fields: ArchiveUploadFields,
  ): Promise<CatalogSource> =>
    adminClient
      .post(`${BASE}/sources/archive`, file, {
        ...quiet,
        params: archiveQuery(fields),
        headers: RAW,
        timeout: UPLOAD_TIMEOUT,
      })
      .then(parseResp(CatalogSourceSchema)),
  replaceArchive: (
    id: string,
    file: Blob,
    name: string,
  ): Promise<CatalogSource> =>
    adminClient
      .put(`${source(id)}/archive`, file, {
        ...quiet,
        params: { name },
        headers: RAW,
        timeout: UPLOAD_TIMEOUT,
      })
      .then(parseResp(CatalogSourceSchema)),
  update: (id: string, body: UpdateSourceRequest): Promise<CatalogSource> =>
    adminClient
      .patch(source(id), body, quiet)
      .then(parseResp(CatalogSourceSchema)),
  remove: async (id: string): Promise<void> => {
    await adminClient.delete(source(id), quiet);
  },
  check: (id: string): Promise<CatalogCheck> =>
    adminClient
      .post(`${source(id)}/check`, {}, { ...quiet, timeout: CHECK_TIMEOUT })
      .then(parseResp(CatalogCheckSchema)),
  apply: (id: string, revision: string): Promise<CatalogApply> =>
    adminClient
      .post(
        `${source(id)}/apply`,
        { revision },
        { ...quiet, timeout: CHECK_TIMEOUT },
      )
      .then(parseResp(CatalogApplySchema)),
  history: (id: string): Promise<CatalogEvent[]> =>
    adminClient
      .get(`${source(id)}/history`, quiet)
      .then(parseResp(CatalogEventListSchema)),

  // Локально: папка рабочего пространства Студии шаблонов в каталоге этой Студии.
  workspace: (workspaceId: string): Promise<WorkspaceCatalog> =>
    apiClient
      .get(workspaceCatalog(workspaceId), quiet)
      .then(parseResp(WorkspaceCatalogSchema)),
  checkWorkspace: (
    workspaceId: string,
    replaceBuiltin: boolean,
  ): Promise<CatalogCheck> =>
    apiClient
      .post(
        `${workspaceCatalog(workspaceId)}/check`,
        { replace_builtin: replaceBuiltin },
        { ...quiet, timeout: CHECK_TIMEOUT },
      )
      .then(parseResp(CatalogCheckSchema)),
  applyWorkspace: (
    workspaceId: string,
    revision: string,
  ): Promise<CatalogApply> =>
    apiClient
      .post(
        `${workspaceCatalog(workspaceId)}/apply`,
        { revision },
        { ...quiet, timeout: CHECK_TIMEOUT },
      )
      .then(parseResp(CatalogApplySchema)),
  setWorkspaceEnabled: (
    workspaceId: string,
    enabled: boolean,
  ): Promise<WorkspaceCatalog> =>
    apiClient
      .patch(workspaceCatalog(workspaceId), { enabled }, quiet)
      .then(parseResp(WorkspaceCatalogSchema)),
  disconnectWorkspace: async (workspaceId: string): Promise<void> => {
    await apiClient.delete(workspaceCatalog(workspaceId), quiet);
  },
};
