import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";
import type {
  CreateProjectRequest,
  ConnectProjectRequest,
  UpdateProjectRequest,
} from "@shared/api/types";
import { CheckRuleSchema } from "@entities/document";
import {
  NdaStatusResponseSchema,
  ProjectResponseSchema,
  ProjectSuggestionsSchema,
} from "./projectSchemas";

export const projectApi = {
  list: () =>
    apiClient.get("/projects").then(parseResp(z.array(ProjectResponseSchema))),

  suggestions: () =>
    apiClient
      .get("/projects/suggestions")
      .then(parseResp(ProjectSuggestionsSchema)),

  get: (id: string) =>
    apiClient.get(`/projects/${id}`).then(parseResp(ProjectResponseSchema)),

  create: (data: CreateProjectRequest) =>
    apiClient.post("/projects", data).then(parseResp(ProjectResponseSchema)),

  connect: (data: ConnectProjectRequest) =>
    apiClient
      .post("/projects/connect", data)
      .then(parseResp(ProjectResponseSchema)),

  update: (id: string, data: UpdateProjectRequest) =>
    apiClient
      .patch(`/projects/${id}`, data)
      .then(parseResp(ProjectResponseSchema)),

  // Team mode: довключить/выключить комплект (папку автора или shared).
  // Выключение не удаляет файлы — только дерегистрирует документы.
  updateTeamSet: (
    id: string,
    data: { author_slug: string | null; enabled: boolean },
  ) =>
    apiClient
      .post(`/projects/${id}/team/sets`, data)
      .then(parseResp(ProjectResponseSchema)),

  remove: (id: string): Promise<void> =>
    apiClient.delete(`/projects/${id}`).then(() => undefined),

  move: (id: string, folder: string) =>
    apiClient
      .post(`/projects/${id}/move`, { folder })
      .then(parseResp(ProjectResponseSchema)),

  getCheckRules: (id: string) =>
    apiClient
      .get(`/projects/${id}/checks/rules`)
      .then(parseResp(z.array(CheckRuleSchema))),

  getNda: (id: string) =>
    apiClient
      .get(`/projects/${id}/nda`)
      .then(parseResp(NdaStatusResponseSchema)),

  instantiateNda: (id: string) =>
    apiClient
      .post(`/projects/${id}/nda/files`)
      .then(parseResp(NdaStatusResponseSchema)),

  deleteNdaFiles: (id: string) =>
    apiClient
      .delete(`/projects/${id}/nda/files`)
      .then(parseResp(NdaStatusResponseSchema)),
};
