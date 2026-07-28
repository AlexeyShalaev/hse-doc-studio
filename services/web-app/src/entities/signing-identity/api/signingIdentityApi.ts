import { apiClient, parseResp } from "@shared/api";
import { z } from "zod";
import type {
  CreateSelfSignedRequest,
  UpdateSlotConfigRequest,
} from "./signingIdentitySchemas";
import { SigningIdentitySchema } from "./signingIdentitySchemas";

// Inline schema matching SlotInfoResponse — avoids cross-entity imports (FSD).
const SlotInfoResponseSchema = z.object({
  png_path: z.string().nullable(),
  natural_width_px: z.number().nullable(),
  natural_height_px: z.number().nullable(),
  signing_identity_id: z.string().uuid().nullable().optional().default(null),
  sign_mode: z
    .enum(["image", "image_crypto", "crypto_invisible", "detached"])
    .optional()
    .default("image"),
  sign_reason: z.string().optional().default(""),
});

const SigningIdentityListSchema = z.array(SigningIdentitySchema);

export const signingIdentityApi = {
  list: () =>
    apiClient
      .get("/signing-identities")
      .then(parseResp(SigningIdentityListSchema)),

  createSelfSigned: (data: CreateSelfSignedRequest) =>
    apiClient
      .post("/signing-identities/self-signed", data)
      .then(parseResp(SigningIdentitySchema)),

  importPkcs12: (
    label: string,
    file: File,
    passphrase?: string,
  ): Promise<z.infer<typeof SigningIdentitySchema>> => {
    const formData = new FormData();
    formData.append("label", label);
    formData.append("file", file);
    if (passphrase) formData.append("passphrase", passphrase);
    return apiClient
      .post("/signing-identities/import-pkcs12", formData, {
        headers: { "Content-Type": null },
      })
      .then(parseResp(SigningIdentitySchema));
  },

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
