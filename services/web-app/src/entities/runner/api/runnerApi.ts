import { apiClient, parseResp } from "@shared/api";
import {
  CompilePlacementSchema,
  MyRunnerListSchema,
  MyRunnerRotatedSchema,
  MyRunnerSchema,
  MyRunnerTokenCreatedSchema,
  MyRunnerTokenListSchema,
  ProjectBuildRunnersSchema,
  RemoteRunnerStatusSchema,
  RunnerPairingInfoSchema,
  type BuildRunnersPolicy,
  type CompilePlacement,
  type CreateMyRunnerTokenRequest,
  type MyRunner,
  type MyRunnerRotated,
  type MyRunnerToken,
  type MyRunnerTokenCreated,
  type ProjectBuildRunners,
  type RemoteRunnerStatus,
  type RunnerPairingDecision,
  type RunnerPairingInfo,
  type UpdateMyRunnerRequest,
  type UpdateRemoteRunnerRequest,
} from "../model/runner.schema";

// Ошибки показывают сами экраны (тост с текстом кода или блок с повтором):
// общий тост клиента здесь лишний.
const quiet = { silentError: true } as const;
const enc = encodeURIComponent;

/** Мои раннеры и токены регистрации (/api/v1/account/runners*, раздел 9.1 спецификации). */
export const myRunnersApi = {
  list: (): Promise<MyRunner[]> =>
    apiClient
      .get("/account/runners", quiet)
      .then(parseResp(MyRunnerListSchema)),
  update: (id: string, body: UpdateMyRunnerRequest): Promise<MyRunner> =>
    apiClient
      .patch(`/account/runners/${enc(id)}`, body, quiet)
      .then(parseResp(MyRunnerSchema)),
  rotate: (id: string): Promise<MyRunnerRotated> =>
    apiClient
      .post(`/account/runners/${enc(id)}/rotate-token`, {}, quiet)
      .then(parseResp(MyRunnerRotatedSchema)),
  revoke: async (id: string): Promise<void> => {
    await apiClient.delete(`/account/runners/${enc(id)}`, quiet);
  },

  tokens: (): Promise<MyRunnerToken[]> =>
    apiClient
      .get("/account/runner-tokens", quiet)
      .then(parseResp(MyRunnerTokenListSchema)),
  createToken: (
    body: CreateMyRunnerTokenRequest,
  ): Promise<MyRunnerTokenCreated> =>
    apiClient
      .post("/account/runner-tokens", body, quiet)
      .then(parseResp(MyRunnerTokenCreatedSchema)),
  revokeToken: async (id: string): Promise<void> => {
    await apiClient.delete(`/account/runner-tokens/${enc(id)}`, quiet);
  },

  pairing: (userCode: string): Promise<RunnerPairingInfo> =>
    apiClient
      .get(`/account/runner-pairings/${enc(userCode)}`, quiet)
      .then(parseResp(RunnerPairingInfoSchema)),
  decidePairing: (
    userCode: string,
    decision: RunnerPairingDecision,
  ): Promise<RunnerPairingInfo> =>
    apiClient
      .post(`/account/runner-pairings/${enc(userCode)}`, { decision }, quiet)
      .then(parseResp(RunnerPairingInfoSchema)),
};

/** Где идут сборки проекта (/api/v1/projects/{id}/build-runners, раздел 9.2). */
export const projectBuildRunnersApi = {
  get: (projectId: string): Promise<ProjectBuildRunners> =>
    apiClient
      .get(`/projects/${enc(projectId)}/build-runners`, quiet)
      .then(parseResp(ProjectBuildRunnersSchema)),
  update: (
    projectId: string,
    policy: BuildRunnersPolicy,
  ): Promise<ProjectBuildRunners> =>
    apiClient
      .put(`/projects/${enc(projectId)}/build-runners`, { policy }, quiet)
      .then(parseResp(ProjectBuildRunnersSchema)),
};

/** Разобрать тело события `placement` потока сборки; непонятное тело даёт null. */
export const parsePlacement = (data: unknown): CompilePlacement | null => {
  const parsed = CompilePlacementSchema.safeParse(data);
  return parsed.success ? parsed.data : null;
};

/** Облачные сборки локальной Студии (/api/v1/remote-runner, только локальный режим, раздел 8.6). */
export const remoteRunnerApi = {
  status: (): Promise<RemoteRunnerStatus> =>
    apiClient
      .get("/remote-runner", quiet)
      .then(parseResp(RemoteRunnerStatusSchema)),
  update: (body: UpdateRemoteRunnerRequest): Promise<RemoteRunnerStatus> =>
    apiClient
      .put("/remote-runner", body, quiet)
      .then(parseResp(RemoteRunnerStatusSchema)),
  pair: (serverUrl: string, name: string): Promise<RemoteRunnerStatus> =>
    apiClient
      .post("/remote-runner/pair", { server_url: serverUrl, name }, quiet)
      .then(parseResp(RemoteRunnerStatusSchema)),
  useToken: (serverUrl: string, token: string): Promise<RemoteRunnerStatus> =>
    apiClient
      .post("/remote-runner/token", { server_url: serverUrl, token }, quiet)
      .then(parseResp(RemoteRunnerStatusSchema)),
  cancelPairing: (): Promise<RemoteRunnerStatus> =>
    apiClient
      .delete("/remote-runner/pairing", quiet)
      .then(parseResp(RemoteRunnerStatusSchema)),
  unpair: (): Promise<RemoteRunnerStatus> =>
    apiClient
      .delete("/remote-runner", quiet)
      .then(parseResp(RemoteRunnerStatusSchema)),
};
