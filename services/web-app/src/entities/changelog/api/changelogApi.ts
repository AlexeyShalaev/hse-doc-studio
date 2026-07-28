import { apiClient } from "@shared/api/client";
import type {
  AddChangeLogEntryRequest,
  ChangeLogEntryResponse,
} from "@shared/api/types";

export const changelogApi = {
  list: (
    projectId: string,
    docId?: string,
  ): Promise<ChangeLogEntryResponse[]> =>
    apiClient
      .get(`/projects/${projectId}/changelog`, {
        params: docId ? { doc_id: docId } : undefined,
      })
      .then((r) => r.data as ChangeLogEntryResponse[]),

  addNote: (
    projectId: string,
    data: AddChangeLogEntryRequest,
  ): Promise<ChangeLogEntryResponse> =>
    apiClient
      .post(`/projects/${projectId}/changelog`, data)
      .then((r) => r.data as ChangeLogEntryResponse),
};
