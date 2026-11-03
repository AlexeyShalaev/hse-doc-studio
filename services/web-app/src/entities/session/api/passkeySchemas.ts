import { z } from "zod";

// Зеркало services/api/hse_doc_studio/api/schemas/passkeys.py. Параметры церемоний (`options`) и
// ответ браузера (`credential`) идут в JSON WebAuthn: их разбирают библиотеки, здесь они непрозрачны.

const iso = z.string().min(1);
const opaque = z.record(z.string(), z.unknown());

export const PasskeyOptionsSchema = z.strictObject({ options: opaque });
export type PasskeyOptions = z.infer<typeof PasskeyOptionsSchema>;

export const PasskeyLoginRequestSchema = z.strictObject({
  credential: opaque,
});
export type PasskeyLoginRequest = z.infer<typeof PasskeyLoginRequestSchema>;

export const AccountPasskeySchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  created_at: iso,
  last_used_at: iso.nullable(),
  synced: z.boolean(),
  domain: z.string(),
  domain_matches: z.boolean(),
});
export type AccountPasskey = z.infer<typeof AccountPasskeySchema>;

export const AccountPasskeyListSchema = z.strictObject({
  items: z.array(AccountPasskeySchema),
  enabled: z.boolean(),
  domain: z.string().nullable(),
  has_password: z.boolean(),
  limit: z.number().int(),
});
export type AccountPasskeyList = z.infer<typeof AccountPasskeyListSchema>;

export const CreatePasskeyRequestSchema = z.strictObject({
  name: z.string().max(64).nullable(),
  credential: opaque,
});
export type CreatePasskeyRequest = z.infer<typeof CreatePasskeyRequestSchema>;

export const RenamePasskeyRequestSchema = z.strictObject({
  name: z.string().min(1).max(64),
});
export type RenamePasskeyRequest = z.infer<typeof RenamePasskeyRequestSchema>;

export const ReauthRequestSchema = z
  .strictObject({
    password: z.string().nullable(),
    credential: opaque.nullable(),
  })
  .refine((v) => (v.password === null) !== (v.credential === null), {
    message: "exactly one of password and credential",
  });
export type ReauthRequest = z.infer<typeof ReauthRequestSchema>;

export const ReauthResponseSchema = z.strictObject({ reauth_until: iso });
export type ReauthResponse = z.infer<typeof ReauthResponseSchema>;

export const AdminUserPasskeySchema = z.strictObject({
  id: z.string(),
  name: z.string(),
  created_at: iso,
  last_used_at: iso.nullable(),
  synced: z.boolean(),
  domain: z.string(),
});
export type AdminUserPasskey = z.infer<typeof AdminUserPasskeySchema>;

export const AdminUserPasskeyListSchema = z.strictObject({
  items: z.array(AdminUserPasskeySchema),
});
export type AdminUserPasskeyList = z.infer<typeof AdminUserPasskeyListSchema>;

export const AdminPasskeysResetSchema = z.strictObject({
  removed: z.number().int(),
});
export type AdminPasskeysReset = z.infer<typeof AdminPasskeysResetSchema>;

// Регистрация по приглашению сразу с passkey, без пароля (только приглашение на конкретный адрес).
export const PasskeySignupOptionsRequestSchema = z.strictObject({
  invitation_token: z.string().min(1),
  name: z.string(),
});
export type PasskeySignupOptionsRequest = z.infer<
  typeof PasskeySignupOptionsRequestSchema
>;

export const PasskeySignupRequestSchema = z.strictObject({
  invitation_token: z.string().min(1),
  name: z.string(),
  passkey_name: z.string().max(64).nullable(),
  credential: opaque,
});
export type PasskeySignupRequest = z.infer<typeof PasskeySignupRequestSchema>;
