import { apiClient, parseResp } from "@shared/api";
import {
  CiPreviewSchema,
  CiWriteSchema,
  OperationStartedSchema,
} from "@entities/git-sync";
import type { CiRequest, CiWriteRequest } from "@entities/git-sync";
import {
  CloneDefaultsSchema,
  GitCredentialListSchema,
  GitCredentialSchema,
  GitHostListSchema,
  ProbeSchema,
  SecretsStatusSchema,
  SharedFolderSchema,
  type CloneRequest,
  type CreateCredentialRequest,
  type ProbeRequest,
  type TrustHostRequest,
  type UpdateCredentialRequest,
} from "./gitRemoteSchemas";

export type CloneFromBundleParams = {
  file: File;
  folder: string;
  name?: string;
  password?: string;
};

// Секреты (токен, пароль файла) идут только в тело запроса и уходят с silentError:
// ошибку разбирает вызывающий по коду, а тост с деталями нам не нужен.
export const gitRemoteApi = {
  // --- доступы -----------------------------------------------------------------

  listCredentials: () =>
    apiClient.get("/git/credentials").then(parseResp(GitCredentialListSchema)),

  createCredential: (params: CreateCredentialRequest) =>
    apiClient
      .post("/git/credentials", params, { silentError: true })
      .then(parseResp(GitCredentialSchema)),

  updateCredential: (id: string, params: UpdateCredentialRequest) =>
    apiClient
      .patch(`/git/credentials/${id}`, params, { silentError: true })
      .then(parseResp(GitCredentialSchema)),

  // 409 credential_in_use несёт список проектов: окно спрашивает «всё равно?».
  deleteCredential: (id: string, force = false): Promise<void> =>
    apiClient
      .delete(`/git/credentials/${id}`, {
        params: { force },
        silentError: true,
      })
      .then(() => undefined),

  // --- ключи серверов ----------------------------------------------------------

  listHosts: () =>
    apiClient.get("/git/hosts").then(parseResp(GitHostListSchema)),

  trustHost: (params: TrustHostRequest): Promise<void> =>
    apiClient
      .post("/git/hosts/trust", params, { silentError: true })
      .then(() => undefined),

  deleteHost: (host: string, port?: number | null): Promise<void> =>
    apiClient
      .delete("/git/hosts", {
        params: { host, port: port ?? undefined },
        // Отказ показывает окно подтверждения, второй тост не нужен.
        silentError: true,
      })
      .then(() => undefined),

  getSecretsStatus: () =>
    apiClient.get("/git/secrets/status").then(parseResp(SecretsStatusSchema)),

  getSharedFolder: (folder: string) =>
    apiClient
      .get("/git/shared-folder", { params: { folder } })
      .then(parseResp(SharedFolderSchema)),

  // --- адрес и клонирование ----------------------------------------------------

  // Проверка отвечает 200 и при отказе (ok: false); 400 только за нечитаемый адрес.
  probe: (params: ProbeRequest) =>
    apiClient
      .post("/git/remote/probe", params, {
        silentError: true,
        timeout: 60_000,
      })
      .then(parseResp(ProbeSchema)),

  startClone: (params: CloneRequest) =>
    apiClient
      .post("/git/clone", params, { silentError: true })
      .then(parseResp(OperationStartedSchema)),

  startCloneFromBundle: (params: CloneFromBundleParams) => {
    const formData = new FormData();
    formData.append("file", params.file);
    formData.append("folder", params.folder);
    if (params.name) formData.append("name", params.name);
    if (params.password) formData.append("password", params.password);
    return apiClient
      .post("/git/clone/bundle", formData, {
        headers: { "Content-Type": null },
        silentError: true,
        timeout: 300_000,
      })
      .then(parseResp(OperationStartedSchema));
  },

  getCloneDefaults: (name?: string) =>
    apiClient
      .get("/git/clone/defaults", {
        params: { name: name === "" ? undefined : name },
      })
      .then(parseResp(CloneDefaultsSchema)),

  // --- сборка в CI -------------------------------------------------------------

  previewCi: (projectId: string, params: CiRequest) =>
    apiClient
      .post(`/projects/${projectId}/git/ci/preview`, params)
      .then(parseResp(CiPreviewSchema)),

  writeCi: (projectId: string, params: CiWriteRequest) =>
    apiClient
      .post(`/projects/${projectId}/git/ci/write`, params)
      .then(parseResp(CiWriteSchema)),
};
