import { z } from "zod";

export const SigningIdentityKindSchema = z.enum([
  "self_signed",
  "pkcs12",
  "pkcs11",
  "openpgp",
]);
export type SigningIdentityKind = z.infer<typeof SigningIdentityKindSchema>;

export const SignModeSchema = z.enum([
  "image",
  "image_crypto",
  "crypto_invisible",
  "detached",
  "detached_text",
]);
export type SignMode = z.infer<typeof SignModeSchema>;

export const SigningIdentitySchema = z.object({
  id: z.string().uuid(),
  label: z.string(),
  kind: SigningIdentityKindSchema,
  subject_cn: z.string(),
  not_after: z.string().datetime({ offset: true }),
  trusted: z.boolean(),
  created_at: z.string().datetime({ offset: true }),
  // OpenPGP: отпечаток первичного ключа и защита паролем.
  fingerprint: z.string().nullish().default(null),
  protected: z.boolean().optional().default(false),
});
export type SigningIdentity = z.infer<typeof SigningIdentitySchema>;

export const CreateSelfSignedRequestSchema = z.object({
  label: z.string().min(1).max(120),
  subject_cn: z.string().min(1).max(200),
  validity_days: z.number().int().min(1).max(3650).default(825),
});
export type CreateSelfSignedRequest = z.infer<
  typeof CreateSelfSignedRequestSchema
>;

export const UpdateSlotConfigRequestSchema = z.object({
  signing_identity_id: z.string().uuid().nullable(),
  sign_mode: SignModeSchema,
  sign_reason: z.string().optional().default(""),
});
export type UpdateSlotConfigRequest = z.infer<
  typeof UpdateSlotConfigRequestSchema
>;

export const OpenPgpKeySchema = z.object({
  fingerprint: z.string(),
  key_id: z.string(),
  uids: z.array(z.string()),
  has_secret: z.boolean(),
  algo: z.string(),
  created: z.string().nullable(),
  expires: z.string().nullable(),
});
export type OpenPgpKey = z.infer<typeof OpenPgpKeySchema>;

export const OpenPgpKeysSchema = z.object({
  available: z.boolean(),
  gpg_version: z.string().nullable(),
  keys: z.array(OpenPgpKeySchema),
});
export type OpenPgpKeys = z.infer<typeof OpenPgpKeysSchema>;

export const ImportOpenPgpKeyResponseSchema = z.object({
  identities: z.array(SigningIdentitySchema),
  public_keys: z.array(OpenPgpKeySchema),
});
export type ImportOpenPgpKeyResponse = z.infer<
  typeof ImportOpenPgpKeyResponseSchema
>;

export type GenerateOpenPgpKeyRequest = {
  name: string;
  email?: string;
  label?: string;
  passphrase?: string;
};

export const TrustedRootSchema = z.object({
  fingerprint: z.string(),
  subject: z.string(),
  not_before: z.string(),
  not_after: z.string(),
});
export type TrustedRoot = z.infer<typeof TrustedRootSchema>;
