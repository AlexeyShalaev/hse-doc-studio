import { apiClient, parseResp } from "@shared/api";
import {
  DeviceAuthorizationInfoSchema,
  GitProjectPageSchema,
  GitServerListSchema,
  GitServerLoginSchema,
  ProjectGitRemoteSchema,
  type DeviceAuthorizationInfo,
  type DeviceDecisionRequest,
  type GitProjectPage,
  type GitServerList,
  type GitServerLogin,
  type GitServerLoginRequest,
  type ProjectGitRemote,
} from "../model/gitServer.schema";

// Ошибки показывают сами экраны (итог на странице /device, текст в мастере):
// общий тост клиента здесь лишний.
const quiet = { silentError: true } as const;
const enc = encodeURIComponent;

/** Страница /device на сервере: что просит устройство и решение человека (раздел 7.4). */
export const deviceApi = {
  info: (userCode: string): Promise<DeviceAuthorizationInfo> =>
    apiClient
      .get(`/account/device/${enc(userCode)}`, quiet)
      .then(parseResp(DeviceAuthorizationInfoSchema)),
  decide: (
    userCode: string,
    body: DeviceDecisionRequest,
  ): Promise<DeviceAuthorizationInfo> =>
    apiClient
      .post(`/account/device/${enc(userCode)}`, body, quiet)
      .then(parseResp(DeviceAuthorizationInfoSchema)),
};

/** Адрес клонирования проекта на сервере (раздел 7.6). */
export const projectGitRemoteApi = {
  get: (projectId: string): Promise<ProjectGitRemote> =>
    apiClient
      .get(`/projects/${enc(projectId)}/git-remote`, quiet)
      .then(parseResp(ProjectGitRemoteSchema)),
};

/** Локальная Студия: вход на сервер Студии кодом и его проекты (раздел 7.5). */
export const gitServersApi = {
  list: (): Promise<GitServerList> =>
    apiClient.get("/git/servers", quiet).then(parseResp(GitServerListSchema)),
  login: (body: GitServerLoginRequest): Promise<GitServerLogin> =>
    apiClient
      .post("/git/servers/login", body, quiet)
      .then(parseResp(GitServerLoginSchema)),
  loginState: (loginId: string): Promise<GitServerLogin> =>
    apiClient
      .get(`/git/servers/login/${enc(loginId)}`, quiet)
      .then(parseResp(GitServerLoginSchema)),
  cancelLogin: (loginId: string): Promise<void> =>
    apiClient
      .delete(`/git/servers/login/${enc(loginId)}`, quiet)
      .then(() => undefined),
  projects: (
    credentialId: string,
    params: { q?: string; limit?: number; offset?: number } = {},
  ): Promise<GitProjectPage> =>
    apiClient
      .get(`/git/servers/${enc(credentialId)}/projects`, {
        ...quiet,
        params,
      })
      .then(parseResp(GitProjectPageSchema)),
  forget: (credentialId: string): Promise<void> =>
    apiClient
      .delete(`/git/servers/${enc(credentialId)}`, quiet)
      .then(() => undefined),
};
