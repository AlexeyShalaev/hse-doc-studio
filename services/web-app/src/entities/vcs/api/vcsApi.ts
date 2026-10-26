import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";
import {
  type VcsSyncFilter,
  VcsBranchSchema,
  VcsCommitDetailSchema,
  VcsCommitSchema,
  VcsDiffSchema,
  VcsHistoryFacetsSchema,
  VcsRestoreSchema,
  VcsSettingsSchema,
  VcsStatusSchema,
  VcsTagSchema,
} from "./vcsSchemas";

export type RestoreParams = {
  commit_id: string;
  mode?: "snapshot" | "hard";
  paths?: string[];
  confirm?: boolean;
};

// Фильтры истории. Пустое поле не уходит в запрос; kind повторяется в адресе.
export type VcsHistoryParams = {
  docId?: string;
  kind?: string[];
  authorEmail?: string;
  q?: string;
  since?: string;
  until?: string;
  sync?: VcsSyncFilter;
  limit?: number;
  offset?: number;
};

export type DiffParams = {
  fromId?: string;
  toId?: string;
  path?: string;
};

export type UpdateVcsSettingsParams = {
  tracking_enabled?: boolean;
  auto_commit_on_compile?: boolean;
  track_pdf?: boolean;
};

export type CreateBranchParams = {
  name: string;
  from_commit?: string;
  switch?: boolean;
};

export type CreateTagParams = {
  name: string;
  commit_id?: string;
  message?: string;
  kind?: "tag" | "release";
};

// Пустая строка в фильтре означает «не задано»: в запрос она не попадает.
const blankToUndefined = (value: string | undefined): string | undefined =>
  value === undefined || value === "" ? undefined : value;

export const vcsApi = {
  getStatus: (projectId: string) =>
    apiClient
      .get(`/projects/${projectId}/vcs/status`)
      .then(parseResp(VcsStatusSchema)),

  getHistory: (projectId: string, docId?: string, limit = 100, offset = 0) =>
    apiClient
      .get(`/projects/${projectId}/vcs/history`, {
        params: { doc_id: docId, limit, offset },
      })
      .then(parseResp(VcsCommitSchema.array())),

  getHistoryPage: (projectId: string, params: VcsHistoryParams) =>
    apiClient
      .get(`/projects/${projectId}/vcs/history`, {
        params: {
          doc_id: params.docId,
          kind: params.kind?.length ? params.kind : undefined,
          author_email: blankToUndefined(params.authorEmail),
          q: blankToUndefined(params.q),
          since: blankToUndefined(params.since),
          until: blankToUndefined(params.until),
          sync: params.sync && params.sync !== "all" ? params.sync : undefined,
          limit: params.limit ?? 100,
          offset: params.offset ?? 0,
        },
        // kind=a&kind=b вместо kind[]=a, как ждёт бэкенд.
        paramsSerializer: { indexes: null },
      })
      .then(parseResp(VcsCommitSchema.array())),

  getHistoryFacets: (projectId: string) =>
    apiClient
      .get(`/projects/${projectId}/vcs/history/facets`)
      .then(parseResp(VcsHistoryFacetsSchema)),

  getCommit: (projectId: string, commitId: string) =>
    apiClient
      .get(`/projects/${projectId}/vcs/commits/${commitId}`)
      .then(parseResp(VcsCommitDetailSchema)),

  getDiff: (projectId: string, params: DiffParams) =>
    apiClient
      .get(`/projects/${projectId}/vcs/diff`, {
        params: {
          from_id: params.fromId,
          to_id: params.toId,
          path: params.path,
        },
      })
      .then(parseResp(VcsDiffSchema)),

  getSettings: (projectId: string) =>
    apiClient
      .get(`/projects/${projectId}/vcs/settings`)
      .then(parseResp(VcsSettingsSchema)),

  init: (projectId: string) =>
    apiClient
      .post(`/projects/${projectId}/vcs/init`, {})
      .then(parseResp(VcsStatusSchema)),

  createSnapshot: (projectId: string, message: string, docId?: string) =>
    apiClient
      .post(`/projects/${projectId}/vcs/snapshots`, {
        message,
        doc_id: docId,
      })
      .then(parseResp(VcsCommitSchema.nullable())),

  restore: (projectId: string, params: RestoreParams) =>
    apiClient
      .post(`/projects/${projectId}/vcs/restore`, params)
      .then(parseResp(VcsRestoreSchema)),

  updateSettings: (projectId: string, params: UpdateVcsSettingsParams) =>
    apiClient
      .patch(`/projects/${projectId}/vcs/settings`, params)
      .then(parseResp(VcsSettingsSchema)),

  listBranches: (projectId: string) =>
    apiClient
      .get(`/projects/${projectId}/vcs/branches`)
      .then(parseResp(VcsBranchSchema.array())),

  createBranch: (projectId: string, params: CreateBranchParams) =>
    apiClient
      .post(`/projects/${projectId}/vcs/branches`, params)
      .then(parseResp(VcsBranchSchema)),

  switchBranch: (projectId: string, name: string) =>
    apiClient
      .post(`/projects/${projectId}/vcs/branches/switch`, { name })
      .then(parseResp(VcsStatusSchema)),

  deleteBranch: (projectId: string, name: string) =>
    apiClient
      .delete(`/projects/${projectId}/vcs/branches`, { params: { name } })
      .then(parseResp(z.object({ deleted: z.boolean() }))),

  listTags: (projectId: string) =>
    apiClient
      .get(`/projects/${projectId}/vcs/tags`)
      .then(parseResp(VcsTagSchema.array())),

  createTag: (projectId: string, params: CreateTagParams) =>
    apiClient
      .post(`/projects/${projectId}/vcs/tags`, params)
      .then(parseResp(VcsTagSchema)),

  deleteTag: (projectId: string, name: string) =>
    apiClient
      .delete(`/projects/${projectId}/vcs/tags`, { params: { name } })
      .then(parseResp(z.object({ deleted: z.boolean() }))),
};
