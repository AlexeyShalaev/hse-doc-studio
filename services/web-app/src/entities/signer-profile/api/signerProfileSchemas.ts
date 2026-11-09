import { z } from "zod";

// Профиль подписанта (только сервер): картинка подписи и данные плашки из
// сертификата или открытого ключа OpenPGP. Сами файлы в ответ не входят.
export const ProfileImageSchema = z.object({
  sha256: z.string(),
  size: z.number().int(),
  width_px: z.number().int().nullable(),
  height_px: z.number().int().nullable(),
  updated_at: z.string().datetime({ offset: true }),
});
export type ProfileImage = z.infer<typeof ProfileImageSchema>;

export const ProfilePublicKeySchema = z.object({
  kind: z.enum(["x509", "openpgp"]),
  owner: z.string(),
  // Серийный номер сертификата или id ключа OpenPGP, как на плашке.
  cert_id: z.string(),
  valid_from: z.string().nullable(),
  valid_to: z.string().nullable(),
  // SHA-256 сертификата или отпечаток ключа: с ним сверяется пришедшая подпись.
  signer_id: z.string(),
  level: z.string(),
  updated_at: z.string().datetime({ offset: true }),
});
export type ProfilePublicKey = z.infer<typeof ProfilePublicKeySchema>;

export const SignerProfileSchema = z.object({
  image: ProfileImageSchema.nullable(),
  public_key: ProfilePublicKeySchema.nullable(),
});
export type SignerProfile = z.infer<typeof SignerProfileSchema>;
