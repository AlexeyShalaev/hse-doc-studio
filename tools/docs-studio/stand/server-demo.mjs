// Серверное демо для съёмки: экраны, которых нет на стендах без живых людей и раннеров.
// Сейчас это маршрут подписания: редактор маршрута, карточка «Подписание» точки, страница
// подписанта и «Входящие → На подпись».
//
// Интерфейс собирается с VITE_SERVER_DEMO=1: ответы API даёт память вкладки (app/demo/server
// в services/web-app), поэтому стенду не нужны ни бэкенд, ни Docker, ни TeX Live. Сборка
// раздаётся статикой на своём порту. Чего в демо нет, отвечает заглушка в контексте браузера:
// PDF документа (одна страница A4, строки подписей там же, где слоты демо), остальные GET
// получают 404 (интерфейс молчит о GET 4xx), прочие запросы 204.
//
// Кадры воспроизводимы: часы браузера пущены с одной и той же минуты (сроки «через 2 дня»,
// даты событий), часовой пояс московский, сценарий демо выбран явно.
//
// Пользуются им tools/docs-studio/record (стенд 'demo') и tools/demo/screenshots/signing.mjs.
import {spawnSync} from 'node:child_process'
import {existsSync, readFileSync, statSync} from 'node:fs'
import {createServer} from 'node:http'
import {extname, join, normalize, resolve} from 'node:path'

const ROOT = resolve(import.meta.dirname, '../../..')
const WEB_APP = join(ROOT, 'services/web-app')
export const SERVER_DEMO_DIR = join(ROOT, 'tools/docs-studio/.build/server-demo')
const WEB = join(SERVER_DEMO_DIR, 'web')

/** Минута, с которой идут часы в кадре. */
export const DEMO_NOW = new Date('2026-11-10T10:00:00+03:00')
export const DEMO_TIMEZONE = 'Europe/Moscow'
/** Сценарий серверного демо: студент, на сервере есть почта. */
export const DEMO_SCENARIO = 'student_ready'

/** Проекты демо (app/demo/server/projects.ts) и то, что напечатано в их заявлении. */
export const DEMO_PROJECTS = {
  own: 'p_01hxa1c4de',
  signRu: 'p_01hxa3k2jm',
  signEn: 'p_01hxa2f8gh',
}
export const DEMO_PROFILE = 'topic-approval'

const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.webp': 'image/webp',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.ttf': 'font/ttf',
  '.ico': 'image/x-icon',
  '.wasm': 'application/wasm',
  '.map': 'application/json',
  '.txt': 'text/plain; charset=utf-8',
}

/** Сборка демо-интерфейса: всегда при SERVER_DEMO_BUILD=1, иначе только если её нет. */
export function buildServerDemo({force = process.env.SERVER_DEMO_BUILD === '1'} = {}) {
  if (!force && existsSync(join(WEB, 'index.html'))) return
  console.log('→ собираю интерфейс серверного демо (VITE_SERVER_DEMO=1)')
  const env = {...process.env, VITE_SERVER_DEMO: '1', NODE_ENV: 'production'}
  delete env.VITE_API_BASE_URL
  if (!existsSync(join(WEB_APP, 'node_modules'))) {
    const install = spawnSync('pnpm', ['install', '--frozen-lockfile'], {cwd: WEB_APP, stdio: 'inherit', env: {...env, NODE_ENV: 'development'}})
    if (install.status !== 0) throw new Error('pnpm install в services/web-app не прошёл')
  }
  const build = spawnSync('pnpm', ['exec', 'vite', 'build', '--outDir', WEB, '--emptyOutDir'], {cwd: WEB_APP, stdio: ['ignore', 'ignore', 'inherit'], env})
  if (build.status !== 0) throw new Error('сборка серверного демо не прошла')
}

/** Статика сборки с возвратом index.html на адреса приложения. Порт 0: любой свободный. */
export async function startServerDemo({port = Number(process.env.DOCS_DEMO_PORT ?? 0)} = {}) {
  buildServerDemo()
  const server = createServer((req, res) => {
    const path = decodeURIComponent(new URL(req.url ?? '/', 'http://x').pathname)
    if (path.startsWith('/api/')) {
      // Сюда доходит только то, что не перехватил контекст браузера (prepareServerDemoContext).
      res.writeHead(404, {'content-type': 'application/json'}).end('{"detail":"not in demo"}')
      return
    }
    const file = normalize(join(WEB, path))
    const inside = file.startsWith(WEB) && existsSync(file) && statSync(file).isFile()
    const target = inside ? file : join(WEB, 'index.html')
    res.writeHead(200, {'content-type': TYPES[extname(target)] ?? 'application/octet-stream', 'cache-control': 'no-store'})
    res.end(readFileSync(target))
  })
  await new Promise((done) => server.listen(port, '127.0.0.1', done))
  const base = `http://127.0.0.1:${server.address().port}`
  return {base, close: () => new Promise((done) => server.close(done))}
}

/** Параметры контекста браузера: часовой пояс один на все кадры. */
export const serverDemoContextOptions = () => ({timezoneId: DEMO_TIMEZONE})

/**
 * Готовит контекст до первой загрузки: сценарий демо, часы, заглушки адресов без мока.
 * `lang` нужен PDF: заявление напечатано на языке кадра.
 */
export async function prepareServerDemoContext(context, {lang, scenario = DEMO_SCENARIO}) {
  await context.addInitScript((scenarioId) => {
    try {
      localStorage.setItem('hse-studio.serverDemoScenario', JSON.stringify({state: {scenarioId}, version: 0}))
    } catch {}
  }, scenario)
  // Переключатель сценариев демо в кадр не попадает.
  await context.addInitScript(() => {
    const hide = () => {
      const style = document.createElement('style')
      style.textContent = '[data-testid="server-demo-picker"]{display:none!important}'
      document.head.appendChild(style)
    }
    if (document.head) hide()
    else document.addEventListener('DOMContentLoaded', hide)
  })
  await context.clock.install({time: DEMO_NOW})
  let signature = null
  const pdfs = new Map()
  const pdfOf = async (projectId) => {
    const key = `${lang}:${projectId}`
    if (!pdfs.has(key)) pdfs.set(key, await renderApplicationPdf(context.browser(), lang, projectId))
    return pdfs.get(key)
  }
  await context.route(/\/api\/v1\//, async (route) => {
    const request = route.request()
    const url = new URL(request.url())
    if (process.env.SERVER_DEMO_TRACE === '1') console.log(`  заглушка ${request.method()} ${url.pathname}`)
    const pdf = /\/api\/v1\/projects\/([^/]+)\/(?:files\/.+\.pdf|docs\/[^/]+\/(?:pdf|frozen)\b.*)$/.exec(url.pathname)
    if (pdf && request.method() === 'GET') {
      return route.fulfill({status: 200, contentType: 'application/pdf', body: await pdfOf(pdf[1])})
    }
    if (request.method() === 'GET' && /\/files\/.+\.png$/.test(url.pathname)) {
      signature ??= await renderSignaturePng(context.browser())
      return route.fulfill({status: 200, contentType: 'image/png', body: signature})
    }
    if (request.method() === 'GET' && url.pathname.endsWith('/system/archive-formats')) {
      return route.fulfill({status: 200, contentType: 'application/json', body: JSON.stringify({formats: ARCHIVE_FORMATS})})
    }
    if (request.method() === 'GET') {
      return route.fulfill({status: 404, contentType: 'application/json', body: '{"detail":"not in demo"}'})
    }
    return route.fulfill({status: 204, body: ''})
  })
}

const ARCHIVE_FORMATS = [
  {id: 'zip', label: 'ZIP', ext: '.zip', available: true},
  {id: 'targz', label: 'tar.gz', ext: '.tar.gz', available: true},
]

/** Картинка подписи автора (PNG с прозрачным фоном): росчерк пером, 600x240 как в демо. */
async function renderSignaturePng(browser) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="600" height="240" viewBox="0 0 600 240">
    <path d="M40 170 C70 60 110 50 120 120 S150 200 180 120 S230 40 250 130 S300 190 330 110 C350 70 380 80 370 140
      C365 175 400 170 430 120 S500 80 560 100" fill="none" stroke="#1d3fa3" stroke-width="7" stroke-linecap="round" stroke-linejoin="round"/>
    <path d="M150 190 C260 175 400 168 540 160" fill="none" stroke="#1d3fa3" stroke-width="5" stroke-linecap="round"/></svg>`
  const context = await browser.newContext({viewport: {width: 600, height: 240}})
  try {
    const page = await context.newPage()
    await page.setContent(`<body style="margin:0;background:transparent">${svg}</body>`)
    return await page.locator('svg').screenshot({omitBackground: true})
  } finally {
    await context.close()
  }
}

/** Что напечатано в заявлении проекта: тема и автор. */
const APPLICATIONS = {
  [DEMO_PROJECTS.own]: {
    ru: {topic: 'Bertie: ассистент, который пишет письма в организации', student: 'Петрова Анна Сергеевна', group: 'БПИ231'},
    en: {topic: 'Bertie: an assistant that writes to organisations', student: 'Anna Petrova', group: 'BSE231'},
  },
  [DEMO_PROJECTS.signRu]: {
    ru: {topic: 'Анализ нагрузки на очередь задач', student: 'Орлов Павел Андреевич', group: 'БПИ222'},
    en: {topic: 'Load analysis of a task queue', student: 'Pavel Orlov', group: 'BSE222'},
  },
  [DEMO_PROJECTS.signEn]: {
    ru: {topic: 'Внедрение CI в индустрии', student: 'Сидоров Иван Олегович', group: 'БПИ222'},
    en: {topic: 'Industry adoption of CI', student: 'Ivan Sidorov', group: 'BSE222'},
  },
}

const TEXT = {
  ru: {
    to: ['Академическому руководителю', 'образовательной программы', '«Программная инженерия»'],
    from: (a) => `от студента группы ${a.group}`,
    title: 'Заявление',
    body: (a) => `Прошу утвердить тему курсового проекта «${a.topic}» и назначить научным руководителем Петрова Петра Петровича, к.т.н., доцента департамента программной инженерии.`,
    supervisor: ['Научный руководитель', 'Петров П. П.'],
    academic: ['Согласовано:', 'академический руководитель ОП'],
    student: (a) => ['Студент', a.student],
    sign: 'подпись',
    date: '«___» ____________ 2026 г.',
  },
  en: {
    to: ['To the academic supervisor', 'of the Software Engineering', 'programme'],
    from: (a) => `from student of group ${a.group}`,
    title: 'Application',
    body: (a) => `I ask to approve the course project topic “${a.topic}” and to appoint Peter Petrov, PhD, Associate Professor of the School of Software Engineering, as my supervisor.`,
    supervisor: ['Supervisor', 'Peter Petrov'],
    academic: ['Approved by:', 'academic supervisor'],
    student: (a) => ['Student', a.student],
    sign: 'signature',
    date: '“___” ____________ 2026',
  },
}

/**
 * Заявление одной страницей A4. Строки подписей стоят под слотами демо
 * (научрук 110x130 мм, академрук 110x160 мм, студент 120x230 мм, ширина 40 мм):
 * рамки «Где подписи» и страницы подписанта ложатся на свои места.
 */
async function renderApplicationPdf(browser, lang, projectId) {
  const a = (APPLICATIONS[projectId] ?? APPLICATIONS[DEMO_PROJECTS.own])[lang]
  const t = TEXT[lang]
  const at = (x, y, html, extra = '') => `<div style="position:absolute;left:${x}mm;top:${y}mm;${extra}">${html}</div>`
  const signLine = (x, y) =>
    at(x, y + 15, '', 'width:40mm;border-top:0.3mm solid #222') + at(x, y + 16, t.sign, 'width:40mm;text-align:center;font-size:8pt;color:#555')
  const left = (y, [first, second]) => at(25, y + 6, `${first}<br>${second}`, 'width:80mm;line-height:1.35')
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
    @page{size:A4;margin:0} html,body{margin:0}
    body{width:210mm;height:297mm;position:relative;font-family:'Times New Roman',Times,serif;font-size:12.5pt;color:#111}
  </style></head><body>
    ${at(110, 22, `${t.to.join('<br>')}<br>${t.from(a)}<br>${a.student}`, 'width:80mm;line-height:1.4')}
    ${at(0, 72, t.title, 'width:210mm;text-align:center;font-weight:bold;letter-spacing:0.08em;text-transform:uppercase')}
    ${at(25, 84, t.body(a), 'width:160mm;text-indent:12.5mm;text-align:justify;line-height:1.5')}
    ${left(130, t.supervisor)}${signLine(110, 130)}
    ${left(160, t.academic)}${signLine(110, 160)}
    ${left(230, t.student(a))}${signLine(120, 230)}
    ${at(25, 262, t.date)}
  </body></html>`
  const context = await browser.newContext()
  try {
    const page = await context.newPage()
    await page.setContent(html, {waitUntil: 'load'})
    return await page.pdf({width: '210mm', height: '297mm', printBackground: true})
  } finally {
    await context.close()
  }
}
