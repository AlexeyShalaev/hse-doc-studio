import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";
import type { UpdateDocumentRequest } from "@shared/api/types";
import {
  CancelCompileResponseSchema,
  CheckResultsResponseSchema,
  CheckRuleSchema,
  CompileDetailSchema,
  CompileListItemSchema,
  DocumentResponseSchema,
  TriggerCompileResponseSchema,
} from "./documentSchemas";

export const documentApi = {
  list: (projectId: string) =>
    apiClient
      .get(`/projects/${projectId}/documents`)
      .then(parseResp(z.array(DocumentResponseSchema))),

  get: (projectId: string, docId: string) =>
    apiClient
      .get(`/projects/${projectId}/documents/${docId}`)
      .then(parseResp(DocumentResponseSchema)),

  update: (projectId: string, docId: string, data: UpdateDocumentRequest) =>
    apiClient
      .patch(`/projects/${projectId}/documents/${docId}`, data)
      .then(parseResp(DocumentResponseSchema)),

  triggerCompile: (projectId: string, docId: string) =>
    apiClient
      .post(`/projects/${projectId}/documents/${docId}/compile`)
      .then(parseResp(TriggerCompileResponseSchema)),

  cancelCompile: (projectId: string, compileId: string) =>
    apiClient
      .post(`/projects/${projectId}/compiles/${compileId}/cancel`)
      .then(parseResp(CancelCompileResponseSchema)),

  listCompiles: (projectId: string, docId: string) =>
    apiClient
      .get(`/projects/${projectId}/documents/${docId}/compiles`)
      .then(parseResp(z.array(CompileListItemSchema))),

  getCompile: (projectId: string, docId: string, compileId: string) =>
    apiClient
      .get(`/projects/${projectId}/documents/${docId}/compiles/${compileId}`)
      .then(parseResp(CompileDetailSchema)),

  getCheckResults: (projectId: string, docId: string, scope?: "document") =>
    apiClient
      .get(`/projects/${projectId}/documents/${docId}/checks`, {
        ...(scope ? { params: { scope } } : {}),
      })
      .then(parseResp(CheckResultsResponseSchema)),

  getCheckRules: (projectId: string, docId: string) =>
    apiClient
      .get(`/projects/${projectId}/documents/${docId}/checks/rules`)
      .then(parseResp(z.array(CheckRuleSchema))),

  uploadCustomFile: (projectId: string, docId: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiClient
      .post(
        `/projects/${projectId}/documents/${docId}/custom-file`,
        formData,
        // Let axios/browser set the multipart boundary itself — otherwise
        // FormData payload arrives labelled as application/json and the
        // server's parser fails.
        { headers: { "Content-Type": null } },
      )
      .then(parseResp(DocumentResponseSchema));
  },

  removeCustomFile: (projectId: string, docId: string, deleteFile = false) =>
    apiClient
      .delete(`/projects/${projectId}/documents/${docId}/custom-file`, {
        params: { delete_file: deleteFile },
      })
      .then(parseResp(DocumentResponseSchema)),
};
