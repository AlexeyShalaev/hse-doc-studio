import { z } from "zod";
import { apiClient, parseResp } from "@shared/api";
import { env } from "@shared/config";

// Причины держим строкой, а не z.enum: бэкенд может завести новый код раньше,
// чем фронт научится его рисовать, и это не повод ронять парсинг ответа —
// незнакомая причина деградирует до общего текста.
export const DockerStatusSchema = z.object({
  available: z.boolean(),
  version: z.string().nullable(),
  detail: z.string().nullable(),
  reason: z.string().nullable().default(null),
  // gid владельца docker-сокета: из него собирается точная строка DOCKER_GID
  // для .env, когда доступ к сокету закрыт правами.
  socket_gid: z.number().int().nullable().default(null),
});

export type DockerStatus = z.infer<typeof DockerStatusSchema>;

export const LocalImageSchema = z.object({
  image: z.string(),
  repository: z.string(),
  tag: z.string(),
  id: z.string(),
  size_bytes: z.number().int().nonnegative(),
  created: z.string(),
});

export type LocalImage = z.infer<typeof LocalImageSchema>;

export const ImagesListResponseSchema = z.object({
  active_image: z.string(),
  allowed_repos: z.array(z.string()),
  installed: z.array(LocalImageSchema),
});

export type ImagesListResponse = z.infer<typeof ImagesListResponseSchema>;

export const RemoteTagSchema = z.object({
  name: z.string(),
  size_bytes: z.number().int().nonnegative(),
  last_updated: z.string().nullable(),
});

export type RemoteTag = z.infer<typeof RemoteTagSchema>;

export const RemoteTagsResponseSchema = z.object({
  repo: z.string(),
  tags: z.array(RemoteTagSchema),
});

export type RemoteTagsResponse = z.infer<typeof RemoteTagsResponseSchema>;

export const SetActiveImageResponseSchema = z.object({
  image: z.string(),
});

export type SetActiveImageResponse = z.infer<
  typeof SetActiveImageResponseSchema
>;

export const imagesApi = {
  dockerStatus: () =>
    apiClient.get(`/compile/docker-status`).then(parseResp(DockerStatusSchema)),

  list: () =>
    apiClient.get(`/compile/images`).then(parseResp(ImagesListResponseSchema)),

  listRemoteTags: (repo: string) =>
    apiClient
      .get(`/compile/images/remote`, { params: { repo } })
      .then(parseResp(RemoteTagsResponseSchema)),

  setActive: (image: string) =>
    apiClient
      .post(`/compile/images/active`, { image })
      .then(parseResp(SetActiveImageResponseSchema)),

  remove: (image: string) =>
    apiClient
      .delete(`/compile/images`, { params: { image } })
      .then(() => image),

  installStreamUrl: (image: string) =>
    `${env.VITE_API_BASE_URL}/api/v1/compile/images/install?image=${encodeURIComponent(image)}`,
};
