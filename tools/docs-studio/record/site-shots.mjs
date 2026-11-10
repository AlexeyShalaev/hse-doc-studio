// Кадры маршрута подписания для сайта документации (docs/{ru,en}/workbench/send-for-signing.md
// и how-to-sign.md). Тот же стенд серверного демо, что у справки (stand/server-demo.mjs), та же
// матрица, что у `make shots`: ru/en × light/dark, окно 1440×900 @2x.
//
//   node site-shots.mjs                          # все кадры
//   ONLY=signing-route,signing-card LANGS=ru THEMES=light node site-shots.mjs
//
// Выход: docs/ru/assets/shots/<кадр>.<lang>.<theme>.webp (WebP 1600 px, q80, как кадры справки;
// sync_shared.py копирует ассеты в docs/en). Каждый кадр снимается в новой вкладке с нуля.
import {chromium} from 'playwright'
import {join, resolve} from 'node:path'

import {saveShot} from './lib/media.mjs'
import {assertNoPersonalData} from './lib/privacy.mjs'
import {

  CHECKPOINT,
  INBOX_SIGNING,
  ROUTE_EDITOR,
  SIGNER_TASK,
  authorMessage,
  card,
  drawSignature,
  editor,
  placeSupervisor,
  returnComment,
  s,
  scrollToTop,
  sendRoute,
  signer,

} from './lib/signing.mjs'
import {prepareServerDemoContext, serverDemoContextOptions, startServerDemo} from '../stand/server-demo.mjs'

const ROOT = resolve(import.meta.dirname, '../../..')
const OUT = process.env.OUT ?? join(ROOT, 'docs/ru/assets/shots')
const LANGS = (process.env.LANGS ?? 'ru,en').split(',')
const THEMES = (process.env.THEMES ?? 'light,dark').split(',')
const ONLY = process.env.ONLY ? new Set(process.env.ONLY.split(',')) : null
const DESKTOP = {width: 1440, height: 900}
const PHONE = {width: 390, height: 844}

// [кадр, начальный адрес, подготовка(page, lang), окно, сценарий демо (по умолчанию student_ready)]
const SCREENS = [
  // Автор: экран маршрута сразу после открытия. Порядок по умолчанию и помеха «подпись не размещена».
  ['signing-route', ROUTE_EDITOR, null],
  // «Где подписи»: подпись научрука поставлена на страницу, рамки на PDF, «Всё готово к отправке».
  [
    'signing-placement',
    ROUTE_EDITOR,
    async (page, lang) => {
      await placeSupervisor(page, lang)
      await scrollToTop(editor.placements(page, lang), page, 16)
      await scrollPdf(page, 430)
    },
  ],
  // Карточка «Подписание» на странице точки: маршрут идёт, очередь научрука.
  [
    'signing-card',
    ROUTE_EDITOR,
    async (page, lang) => {
      await placeSupervisor(page, lang)
      await editor.message(page).fill(authorMessage(lang))
      await sendRoute(page, lang)
      await dismissToasts(page)
    },
  ],
  // «Скопировать ссылку»: адрес страницы подписи для человека, которому идёт очередь (уведомление «Ссылка скопирована»).
  [
    'signing-link',
    ROUTE_EDITOR,
    async (page, lang) => {
      await placeSupervisor(page, lang)
      await sendRoute(page, lang)
      await dismissToasts(page)
      await card.copyLink(page, lang).click()
      await page.waitForTimeout(900)
    },
  ],
  // Подписант: «Входящие → На подпись» и строка колокольчика «Ждут вашей подписи».
  [
    'signing-inbox',
    INBOX_SIGNING,
    async (page) => {
      await page.getByTestId('inbox-bell').click()
      await page.waitForTimeout(700)
    },
  ],
  // Страница подписи: шапка с сообщением автора, ход подписания, что нужно, PDF, «Как подписать».
  ['signing-page', SIGNER_TASK, null],
  // «Как подписать»: картинка, нарисованная на странице.
  [
    'signing-image',
    SIGNER_TASK,
    async (page, lang) => {
      await signer.method(page, 'image').click()
      await signer.draw(page, lang).click()
      await scrollToTop(signer.howTo(page, lang), page, 24)
      await drawSignature(page)
    },
  ],
  // «Как подписать»: открепленная ЭП, «Чем подписать» и «Согласовать и подписать».
  [
    'signing-esign',
    SIGNER_TASK,
    async (page, lang) => {
      await signer.method(page, 'detached').click()
      await signer.toPlace(page, lang).click()
      await page.waitForTimeout(900)
    },
  ],
  // После «Согласовать»: картинка встала на место, страница пишет, что дальше.
  [
    'signing-approved',
    SIGNER_TASK,
    async (page, lang) => {
      await signer.method(page, 'image').click()
      await signer.draw(page, lang).click()
      await drawSignature(page)
      await signer.drawDone(page, lang).click()
      await page.waitForTimeout(600)
      await signer.approve(page, lang).click()
      await page.waitForTimeout(1800)
      await dismissToasts(page)
      await page.evaluate(() => document.querySelectorAll('*').forEach((el) => el.scrollTop > 0 && (el.scrollTop = 0)))
      await page.waitForTimeout(500)
    },
  ],
  // «Вернуть на доработку»: окно с комментарием.
  [
    'signing-return',
    SIGNER_TASK,
    async (page, lang) => {
      await signer.returnButton(page, lang).click()
      await page.waitForTimeout(500)
      await signer.returnField(page).fill(returnComment(lang))
      await page.waitForTimeout(400)
    },
  ],
  // Телефон: кнопки прилипают к низу экрана.
  ['signing-phone', SIGNER_TASK, null, PHONE],
  // Версия на подписи, сценарий «Подписание: версии». Автор пересобрал заявление после отправки:
  // карточка пишет «Есть изменения после отправки на подпись» и предлагает «Отправить новую версию».
  ['signing-version-card', CHECKPOINT, null, DESKTOP, 'student_signing_versions'],
  // Подтверждение «Отправить новую версию?»: что изменилось, кто согласует заново, поле «Что изменилось».
  [
    'signing-new-version',
    CHECKPOINT,
    async (page, lang) => {
      await page.getByRole('button', {name: s(lang, 'signingProgress', 'newVersion.action'), exact: true}).first().click()
      await page.waitForTimeout(1200)
    },
    DESKTOP,
    'student_signing_versions',
  ],
  // Подписанту прислали новую версию: «Новая версия: изменился документ …».
  ['signing-version-page', SIGNER_TASK, null, DESKTOP, 'student_signing_versions'],
  // Сценарий «Подписание: перенос 0.20.0»: версию не восстановить, маршрут ждёт новую версию.
  ['signing-migration', CHECKPOINT, null, DESKTOP, 'student_signing_migration'],
]

/** Прокрутить PDF в окне просмотра: рамки подписей ниже текста заявления. */
async function scrollPdf(page, dy) {
  const box = await page.locator('canvas').filter({visible: true}).first().boundingBox()
  if (!box) return
  await page.mouse.move(box.x + box.width / 2, Math.min(box.y + 200, 800))
  await page.mouse.wheel(0, dy)
  await page.waitForTimeout(700)
}

async function dismissToasts(page) {
  await page.waitForTimeout(300)
  await page.evaluate(() => document.querySelectorAll('[aria-live="polite"] > .card[role="alert"]').forEach((el) => (el.style.display = 'none')))
}

const {base, close} = await startServerDemo()
const browser = await chromium.launch({args: ['--hide-scrollbars', '--font-render-hinting=none']})
let failures = 0

for (const lang of LANGS) {
  for (const theme of THEMES) {
    for (const [name, start, prepare, viewport = DESKTOP, scenario] of SCREENS) {
      if (ONLY && !ONLY.has(name)) continue
      const variant = `${name}.${lang}.${theme}`
      const context = await browser.newContext({
        viewport,
        deviceScaleFactor: 2,
        colorScheme: theme,
        locale: lang === 'ru' ? 'ru-RU' : 'en-US',
        permissions: ['clipboard-read', 'clipboard-write'],
        isMobile: viewport === PHONE,
        hasTouch: viewport === PHONE,
        ...serverDemoContextOptions(),
      })
      await context.addInitScript(
        ([theme, lang]) => {
          try {
            localStorage.setItem('hse-studio-theme', JSON.stringify({state: {theme, density: 'comfortable', lang}, version: 0}))
            localStorage.setItem('hse-studio-onboarding', JSON.stringify({state: {dismissed: true}, version: 0}))
          } catch {}
        },
        [theme, lang],
      )
      await prepareServerDemoContext(context, {lang, scenario})
      const page = await context.newPage()
      try {
        await page.goto(base + start, {waitUntil: 'domcontentloaded'})
        await page.waitForLoadState('networkidle').catch(() => {})
        await page.evaluate(() => document.fonts?.ready)
        await page.waitForTimeout(1500)
        if (prepare) await prepare(page, lang)
        await page.waitForTimeout(500)
        await assertNoPersonalData(page, variant)
        await saveShot(await page.screenshot(), join(OUT, `${variant}.webp`))
        console.log('shot', variant)
      } catch (error) {
        failures++
        await page.screenshot({path: join(ROOT, 'tools/docs-studio/.build', `fail-site-${variant}.png`)}).catch(() => {})
        console.error('FAIL', variant, String(error?.message ?? error).split('\n')[0])
      } finally {
        await context.close()
      }
    }
  }
}

await browser.close()
await close()
if (failures) process.exit(1)
console.log('SHOTS_DONE →', OUT)
