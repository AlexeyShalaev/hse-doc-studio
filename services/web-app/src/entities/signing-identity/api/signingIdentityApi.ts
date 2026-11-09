import { apiClient, parseResp } from "@shared/api";
import { env } from "@shared/config";
import { z } from "zod";
import type {
  CreateSelfSignedRequest,
  GenerateOpenPgpKeyRequest,
  UpdateSlotConfigRequest,
} from "./signingIdentitySchemas";
import {
  ImportOpenPgpKeyResponseSchema,
  OpenPgpKeysSchema,
  SigningIdentitySchema,
  TrustedRootSchema,
} from "./signingIdentitySchemas";

// Inline schema matching SlotInfoResponse — avoids cross-entity imports (FSD).
const SlotInfoResponseSchema = z.object({
  png_path: z.string().nullable(),
  natural_width_px: z.number().nullable(),
  natural_height_px: z.number().nullable(),
  signing_identity_id: z.string().uuid().nullable().optional().default(null),
  sign_mode: z
    .enum([
      "image",
      "image_crypto",
      "crypto_invisible",
      "detached",
      "detached_text",
    ])
    .optional()
    .default("image"),
  sign_reason: z.string().optional().default(""),
});

const SigningIdentityListSchema = z.array(SigningIdentitySchema);

// Ключ по умолчанию: им «Подписать комплект» подписывает свои слоты и заполняет
// плашку. identity_id — выбранный явно; effective_id — тот, что сработает (при
// единственном ключе он выбирается сам, auto = true).
const DefaultKeySchema = z.object({
  identity_id: z.string().uuid().nullable(),
  effective_id: z.string().uuid().nullable(),
  auto: z.boolean(),
});

export type DefaultKey = z.infer<typeof DefaultKeySchema>;

/** `silent`: ошибку показывает сам экран (по коду из тела), общий тост клиента лишний. */
type CallOptions = { silent?: boolean };
const quiet = (options?: CallOptions) =>
  options?.silent ? { silentError: true } : {};

export const signingIdentityApi = {
  list: () =>
    apiClient
      .get("/signing-identities")
      .then(parseResp(SigningIdentityListSchema)),

  getDefault: () =>
    apiClient
      .get("/signing-identities/default")
      .then(parseResp(DefaultKeySchema)),

  setDefault: (identityId: string | null) =>
    apiClient
      .put("/signing-identities/default", { identity_id: identityId })
      .then(parseResp(DefaultKeySchema)),

  createSelfSigned: (data: CreateSelfSignedRequest) =>
    apiClient
      .post("/signing-identities/self-signed", data)
      .then(parseResp(SigningIdentitySchema)),

  importPkcs12: (
    label: string,
    file: File,
    passphrase?: string,
    options?: CallOptions,
  ): Promise<z.infer<typeof SigningIdentitySchema>> => {
    const formData = new FormData();
    formData.append("label", label);
    formData.append("file", file);
    if (passphrase) formData.append("passphrase", passphrase);
    return apiClient
      .post("/signing-identities/import-pkcs12", formData, {
        headers: { "Content-Type": null },
        ...quiet(options),
      })
      .then(parseResp(SigningIdentitySchema));
  },

  generateOpenPgp: (data: GenerateOpenPgpKeyRequest, options?: CallOptions) =>
    apiClient
      .post("/signing-identities/openpgp/generate", data, quiet(options))
      .then(parseResp(SigningIdentitySchema)),

  importOpenPgp: (
    file: File,
    passphrase?: string,
    label?: string,
    options?: CallOptions,
  ) => {
    const formData = new FormData();
    formData.append("file", file);
    if (passphrase) formData.append("passphrase", passphrase);
    if (label) formData.append("label", label);
    return apiClient
      .post("/signing-identities/openpgp/import", formData, {
        headers: { "Content-Type": null },
        ...quiet(options),
      })
      .then(parseResp(ImportOpenPgpKeyResponseSchema));
  },

  listOpenPgpKeys: () =>
    apiClient
      .get("/signing-identities/openpgp/keys")
      .then(parseResp(OpenPgpKeysSchema)),

  listTrustedRoots: () =>
    apiClient.get("/trusted-roots").then(parseResp(z.array(TrustedRootSchema))),

  addTrustedRoot: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return apiClient
      .post("/trusted-roots", formData, { headers: { "Content-Type": null } })
      .then(parseResp(TrustedRootSchema));
  },

  deleteTrustedRoot: (fingerprint: string): Promise<void> =>
    apiClient.delete(`/trusted-roots/${fingerprint}`).then(() => undefined),

  delete: (id: string): Promise<void> =>
    apiClient.delete(`/signing-identities/${id}`).then(() => undefined),

  updateSlotConfig: (
    projectId: string,
    slotId: string,
    data: UpdateSlotConfigRequest,
  ) =>
    apiClient
      .patch(`/projects/${projectId}/signatures/slots/${slotId}/config`, data)
      .then(parseResp(SlotInfoResponseSchema)),
};

export const publicKeyUrl = (identityId: string): string =>
  `${env.VITE_API_BASE_URL}/api/v1/signing-identities/${identityId}/public-key`;
