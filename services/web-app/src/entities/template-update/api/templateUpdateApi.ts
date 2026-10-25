import { apiClient, parseResp } from "@shared/api";
import {
  ApplyTemplateUpdateResultSchema,
  CompareWithTemplateSchema,
  RevertTemplateUpdateResultSchema,
  TemplateDiffSchema,
  TemplateTrackingSchema,
  TemplateUpdatePlanSchema,
  TemplateUpdateStatusSchema,
} from "./templateUpdateSchemas";

export type ConflictResolution = "mine" | "theirs" | "markers";

// view: template — что меняет шаблон; mine — мои правки; result — итог обновления.
export type TemplateDiffView = "template" | "mine" | "result";

export type TemplateDiffParams = {
  path: string;
  view: TemplateDiffView;
  // Без версии — сравнение с текущей версией шаблона (только view=mine).
  toVersion?: string;
  resolution?: ConflictResolution;
};

export type ApplyTemplateUpdateParams = {
  to_version: string;
  fingerprint: string;
  resolutions: Record<string, ConflictResolution>;
};

export type RevertTemplateUpdateParams = {
  update_id?: string;
  dry_run?: boolean;
  resolutions?: Record<string, ConflictResolution>;
};

export const templateUpdateApi = {
  getStatus: (projectId: string) =>
    apiClient
      .get(`/projects/${projectId}/template-update`)
      .then(parseResp(TemplateUpdateStatusSchema)),

  plan: (projectId: string, toVersion: string) =>
    apiClient
      .post(
        `/projects/${projectId}/template-update/plan`,
        { to_version: toVersion },
        // Конфликт/недоступность показываем в окне предпросмотра, а не тостом.
        { silentError: true, timeout: 120_000 },
      )
      .then(parseResp(TemplateUpdatePlanSchema)),

  getDiff: (projectId: string, params: TemplateDiffParams) =>
    apiClient
      .get(`/projects/${projectId}/template-update/diff`, {
        params: {
          path: params.path,
          view: params.view,
          to_version: params.toVersion,
          resolution: params.resolution,
        },
      })
      .then(parseResp(TemplateDiffSchema)),

  apply: (projectId: string, params: ApplyTemplateUpdateParams) =>
    apiClient
      .post(`/projects/${projectId}/template-update/apply`, params, {
        // Планирование по 10–30 с на больших проектах — не таймаут клиента.
        timeout: 120_000,
      })
      .then(parseResp(ApplyTemplateUpdateResultSchema)),

  revert: (projectId: string, params: RevertTemplateUpdateParams) =>
    apiClient
      .post(`/projects/${projectId}/template-update/revert`, params, {
        timeout: 120_000,
      })
      .then(parseResp(RevertTemplateUpdateResultSchema)),

  compare: (projectId: string) =>
    apiClient
      .get(`/projects/${projectId}/template/compare`, { timeout: 120_000 })
      .then(parseResp(CompareWithTemplateSchema)),

  setTracking: (projectId: string, path: string, tracked: boolean) =>
    apiClient
      .put(`/projects/${projectId}/template/tracking`, { path, tracked })
      .then(parseResp(TemplateTrackingSchema)),
};
