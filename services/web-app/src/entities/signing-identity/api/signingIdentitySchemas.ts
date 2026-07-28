import { z } from "zod";

export const SigningIdentityKindSchema = z.enum([
  "self_signed",
  "pkcs12",
  "pkcs11",
]);
export type SigningIdentityKind = z.infer<typeof SigningIdentityKindSchema>;

export const SignModeSchema = z.enum([
  "image",
  "image_crypto",
  "crypto_invisible",
  "detached",
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
