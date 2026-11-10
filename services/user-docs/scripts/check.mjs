// Проверка справки против репозитория (та же, что в CI):
//  - у каждой статьи есть пара ru/en с тем же числом шагов, теми же кадрами и роликом;
//  - help.routes существуют в маршрутах приложения (router.tsx и разделы админки);
//  - verified.sources существуют;
//  - значки «?» приложения (<HelpAnchor article="…" step={N} />) ведут на статью с help и таким шагом;
//  - медиа на месте (строго при CHECK_MEDIA=1, иначе только сводка: съёмка — отдельная ручная джоба).
import {existsSync, readFileSync, readdirSync, statSync} from 'node:fs'
import {dirname, join, relative, resolve} from 'node:path'
import {fileURLToPath} from 'node:url'
import {parse} from 'yaml'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const REPO = resolve(ROOT, '../..')
const DOCS = join(ROOT, 'src/content/docs')
const MEDIA = join(ROOT, 'public/media')
const STRICT_MEDIA = process.env.CHECK_MEDIA === '1'

const errors = []
const missingMedia = []
const fail = (msg) => errors.push(msg)

const walk = (dir) =>
  readdirSync(dir).flatMap((e) => {
    const p = join(dir, e)
    return statSync(p).isDirectory() ? walk(p) : [p]
  })

const frontmatter = (file) => parse(readFileSync(file, 'utf-8').split(/^---$/m)[1] ?? '') ?? {}

/** Шаблоны путей приложения: router.tsx плюс /admin/<раздел>. */
const appPatterns = (() => {
  const router = readFileSync(join(REPO, 'services/web-app/src/app/router.tsx'), 'utf-8')
  // Пути-константы (path: LOCAL_STUDIO_PATH) раскрываются по их объявлению в исходниках приложения.
  const constants = new Map()
  for (const file of walk(join(REPO, 'services/web-app/src')).filter((f) => /\.tsx?$/.test(f))) {
    for (const m of readFileSync(file, 'utf-8').matchAll(/export const ([A-Z_]+_PATH)\s*=\s*"([^"]+)"/g)) constants.set(m[1], m[2])
  }
  const literal = [...router.matchAll(/path:\s*"([^"]+)"/g)].map((m) => m[1])
  const named = [...router.matchAll(/path:\s*([A-Z_]+_PATH)\b/g)].map((m) => constants.get(m[1])).filter(Boolean)
  const patterns = [...literal, ...named].filter((p) => p.startsWith('/') && !p.includes('*'))
  const admin = readFileSync(join(REPO, 'services/web-app/src/pages/AdminPage/AdminApp.tsx'), 'utf-8')
  const parts = new Set([...admin.matchAll(/["']([a-z][a-z-]+)["']/g)].map((m) => m[1]))
  return {patterns, adminParts: parts}
})()

const toRegex = (pattern) => new RegExp('^' + pattern.replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/\\?:[A-Za-z]+/g, '[^/]+') + '/?$')
const knownRoute = (route) => {
  const path = route.split('?')[0]
  if (path === '/admin') return true
  const admin = /^\/admin\/([a-z-]+)$/.exec(path)
  if (admin) return appPatterns.adminParts.has(admin[1])
  // Совпадение с шаблоном роутера: точный шаблон или конкретный путь под ним (/settings/providers).
  return appPatterns.patterns.some((p) => p === path || toRegex(p).test(path))
}

const variants = (base) => ['ru', 'en'].flatMap((lang) => ['light', 'dark'].map((theme) => `${base}.${lang}.${theme}`))

const articles = {ru: new Map(), en: new Map()}
for (const lang of ['ru', 'en']) {
  for (const file of walk(join(DOCS, lang))) {
    if (!/\.mdx?$/.test(file)) continue
    articles[lang].set(relative(join(DOCS, lang), file).replace(/\.mdx?$/, ''), {file, fm: frontmatter(file)})
  }
}

for (const [key, {file, fm}] of articles.ru) {
  const en = articles.en.get(key)
  const where = relative(REPO, file)
  if (!en) fail(`${where}: нет английской пары en/${key}`)
  if (!['user', 'admin'].includes(fm.access)) fail(`${where}: access должен быть user или admin`)
  if (en && en.fm.access !== fm.access) fail(`${where}: access ru/en различается`)
  if (key.startsWith('admin/') && fm.access !== 'admin') fail(`${where}: статья в admin/ должна быть access: admin`)
  if (!fm.help) continue
  const steps = fm.help.steps ?? []
  if (en) {
    const enSteps = en.fm.help?.steps ?? []
    if (enSteps.length !== steps.length) fail(`${where}: шагов ru ${steps.length}, en ${enSteps.length}`)
    steps.forEach((s, i) => {
      if ((s.shot ?? null) !== (enSteps[i]?.shot ?? null)) fail(`${where}: кадр шага ${i + 1} ru/en различается`)
    })
    if ((fm.help.video?.src ?? null) !== (en.fm.help?.video?.src ?? null)) fail(`${where}: ролик ru/en различается`)
    if (JSON.stringify(fm.help.routes ?? []) !== JSON.stringify(en.fm.help?.routes ?? [])) fail(`${where}: routes ru/en различаются`)
  }
  for (const route of fm.help.routes ?? []) if (!knownRoute(route)) fail(`${where}: маршрута ${route} нет в приложении`)
  if (!fm.verified) fail(`${where}: нет verified (дата сверки и sources)`)
  for (const source of fm.verified?.sources ?? []) if (!existsSync(join(REPO, source))) fail(`${where}: verified.sources ${source} не существует`)
  steps.forEach((s, i) => {
    if (!s.shot) return
    if (!s.shot.startsWith(`${key}/`)) fail(`${where}: кадр шага ${i + 1} должен лежать под ${key}/`)
    for (const v of variants(s.shot)) if (!existsSync(join(MEDIA, `${v}.webp`))) missingMedia.push(`${v}.webp`)
  })
  if (fm.help.video) {
    for (const v of variants(fm.help.video.src)) for (const ext of ['mp4', 'webp']) if (!existsSync(join(MEDIA, `${v}.${ext}`))) missingMedia.push(`${v}.${ext}`)
  }
}
for (const key of articles.en.keys()) if (!articles.ru.has(key)) fail(`en/${key}: нет русской пары`)

// Значок «?» у поля знает ключ статьи и номер шага: статья с help.steps должна существовать.
for (const file of walk(join(REPO, 'services/web-app/src')).filter((f) => /\.tsx$/.test(f) && !/\.test\.tsx$/.test(f))) {
  for (const m of readFileSync(file, 'utf-8').matchAll(/<HelpAnchor\s+article="([^"]+)"(?:\s+step=\{(\d+)\})?/g)) {
    const where = relative(REPO, file)
    const article = articles.ru.get(m[1])
    if (!article?.fm.help) fail(`${where}: значок «?» ведёт на статью ${m[1]} без help`)
    else if (m[2] && Number(m[2]) > (article.fm.help.steps ?? []).length) fail(`${where}: в статье ${m[1]} нет шага ${m[2]}`)
  }
}

if (missingMedia.length) {
  const msg = `медиа не снято: ${missingMedia.length} файл(ов), например ${missingMedia.slice(0, 3).join(', ')} (make docs-media)`
  if (STRICT_MEDIA) fail(msg)
  else console.warn(`ВНИМАНИЕ: ${msg}`)
}
if (errors.length) {
  for (const e of errors) console.error(`ОШИБКА: ${e}`)
  process.exit(1)
}
console.log(`справка в порядке: статей ${articles.ru.size} (ru) + ${articles.en.size} (en)`)
