import type {APIRoute, GetStaticPaths} from 'astro'

import {LANGS, articleKey, getHelpArticles, serializeArticle} from '../../../lib/help'

/**
 * `GET /help/<lang>/help/<ключ>.json`: статья данными для панели справки в приложении.
 * Данные, а не HTML: панель рисует строки своими компонентами и в своей теме.
 */
export const getStaticPaths: GetStaticPaths = async () => {
  const paths = []
  for (const lang of LANGS) {
    for (const entry of await getHelpArticles(lang)) {
      paths.push({params: {lang, key: articleKey(entry.id)}, props: {article: serializeArticle(entry)}})
    }
  }
  return paths
}

export const GET: APIRoute = ({props}) =>
  new Response(JSON.stringify(props.article), {headers: {'content-type': 'application/json; charset=utf-8'}})
