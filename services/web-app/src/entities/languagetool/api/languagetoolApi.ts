import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";
import { env } from "@shared/config";

export const LanguageToolStatusSchema = z.object({
  docker_available: z.boolean(),
  docker_detail: z.string().nullable(),
  // Те же поля, что и у статуса образов компилятора: по ним рисуется общая
  // подсказка с починкой прав на docker-сокет.
  docker_reason: z.string().nullable().default(null),
  docker_socket_gid: z.number().int().nullable().default(null),
  active_image: z.string(),
  image_installed: z.boolean(),
  container_present: z.boolean(),
  container_running: z.boolean(),
  container_status: z.string().nullable(),
  healthy: z.boolean(),
  base_url: z.string().nullable(),
});

export type LanguageToolStatus = z.infer<typeof LanguageToolStatusSchema>;

export const LanguageToolImageSchema = z.object({
  image: z.string(),
  repository: z.string(),
  tag: z.string(),
  id: z.string(),
  size_bytes: z.number().int().nonnegative(),
  created: z.string(),
});

export type LanguageToolImage = z.infer<typeof LanguageToolImageSchema>;

export const LanguageToolImagesListSchema = z.object({
  active_image: z.string(),
  allowed_repos: z.array(z.string()),
  installed: z.array(LanguageToolImageSchema),
});

export type LanguageToolImagesList = z.infer<
  typeof LanguageToolImagesListSchema
>;

export const LanguageToolRemoteTagSchema = z.object({
  name: z.string(),
  size_bytes: z.number().int().nonnegative(),
  last_updated: z.string().nullable(),
});

export type LanguageToolRemoteTag = z.infer<typeof LanguageToolRemoteTagSchema>;

export const LanguageToolRemoteTagsSchema = z.object({
  repo: z.string(),
  tags: z.array(LanguageToolRemoteTagSchema),
});

export type LanguageToolRemoteTags = z.infer<
  typeof LanguageToolRemoteTagsSchema
>;

export const SetActiveLanguageToolImageSchema = z.object({
  image: z.string(),
});

export type SetActiveLanguageToolImage = z.infer<
  typeof SetActiveLanguageToolImageSchema
>;

export const languagetoolApi = {
  status: () =>
    apiClient
      .get(`/languagetool/status`)
      .then(parseResp(LanguageToolStatusSchema)),

  images: () =>
    apiClient
      .get(`/languagetool/images`)
      .then(parseResp(LanguageToolImagesListSchema)),

  listRemoteTags: (repo: string) =>
    apiClient
      .get(`/languagetool/images/remote`, { params: { repo } })
      .then(parseResp(LanguageToolRemoteTagsSchema)),

  setActive: (image: string) =>
    apiClient
      .post(`/languagetool/images/active`, { image })
      .then(parseResp(SetActiveLanguageToolImageSchema)),

  remove: (image: string) =>
    apiClient
      .delete(`/languagetool/images`, { params: { image } })
      .then(() => image),

  installStreamUrl: (image: string) =>
    `${env.VITE_API_BASE_URL}/api/v1/languagetool/images/install?image=${encodeURIComponent(image)}`,
};
