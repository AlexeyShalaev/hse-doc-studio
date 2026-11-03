import type {APIRoute, GetStaticPaths} from 'astro'

import {LANGS, articleKey, articleUrl, getHelpArticles, type Lang} from '../../lib/help'

/**
 * `GET /help/<lang>/help-map.json`: какая статья у какого экрана приложения.
 * Приложение ключей статей не знает: добавить справку экрану можно, не трогая фронтенд.
 * У экрана может быть несколько статей; первая открывается кнопкой справки.
 */
export const getStaticPaths: GetStaticPaths = () => LANGS.map((lang) => ({params: {lang}}))

export const GET: APIRoute = async ({params}) => {
  const articles = await getHelpArticles(params.lang as Lang)
  const routes: Record<string, string[]> = {}
  for (const entry of articles) {
    for (const route of entry.data.help.routes) (routes[route] ??= []).push(articleKey(entry.id))
  }
  const body = {
    routes,
    articles: articles.map((entry) => ({
      key: articleKey(entry.id),
      title: entry.data.title,
      summary: entry.data.help.summary,
      url: articleUrl(entry.id),
      access: entry.data.access,
      routes: entry.data.help.routes,
    })),
  }
  return new Response(JSON.stringify(body), {headers: {'content-type': 'application/json; charset=utf-8'}})
}
