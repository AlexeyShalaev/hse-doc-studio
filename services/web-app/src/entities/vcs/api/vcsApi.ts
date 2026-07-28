import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";
import {
  VcsBranchSchema,
  VcsCommitDetailSchema,
  VcsCommitSchema,
  VcsDiffSchema,
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
