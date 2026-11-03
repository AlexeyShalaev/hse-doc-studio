import { z } from "zod";
import type { Lang } from "@shared/api";

/**
 * Справка (services/user-docs) отдаётся тем же сервером по /help/: две статичные выдачи для
 * приложения — карта «экран → статьи» и статья данными. Один origin: ни CORS, ни токена; какую
 * сборку (пользователя или администратора) получить, сервер решает по cookie сессии.
 *
 * Приложение не знает ключей статей: какая статья у какого экрана, объявлено во frontmatter
 * статьи и опубликовано в карте. Справку экрану добавляют, не трогая фронтенд.
 */
export const HELP_BASE = "/help";

const ShotSchema = z.object({ light: z.string(), dark: z.string() });
const VideoVariantSchema = z.object({
  mp4: z.string(),
  poster: z.string(),
});

export const HelpStepSchema = z.object({
  text: z.string(),
  hint: z.string().optional(),
  shot: ShotSchema.optional(),
});

export const HelpArticleSchema = z.object({
  key: z.string(),
  title: z.string(),
  summary: z.string(),
  url: z.string(),
  routes: z.array(z.string()),
  steps: z.array(HelpStepSchema),
  video: z
    .object({
      light: VideoVariantSchema,
      dark: VideoVariantSchema,
      chapters: z.array(z.number()).default([]),
    })
    .optional(),
  verified: z.object({ at: z.string(), appVersion: z.string() }).optional(),
});

export const HelpMapSchema = z.object({
  routes: z.record(z.string(), z.array(z.string())),
  articles: z.array(
    z.object({
      key: z.string(),
      title: z.string(),
      summary: z.string(),
      url: z.string(),
      access: z.enum(["user", "admin"]),
      routes: z.array(z.string()),
    }),
  ),
});

export type HelpStep = z.infer<typeof HelpStepSchema>;
export type HelpArticle = z.infer<typeof HelpArticleSchema>;
export type HelpMap = z.infer<typeof HelpMapSchema>;

export class HelpRequestError extends Error {
  readonly status: number;
  constructor(status: number, path: string) {
    super(`${path} responded ${status}`);
    this.name = "HelpRequestError";
    this.status = status;
  }
}

// Обычный fetch, не axios-клиент API: 404 статичного файла не должен запускать его перехватчики.
// `same-origin`: администратор получает свою сборку только с cookie сессии.
const fetchJson = async (path: string, signal?: AbortSignal) => {
  const response = await fetch(path, {
    signal: signal ?? null,
    credentials: "same-origin",
    headers: { accept: "application/json" },
  });
  if (!response.ok) throw new HelpRequestError(response.status, path);
  return (await response.json()) as unknown;
};

export const helpApi = {
  getMap: async (lang: Lang, signal?: AbortSignal): Promise<HelpMap> =>
    HelpMapSchema.parse(
      await fetchJson(`${HELP_BASE}/${lang}/help-map.json`, signal),
    ),
  getArticle: async (
    lang: Lang,
    key: string,
    signal?: AbortSignal,
  ): Promise<HelpArticle> =>
    HelpArticleSchema.parse(
      await fetchJson(`${HELP_BASE}/${lang}/help/${key}.json`, signal),
    ),
  siteUrl: (lang: Lang) => `${HELP_BASE}/${lang}/`,
};
