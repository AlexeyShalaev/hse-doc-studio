import {docsLoader} from '@astrojs/starlight/loaders'
import {docsSchema} from '@astrojs/starlight/schema'
import {defineCollection} from 'astro:content'
import {z} from 'astro/zod'

/**
 * Шаг рантбука. Шаги живут во frontmatter, а не в теле: те же шаги уходят приложению JSON-ом
 * (`/help/<lang>/help/<ключ>.json`) и рисуются в панели справки. Один источник, два получателя.
 *
 * В `text`/`hint` работает только **жирный**, *курсив* и [ссылки](...): ровно это понимает
 * панель справки в приложении.
 */
const helpStep = z.object({
  text: z.string(),
  hint: z.string().optional(),
  /**
   * Скриншот шага: путь в public/media без суффикса варианта, например `runbooks/create-project/step-01`.
   * Файлы `<shot>.<ru|en>.<light|dark>.webp` снимает tools/docs-studio, руками их не кладут.
   */
  shot: z.string().optional(),
})

const helpVideo = z.object({
  /** База ролика в public/media: `<src>.<lang>.<theme>.{webm,mp4}` и постер `<src>.<lang>.<theme>.webp`. */
  src: z.string(),
  /** Секунда начала каждого шага, проставляет рекордер. */
  chapters: z.array(z.number()).optional(),
})

const help = z.object({
  /**
   * Экраны, на которых приложение предлагает статью: шаблоны путей react-router
   * (`/projects/:projectId/submit`), можно с параметром вкладки (`...?tab=checks`).
   * Приложение не знает ключей статей, оно читает help-map.json.
   */
  routes: z.array(z.string()).default([]),
  summary: z.string(),
  steps: z.array(helpStep).min(1),
  video: helpVideo.optional(),
})

const verified = z.object({
  at: z.coerce.date(),
  app_version: z.string(),
  /** Пути репозитория, изменение которых делает статью подозрительной. */
  sources: z.array(z.string()).min(1),
})

/**
 * Кто читает статью. Сайт собирается по разу на аудиторию, и статья `admin` физически
 * попадает только в сборку администратора. Обязательное поле: забытое значение по умолчанию
 * было бы «всем», а это ровно та ошибка, которая утекает.
 */
const access = z.enum(['user', 'admin'])

export const collections = {
  docs: defineCollection({
    loader: docsLoader(),
    schema: docsSchema({
      extend: z.object({
        access,
        help: help.optional(),
        verified: verified.optional(),
      }),
    }),
  }),
}
