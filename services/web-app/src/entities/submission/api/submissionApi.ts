import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";
import type { CreateSubmissionRequest } from "@shared/api/types";
import {
  CustomFilePreflightResponseSchema,
  SubmissionProfileSchema,
  SubmissionRecordSchema,
} from "./submissionSchemas";

export type PreflightCustomFilesParams = {
  profile_id: string;
  archive_format?: string;
  author_slug?: string;
};

export const submissionApi = {
  getProfiles: (projectId: string) =>
    apiClient
      .get(`/projects/${projectId}/submissions/profiles`)
      .then(parseResp(z.array(SubmissionProfileSchema))),

  create: (projectId: string, data: CreateSubmissionRequest) =>
    apiClient
      .post(`/projects/${projectId}/submissions`, data)
      .then(parseResp(SubmissionRecordSchema)),

  list: (projectId: string) =>
    apiClient
      .get(`/projects/${projectId}/submissions`)
      .then(parseResp(z.array(SubmissionRecordSchema))),

  downloadUrl: (projectId: string, submissionId: string): string =>
    `/api/v1/projects/${projectId}/submissions/${submissionId}/download`,

  preflightCustomFiles: (
    projectId: string,
    params: PreflightCustomFilesParams,
  ) =>
    apiClient
      .get(`/projects/${projectId}/submissions/preflight`, { params })
      .then(parseResp(CustomFilePreflightResponseSchema)),
};
