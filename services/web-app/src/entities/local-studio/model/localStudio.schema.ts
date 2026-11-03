import { z } from "zod";

/** Ответ `GET /local-studio` облачной Студии. */
export const LocalStudioInfoSchema = z.strictObject({
  server_url: z.string(),
  server_version: z.string(),
  git_remote_enabled: z.boolean(),
  recommended_tag: z.string().nullable(),
  image: z.string(),
  install_base_url: z.string(),
  releases_url: z.string(),
  default_port: z.number().int(),
});
export type LocalStudioInfo = z.infer<typeof LocalStudioInfoSchema>;
