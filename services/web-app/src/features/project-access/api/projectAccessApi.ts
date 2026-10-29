import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";
import {
  ProjectAccessCandidateSchema,
  ProjectAccessEntrySchema,
  type ProjectAccessCandidate,
  type ProjectAccessEntry,
  type SetProjectAccessRequest,
} from "@entities/session";

const enc = encodeURIComponent;
const base = (projectId: string) => `/projects/${enc(projectId)}/members`;

// Запись идёт без молчания: отказ по роли показывает общий тост с названием роли.
// Остальные отказы панель показывает сама.
export const projectAccessApi = {
  list: (projectId: string): Promise<ProjectAccessEntry[]> =>
    apiClient
      .get(base(projectId), { silentError: true })
      .then(parseResp(z.array(ProjectAccessEntrySchema))),
  candidates: (
    projectId: string,
    q: string,
  ): Promise<ProjectAccessCandidate[]> =>
    apiClient
      .get(`${base(projectId)}/candidates`, {
        params: { q },
        silentError: true,
      })
      .then(parseResp(z.array(ProjectAccessCandidateSchema))),
  set: (
    projectId: string,
    body: SetProjectAccessRequest,
  ): Promise<ProjectAccessEntry> =>
    apiClient
      .put(base(projectId), body)
      .then(parseResp(ProjectAccessEntrySchema)),
  remove: async (
    projectId: string,
    kind: "user" | "group",
    subjectId: string,
  ): Promise<void> => {
    await apiClient.delete(`${base(projectId)}/${kind}/${enc(subjectId)}`);
  },
};
