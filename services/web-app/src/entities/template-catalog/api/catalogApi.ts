import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";
import {
  PackResponseSchema,
  VersionListItemSchema,
  VersionDetailSchema,
} from "./catalogSchemas";

export const catalogApi = {
  listPacks: () =>
    apiClient
      .get("/catalog/packs")
      .then(parseResp(z.array(PackResponseSchema))),

  listVersions: (packId: string, templateId: string) =>
    apiClient
      .get(`/catalog/packs/${packId}/templates/${templateId}/versions`)
      .then(parseResp(z.array(VersionListItemSchema))),

  getVersion: (packId: string, templateId: string, version: string) =>
    apiClient
      .get(
        `/catalog/packs/${packId}/templates/${templateId}/versions/${version}`,
      )
      .then(parseResp(VersionDetailSchema)),
};
