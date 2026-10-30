import { z } from "zod";
import { apiClient, listPageOf, parseResp } from "@shared/api";
import type { ListPage, ListRequestParams } from "@shared/lib";
import {
  ProjectAccessCandidateSchema,
  ProjectAccessEntrySchema,
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

// Список доступа по контракту: страница с total; прежний сервер отдаёт массив,
// он показывается одной страницей.
const AccessPageSchema = z.union([
  listPageOf(ProjectAccessEntrySchema),
  z.array(ProjectAccessEntrySchema).transform((items) => ({
    items,
    total: items.length,
    limit: items.length,
    offset: 0,
  })),
]);
// Кандидаты по контракту пикера: до 20 и признак «уточните поиск».
const CandidatesSchema = z.union([
  z.strictObject({
    items: z.array(ProjectAccessCandidateSchema),
    has_more: z.boolean(),
  }),
  z
    .array(ProjectAccessCandidateSchema)
    .transform((items) => ({ items, has_more: false })),
]);

export type CandidatePage = {
  items: ProjectAccessCandidate[];
  has_more: boolean;
};

// Запись идёт без молчания: отказ по роли показывает общий тост с названием роли.
// Остальные отказы панель показывает сама.
export const projectAccessApi = {
  list: (
    projectId: string,
    params: ListRequestParams,
    signal: AbortSignal,
  ): Promise<ListPage<ProjectAccessEntry>> =>
    apiClient
      .get(base(projectId), { silentError: true, signal, params })
      .then(parseResp(AccessPageSchema)),
  candidates: (
    projectId: string,
    q: string,
    limit: number,
    signal: AbortSignal,
  ): Promise<CandidatePage> =>
    apiClient
      .get(`${base(projectId)}/candidates`, {
        params: { q, limit },
        silentError: true,
        signal,
      })
      .then(parseResp(CandidatesSchema)),
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
