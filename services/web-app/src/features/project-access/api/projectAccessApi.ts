import { apiClient, parseResp } from "@shared/api";
import {
  ProjectAccessCandidateListSchema,
  ProjectAccessPageSchema,
  type ProjectAccessCandidate,
  type ProjectAccessEntry,
  type ProjectRole,
} from "@entities/session";

const enc = encodeURIComponent;

/** Кому и какую роль выдать: тело вызова панели, на сервер уходит в `PUT .../members/{kind}:{id}`. */
export type SetProjectAccessRequest = {
  subject_kind: "user" | "group";
  subject_id: string;
  role: ProjectRole;
};
const base = (projectId: string) => `/projects/${enc(projectId)}/members`;

// Запись идёт без молчания: отказ по роли показывает общий тост с названием роли.
// Остальные отказы панель показывает сама.
export const projectAccessApi = {
  // Сервер листает список сам; панель пока берёт одну страницу наибольшего размера.
  list: (projectId: string): Promise<ProjectAccessEntry[]> =>
    apiClient
      .get(base(projectId), { params: { limit: 200 }, silentError: true })
      .then(parseResp(ProjectAccessPageSchema))
      .then((page) => page.items),
  candidates: (
    projectId: string,
    q: string,
  ): Promise<ProjectAccessCandidate[]> =>
    apiClient
      .get(`${base(projectId)}/candidates`, {
        params: { q },
        silentError: true,
      })
      .then(parseResp(ProjectAccessCandidateListSchema))
      .then((list) => list.items),
  // Запись идёт ручками бэкенда PUT|DELETE .../members/{user|group}:{id}; список панель
  // перечитывает сама, поэтому ответ не нужен.
  set: async (
    projectId: string,
    body: SetProjectAccessRequest,
  ): Promise<void> => {
    await apiClient.put(
      `${base(projectId)}/${body.subject_kind}:${enc(body.subject_id)}`,
      {
        role: body.role,
        persona: null,
        can_share: false,
        show_sources: false,
        can_edit_all: false,
      },
    );
  },
  remove: async (
    projectId: string,
    kind: "user" | "group",
    subjectId: string,
  ): Promise<void> => {
    await apiClient.delete(`${base(projectId)}/${kind}:${enc(subjectId)}`);
  },
};
