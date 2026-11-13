import { apiClient, parseResp } from "@shared/api";
import { env } from "@shared/config";
import type { UpdatePlacementRequest } from "@shared/api/types";
import {
  AttachDetachedResponseSchema,
  FreezePdfResponseSchema,
  SignaturesStateSchema,
  SignaturePlanSchema,
  SignPreviewSchema,
  SignSubmissionResultSchema,
  PlacementSchema,
  SlotInfoSchema,
  SlotOptionalSchema,
  UploadSignatureResponseSchema,
  type SetDateMarksRequest,
} from "./signatureSchemas";

export type SignSubmissionBody = {
  profile_id: string;
  author?: string | null | undefined;
  identity_id?: string | null | undefined;
  passphrase?: string | undefined;
  confirm_reset?: boolean | undefined;
  expected?: Record<string, string> | undefined;
};

export const signatureApi = {
  getState: (projectId: string) =>
    apiClient
      .get(`/projects/${projectId}/signatures`)
      .then(parseResp(SignaturesStateSchema)),

  getPlan: (
    projectId: string,
    params: {
      profileId?: string | null | undefined;
      author?: string | null | undefined;
      docId?: string | null | undefined;
    } = {},
    signal?: AbortSignal,
  ) =>
    apiClient
      .get(`/projects/${projectId}/signature-plan`, {
        params: {
          ...(params.profileId ? { profile_id: params.profileId } : {}),
          ...(params.author ? { author: params.author } : {}),
          ...(params.docId ? { doc_id: params.docId } : {}),
        },
        ...(signal ? { signal } : {}),
      })
      .then(parseResp(SignaturePlanSchema)),

  previewSignSubmission: (projectId: string, body: SignSubmissionBody) =>
    apiClient
      .post(`/projects/${projectId}/signature-plan/sign-preview`, body)
      .then(parseResp(SignPreviewSchema)),

  signSubmission: (projectId: string, body: SignSubmissionBody) =>
    apiClient
      .post(`/projects/${projectId}/signature-plan/sign`, body)
      .then(parseResp(SignSubmissionResultSchema)),

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

  /**
   * Метки даты слота документа целиком и ручная дата (signing-route.md, 14.7). 409
   * `resets_signatures` (с `resets`) окно подтверждения разбирает само: ответ без тоста.
   */
  setDateMarks: (
    projectId: string,
    docId: string,
    slotId: string,
    body: SetDateMarksRequest,
  ) =>
    apiClient
      .put(
        `/projects/${projectId}/signatures/placements/${encodeURIComponent(docId)}/${encodeURIComponent(slotId)}/dates`,
        body,
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

  /**
   * «Подписывать текущую сборку» (signing-route.md, 12.4): снять версию на подписи. Подписи,
   * поставленные на неё, перестают подходить к документу. Пока документ держит маршрут,
   * 409 `route_locked`; без версии на подписи тоже 204.
   */
  unpinVersion: (projectId: string, docId: string): Promise<void> =>
    apiClient
      .delete(`/projects/${projectId}/docs/${docId}/pinned`)
      .then(() => undefined),

  attachDetached: (
    projectId: string,
    docId: string,
    slotId: string,
    file: File,
    publicKey?: File,
    options?: { silent?: boolean },
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
          // Страница подписи показывает отказ сама, по коду из тела.
          ...(options?.silent ? { silentError: true } : {}),
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

  completeChain: (projectId: string, docId: string, slotId: string) =>
    apiClient
      .post(
        `/projects/${projectId}/docs/${docId}/detached/${slotId}/complete-chain`,
      )
      .then(parseResp(AttachDetachedResponseSchema)),

  trustRootFromChain: (fingerprint: string): Promise<void> =>
    apiClient
      .post(`/trusted-roots/from-chain/${fingerprint}`)
      .then(() => undefined),

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

  downloadFrozenPdf: (
    projectId: string,
    docId: string,
    options?: { silent?: boolean },
  ) =>
    apiClient
      .get(`/projects/${projectId}/docs/${docId}/frozen/pdf`, {
        responseType: "arraybuffer",
        ...(options?.silent ? { silentError: true } : {}),
      })
      .then((r) => new Uint8Array(r.data as ArrayBuffer)),

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

  setSignerLevel: (projectId: string, slotId: string, level: string) =>
    apiClient
      .put(`/projects/${projectId}/signatures/slots/${slotId}/signer/level`, {
        level,
      })
      .then(parseResp(SlotInfoSchema)),

  clearSigner: (projectId: string, slotId: string) =>
    apiClient
      .delete(`/projects/${projectId}/signatures/slots/${slotId}/signer`)
      .then(parseResp(SlotInfoSchema)),

  deletePng: (projectId: string, slotId: string): Promise<void> =>
    apiClient
      .delete(`/projects/${projectId}/signatures/slots/${slotId}/png`)
      .then(() => undefined),

  /** «Показать» картинку, которую придержал маршрут подписания (docs/design/signing-route.md, 5.6). */
  releaseWithheld: (
    projectId: string,
    docId: string,
    slotId: string,
  ): Promise<void> =>
    apiClient
      .delete(`/projects/${projectId}/signatures/withheld/${docId}/${slotId}`)
      .then(() => undefined),

  /** «Подпись необязательна» на точке `profile_id` (signing-route.md, 13.6). */
  setSlotOptional: (
    projectId: string,
    docId: string,
    slotId: string,
    body: { profile_id: string; optional: boolean },
  ) =>
    apiClient
      .put(
        `/projects/${projectId}/signatures/optional/${encodeURIComponent(docId)}/${encodeURIComponent(slotId)}`,
        body,
      )
      .then(parseResp(SlotOptionalSchema)),
};

// Прямые ссылки для скачивания (браузер сам ставит имя файла из заголовка).
const docBase = (projectId: string, docId: string): string =>
  `${env.VITE_API_BASE_URL}/api/v1/projects/${projectId}/docs/${docId}`;

export const signatureDownloadUrls = {
  frozenPdf: (projectId: string, docId: string): string =>
    `${docBase(projectId, docId)}/frozen/pdf`,
  /**
   * «С подписями»: источник подписи с видимым слоем, после фиксации сам B. У документа с версией
   * на подписи это она, а не текущая сборка: так «Открыть версию на подписи» (signing-route.md, 12.4).
   */
  signedPdf: (projectId: string, docId: string): string =>
    `${docBase(projectId, docId)}/pdf/signed`,
  signingPackage: (
    projectId: string,
    docId: string,
    mode: "request" | "signed",
  ): string => `${docBase(projectId, docId)}/signing-package?mode=${mode}`,
  detachedFile: (projectId: string, docId: string, slotId: string): string =>
    `${docBase(projectId, docId)}/detached/${slotId}/file`,
};
