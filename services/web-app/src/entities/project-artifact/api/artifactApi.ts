import { apiClient, parseResp } from "@shared/api";
import { env } from "@shared/config";
import {
  ProjectArtifactListSchema,
  type ProjectArtifactList,
} from "../model/artifact.schema";

const base = (projectId: string): string => `/projects/${projectId}/artifacts`;

export const projectArtifactApi = {
  list: (projectId: string): Promise<ProjectArtifactList> =>
    apiClient
      .get(base(projectId), { silentError: true })
      .then(parseResp(ProjectArtifactListSchema)),
  remove: (projectId: string, artifactId: string): Promise<unknown> =>
    apiClient.delete(`${base(projectId)}/${artifactId}`),
};

/** Адрес файла для просмотрщика и ссылок: `file_url` бэкенда уже начинается с `/api/v1`. */
export const artifactFileUrl = (fileUrl: string): string =>
  `${env.VITE_API_BASE_URL}${fileUrl}`;
