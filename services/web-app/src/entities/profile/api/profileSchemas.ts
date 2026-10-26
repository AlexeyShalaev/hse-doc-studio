import { z } from "zod";

// Профиль автора: имя и e-mail, которые попадают в публикуемые версии.

export const ProfileSchema = z.object({
  name: z.string().nullish(),
  email: z.string().nullish(),
  effective_name: z.string(),
  effective_email: z.string(),
  is_default: z.boolean(),
  commit_preview: z.string(),
});

export const ProfileRequestSchema = z.object({
  name: z.string(),
  email: z.string(),
});

// 422 на PUT /profile: стандартный список ошибок FastAPI с кодом правила.
export const ProfileValidationErrorSchema = z.object({
  detail: z.array(
    z.object({
      loc: z.array(z.union([z.string(), z.number()])),
      code: z.string(),
      msg: z.string(),
    }),
  ),
});

export type Profile = z.infer<typeof ProfileSchema>;
export type ProfileRequest = z.infer<typeof ProfileRequestSchema>;
export type ProfileValidationError = z.infer<
  typeof ProfileValidationErrorSchema
>;
