import { apiClient, getCsrfToken, parseResp } from "@shared/api";
import {
  ProjectPeopleSchema,
  type PresenceSignal,
  type ProjectPeople,
} from "../model/people.schema";

// Ошибки не показываем: список людей украшение, а не причина для красного тоста.
const quiet = { silentError: true } as const;

export const peopleApi = {
  /** Сигнал вкладки; в ответе сразу список людей (отдельного запроса за списком нет). */
  signal: (projectId: string, body: PresenceSignal): Promise<ProjectPeople> =>
    apiClient
      .post(`/projects/${projectId}/presence`, body, quiet)
      .then(parseResp(ProjectPeopleSchema)),
  /**
   * Вкладка закрывается: сессия уходит из списка сразу. Обычный запрос на выгрузке страницы отменяется,
   * поэтому `keepalive`; CSRF-токен идёт заголовком, как у остальных небезопасных запросов.
   */
  leave: (projectId: string, sessionId: string): void => {
    const base = apiClient.defaults.baseURL ?? "";
    const csrf = getCsrfToken();
    void fetch(`${base}/projects/${projectId}/presence/${sessionId}`, {
      method: "DELETE",
      keepalive: true,
      credentials: "include",
      headers: csrf === null ? {} : { "X-CSRF-Token": csrf },
    }).catch(() => undefined);
  },
};
