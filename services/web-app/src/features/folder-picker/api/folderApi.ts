import { apiClient, parseResp } from "@shared/api";
import { BrowseResponseSchema, InspectResponseSchema } from "./folderSchemas";

export const folderApi = {
  browse: (path?: string | null) =>
    apiClient
      .get("/fs/browse", { params: path ? { path } : {} })
      .then(parseResp(BrowseResponseSchema)),

  inspect: (path: string) =>
    apiClient
      .get("/fs/inspect", { params: { path } })
      .then(parseResp(InspectResponseSchema)),
};
