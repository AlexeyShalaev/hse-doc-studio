import {getCollection, type CollectionEntry} from 'astro:content'

/**
 * Общая сборка данных справки для приложения: help-map.json и /help/<ключ>.json.
 * Приложению отдаются абсолютные URL (`/help/media/...`): панель рисуется внутри SPA, и
 * относительный путь разрешился бы от текущего экрана.
 */
export const LANGS = ['ru', 'en'] as const
export type Lang = (typeof LANGS)[number]
export const THEMES = ['light', 'dark'] as const

export const BASE = import.meta.env.BASE_URL.replace(/\/$/, '')

export const mediaUrl = (path: string): string => `${BASE}/media/${path}`

/** `ru/runbooks/create-project` → `runbooks/create-project`: ключ один на оба языка. */
export const articleKey = (id: string): string => id.replace(/^(ru|en)\//, '')
export const articleLang = (id: string): Lang => (id.startsWith('en/') ? 'en' : 'ru')
export const articleUrl = (id: string): string => `${BASE}/${id}/`

/** Варианты кадра под тему: в приложении тема своя, язык — язык статьи. */
export const shotVariants = (shot: string, lang: Lang) => ({
  light: mediaUrl(`${shot}.${lang}.light.webp`),
  dark: mediaUrl(`${shot}.${lang}.dark.webp`),
})

export const videoVariants = (src: string, lang: Lang) =>
  Object.fromEntries(
    THEMES.map((theme) => [
      theme,
      {
        webm: mediaUrl(`${src}.${lang}.${theme}.webm`),
        mp4: mediaUrl(`${src}.${lang}.${theme}.mp4`),
        poster: mediaUrl(`${src}.${lang}.${theme}.webp`),
      },
    ]),
  ) as Record<(typeof THEMES)[number], {webm: string; mp4: string; poster: string}>

export type HelpArticleEntry = CollectionEntry<'docs'> & {
  data: {help: NonNullable<CollectionEntry<'docs'>['data']['help']>}
}

/** Статьи языка с блоком help, в стабильном порядке: «первое совпадение» в приложении не плавает. */
export async function getHelpArticles(lang: Lang): Promise<HelpArticleEntry[]> {
  const docs = await getCollection('docs')
  return docs
    .filter((entry): entry is HelpArticleEntry => Boolean(entry.data.help) && articleLang(entry.id) === lang)
    .sort((a, b) => {
      const orderA = a.data.sidebar?.order ?? Number.MAX_SAFE_INTEGER
      const orderB = b.data.sidebar?.order ?? Number.MAX_SAFE_INTEGER
      return orderA - orderB || a.id.localeCompare(b.id)
    })
}

export function serializeArticle(entry: HelpArticleEntry) {
  const {help, verified, access} = entry.data
  const lang = articleLang(entry.id)
  return {
    key: articleKey(entry.id),
    lang,
    title: entry.data.title,
    summary: help.summary,
    url: articleUrl(entry.id),
    access,
    routes: help.routes,
    steps: help.steps.map((step) => ({
      text: step.text,
      hint: step.hint,
      shot: step.shot ? shotVariants(step.shot, lang) : undefined,
    })),
    video: help.video ? {...videoVariants(help.video.src, lang), chapters: help.video.chapters ?? []} : undefined,
    verified: verified ? {at: verified.at.toISOString().slice(0, 10), appVersion: verified.app_version} : undefined,
  }
}
