// Стенды съёмки и их «мир»: адрес, персоны, засеянные проекты. Сид идёт настоящими запросами API,
// как у пользователя, и идемпотентен: существующие проекты находятся по имени.
import {readFileSync, existsSync} from 'node:fs'
import {homedir} from 'node:os'
import {join, resolve} from 'node:path'

const ROOT = resolve(import.meta.dirname, '../../../..')

export const LOCAL_BASE = process.env.DOCS_LOCAL_URL ?? `http://127.0.0.1:${process.env.DOCS_LOCAL_PORT ?? 17790}`
export const SERVER_BASE = process.env.DOCS_SERVER_URL ?? `http://localhost:${process.env.DOCS_SERVER_PORT ?? 8110}`
const PROJECTS_HOME = process.env.DOCS_PROJECTS_HOME ?? join(homedir(), 'Documents', 'hse-studio-docs')

/** Демо-проекты: русская и английская ВКР, синтетические люди. */
const LOCAL_PROJECTS = {
  ru: {
    name: 'Анализ задержек CI/CD-конвейеров',
    folder: 'vkr-ci',
    lang: 'ru',
    authors: [{name: 'Смирнова Анна Сергеевна', group: 'БПИ221'}],
    supervisor: {name: 'Петров Пётр Петрович', title: 'к.т.н., доцент ФКН', role: 'university'},
  },
  en: {
    name: 'Latency analysis of CI/CD pipelines',
    folder: 'vkr-ci-en',
    lang: 'en',
    authors: [{name: 'Anna Smirnova', group: 'BSE221'}],
    supervisor: {name: 'Peter Petrov', title: 'PhD, Associate Professor', role: 'university'},
  },
}

const json = async (response, what) => {
  if (!response.ok) throw new Error(`${what}: HTTP ${response.status} ${(await response.text()).slice(0, 200)}`)
  return response.json()
}

export async function waitFor(base) {
  for (let i = 0; i < 60; i++) {
    try {
      if ((await fetch(`${base}/health`)).ok) return
    } catch {}
    await new Promise((r) => setTimeout(r, 1000))
  }
  throw new Error(`стенд ${base} не отвечает: make docs-stand-local / docs-stand-server`)
}

export async function seedLocal() {
  await waitFor(LOCAL_BASE)
  const listed = await json(await fetch(`${LOCAL_BASE}/api/v1/projects?limit=200`), 'список проектов')
  const cards = Array.isArray(listed) ? listed : listed.items
  const projects = {}
  for (const [lang, p] of Object.entries(LOCAL_PROJECTS)) {
    let card = cards.find((c) => c.name === p.name)
    if (!card) {
      card = await json(
        await fetch(`${LOCAL_BASE}/api/v1/projects`, {
          method: 'POST',
          headers: {'content-type': 'application/json'},
          body: JSON.stringify({
            name: p.name,
            folder: join(PROJECTS_HOME, p.folder),
            pack_id: 'hse-cs-se',
            template_id: 'vkr',
            version: '2026.1',
            kind: 'project',
            lang: p.lang,
            authors: p.authors,
            supervisor: p.supervisor,
          }),
        }),
        `создание проекта ${p.name}`,
      )
      console.log(`  засеян проект ${p.name}`)
    }
    projects[lang] = {id: card.id, name: p.name, doc: 'thesis'}
    await ensureCompiled(card.id, 'thesis')
  }
  return {projects}
}

/** Превью в кадре — настоящий PDF: собираем тезис один раз (TeX Live в Docker на машине). */
async function ensureCompiled(projectId, doc) {
  const url = `${LOCAL_BASE}/api/v1/projects/${projectId}/documents/${doc}`
  const latest = async () => {
    const response = await fetch(`${url}/compiles`)
    if (!response.ok) return null
    const list = await response.json()
    const items = Array.isArray(list) ? list : list.items ?? []
    // Список идёт от старых к новым: берём самую свежую по времени начала.
    return items.reduce((a, b) => (!a || (b.started_at ?? '') > (a.started_at ?? '') ? b : a), null)
  }
  const done = (record) => record && !['running', 'pending', 'queued'].includes(record.status)
  // Первая сборка на свежем образе TeX Live строит кэш шрифтов; упавшая сборка пересобирается.
  const before = await latest()
  if (before?.status === 'success') return
  console.log(`  собираю ${doc} (${projectId}), первый раз это несколько минут`)
  const started = await fetch(`${url}/compile`, {method: 'POST'})
  if (!started.ok) {
    // Нет образа TeX Live или Docker: кадры снимутся без PDF, но дубль не встанет.
    console.warn(`  сборка не запустилась: HTTP ${started.status} ${(await started.text()).slice(0, 160)}`)
    return
  }
  for (let i = 0; i < 600; i++) {
    await new Promise((r) => setTimeout(r, 2000))
    const record = await latest()
    if (record && record.id !== before?.id && done(record)) {
      if (record.status !== 'success') console.warn(`  сборка ${doc}: ${record.status}, кадры будут без PDF`)
      return
    }
  }
  throw new Error(`сборка ${doc} не закончилась за 20 минут`)
}

export function serverPersonas() {
  const envFile = join(ROOT, 'tools/docs-studio/.build/server.env')
  if (!existsSync(envFile)) throw new Error('нет tools/docs-studio/.build/server.env: сначала make docs-stand-server')
  const env = Object.fromEntries(
    readFileSync(envFile, 'utf-8')
      .split('\n')
      .filter((l) => l.includes('='))
      .map((l) => [l.slice(0, l.indexOf('=')), l.slice(l.indexOf('=') + 1)]),
  )
  return {
    admin: {email: env.SERVER_LITE_ADMIN_EMAIL ?? 'admin@example.org', password: env.SERVER_LITE_ADMIN_PASSWORD},
    anna: {email: 'anna@example.org', password: env.SERVER_LITE_SEED_PASSWORD},
    victor: {email: 'victor@example.org', password: env.SERVER_LITE_SEED_PASSWORD},
  }
}

/** Вход персоны в контекст браузера: cookie сессии ложится в контекст, как после формы входа. */
export async function signIn(context, persona) {
  const response = await context.request.post(`${SERVER_BASE}/api/v1/auth/login`, {
    data: {email: persona.email, password: persona.password},
    headers: {Origin: SERVER_BASE},
  })
  if (!response.ok()) throw new Error(`вход ${persona.email}: HTTP ${response.status()}`)
  return response.json()
}
