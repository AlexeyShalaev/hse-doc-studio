import { apiClient, parseResp } from "@shared/api";
import {
  CancelCloudBuildsResponseSchema,
  FetchBuildResponseSchema,
  LocalBuildsSchema,
  ProjectBuildsSchema,
  type CancelCloudBuildsResponse,
  type FetchBuildRequest,
  type FetchBuildResponse,
  type LocalBuilds,
  type ProjectBuilds,
} from "../model/build.schema";

const quiet = { silentError: true } as const;

/** Облако: где и когда собран каждый документ (`/projects/{id}/builds`). */
export const cloudBuildsApi = {
  list: (projectId: string): Promise<ProjectBuilds> =>
    apiClient
      .get(`/projects/${projectId}/builds`, quiet)
      .then(parseResp(ProjectBuildsSchema)),
};

/** Локальная Студия: сборки у себя и в облаке, получение готового PDF (`/projects/{id}/git/builds*`). */
export const localBuildsApi = {
  list: (projectId: string): Promise<LocalBuilds> =>
    apiClient
      .get(`/projects/${projectId}/git/builds`, quiet)
      .then(parseResp(LocalBuildsSchema)),
  fetch: (
    projectId: string,
    body: FetchBuildRequest,
  ): Promise<FetchBuildResponse> =>
    apiClient
      .post(`/projects/${projectId}/git/builds/fetch`, body, quiet)
      .then(parseResp(FetchBuildResponseSchema)),
  /** Остановить облачные сборки проекта (одного документа или всех) по входу этой Студии. */
  cancelCloud: (
    projectId: string,
    docId: string | null,
  ): Promise<CancelCloudBuildsResponse> =>
    apiClient
      .post(
        `/projects/${projectId}/git/builds/cancel`,
        { doc_id: docId },
        quiet,
      )
      .then(parseResp(CancelCloudBuildsResponseSchema)),
};
