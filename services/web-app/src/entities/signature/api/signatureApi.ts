import { apiClient, parseResp } from "@shared/api";
import { env } from "@shared/config";
import type { UpdatePlacementRequest } from "@shared/api/types";
import {
  AttachDetachedResponseSchema,
  FreezePdfResponseSchema,
  SignaturesStateSchema,
  PlacementSchema,
  SlotInfoSchema,
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

  freezePdf: (projectId: string, docId: string) =>
    apiClient
      .post(`/projects/${projectId}/docs/${docId}/frozen`)
      .then(parseResp(FreezePdfResponseSchema)),

  unfreezePdf: (projectId: string, docId: string): Promise<void> =>
    apiClient
      .delete(`/projects/${projectId}/docs/${docId}/frozen`)
      .then(() => undefined),

  attachDetached: (
    projectId: string,
    docId: string,
    slotId: string,
    file: File,
    publicKey?: File,
  ) => {
    const formData = new FormData();
    formData.append("file", file);
    if (publicKey) formData.append("public_key", publicKey);
    return apiClient
      .post(
        `/projects/${projectId}/docs/${docId}/detached/${slotId}`,
        formData,
        {
          headers: { "Content-Type": null },
        },
      )
      .then(parseResp(AttachDetachedResponseSchema));
  },

  recheckDetached: (
    projectId: string,
    docId: string,
    slotId: string,
    publicKey?: File,
  ) => {
    const formData = new FormData();
    if (publicKey) formData.append("public_key", publicKey);
    return apiClient
      .post(
        `/projects/${projectId}/docs/${docId}/detached/${slotId}/recheck`,
        formData,
        { headers: { "Content-Type": null } },
      )
      .then(parseResp(AttachDetachedResponseSchema));
  },

  signInStudio: (
    projectId: string,
    docId: string,
    slotId: string,
    identityId: string,
    passphrase: string,
  ) =>
    apiClient
      .post(`/projects/${projectId}/docs/${docId}/detached/${slotId}/sign`, {
        identity_id: identityId,
        passphrase,
      })
      .then(parseResp(AttachDetachedResponseSchema)),

  deleteDetached: (
    projectId: string,
    docId: string,
    slotId: string,
  ): Promise<void> =>
    apiClient
      .delete(`/projects/${projectId}/docs/${docId}/detached/${slotId}`)
      .then(() => undefined),

  setSignerFromFile: (projectId: string, slotId: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiClient
      .post(
        `/projects/${projectId}/signatures/slots/${slotId}/signer/file`,
        formData,
        { headers: { "Content-Type": null } },
      )
      .then(parseResp(SlotInfoSchema));
  },

  setSigner: (
    projectId: string,
    slotId: string,
    data:
      | { identity_id: string }
      | {
          owner: string;
          cert_id?: string;
          valid_from?: string | null;
          valid_to?: string | null;
        },
  ) =>
    apiClient
      .put(`/projects/${projectId}/signatures/slots/${slotId}/signer`, data)
      .then(parseResp(SlotInfoSchema)),

  clearSigner: (projectId: string, slotId: string) =>
    apiClient
      .delete(`/projects/${projectId}/signatures/slots/${slotId}/signer`)
      .then(parseResp(SlotInfoSchema)),

  deletePng: (projectId: string, slotId: string): Promise<void> =>
    apiClient
      .delete(`/projects/${projectId}/signatures/slots/${slotId}/png`)
      .then(() => undefined),
};

// Прямые ссылки для скачивания (браузер сам ставит имя файла из заголовка).
const docBase = (projectId: string, docId: string): string =>
  `${env.VITE_API_BASE_URL}/api/v1/projects/${projectId}/docs/${docId}`;

export const signatureDownloadUrls = {
  frozenPdf: (projectId: string, docId: string): string =>
    `${docBase(projectId, docId)}/frozen/pdf`,
  signingPackage: (
    projectId: string,
    docId: string,
    mode: "request" | "signed",
  ): string => `${docBase(projectId, docId)}/signing-package?mode=${mode}`,
  detachedFile: (projectId: string, docId: string, slotId: string): string =>
    `${docBase(projectId, docId)}/detached/${slotId}/file`,
};
