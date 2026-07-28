import { apiClient, parseResp } from "@shared/api";
import type { UpdatePlacementRequest } from "@shared/api/types";
import {
  SignaturesStateSchema,
  PlacementSchema,
  UploadSignatureResponseSchema,
} from "./signatureSchemas";

export const signatureApi = {
  getState: (projectId: string) =>
    apiClient
      .get(`/projects/${projectId}/signatures`)
      .then(parseResp(SignaturesStateSchema)),

  updatePlacement: (
    projectId: string,
    docId: string,
    slotId: string,
    data: UpdatePlacementRequest,
  ) =>
    apiClient
      .patch(
        `/projects/${projectId}/signatures/placements/${docId}/${slotId}`,
        data,
      )
      .then(parseResp(PlacementSchema)),

  uploadPng: (projectId: string, slotId: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiClient
      .post(
        `/projects/${projectId}/signatures/slots/${slotId}/png`,
        formData,
        // Let axios/browser set the multipart boundary itself — otherwise
        // FormData payload arrives labelled as application/json and the
        // server's parser fails.
        { headers: { "Content-Type": null } },
      )
      .then(parseResp(UploadSignatureResponseSchema));
  },

  deletePng: (projectId: string, slotId: string): Promise<void> =>
    apiClient
      .delete(`/projects/${projectId}/signatures/slots/${slotId}/png`)
      .then(() => undefined),
};
