// Маршрут подписания на стенде серверного демо (stand/server-demo.mjs): общие ходы для кадров
// справки (сценарии runbooks/signing-*, runbooks/sign-documents) и сайта документации
// (site-shots.mjs). Состояние демо живёт в памяти вкладки: между экранами ходим внутри
// приложения (`spaGo`), а не перезагрузкой, иначе отправленный маршрут пропадёт.
import {DEMO_PROFILE, DEMO_PROJECTS} from '../../stand/server-demo.mjs'
import {uiString} from './director.mjs'

export const ROUTE_EDITOR = `/projects/${DEMO_PROJECTS.own}/submit/cp/${DEMO_PROFILE}/route`
export const CHECKPOINT = `/projects/${DEMO_PROJECTS.own}/submit/cp/${DEMO_PROFILE}`
export const INBOX_SIGNING = '/inbox?tab=signing'
/** Задача подписанта в демо: «Industry adoption of CI», подпись научрука размещена, способов два. */
export const SIGNER_TASK = `/sign/${DEMO_PROJECTS.signEn}/sr_demo0001`

export const s = (lang, ns, key, vars) => uiString(lang, ns, key, vars)

/** Переход внутри приложения без перезагрузки: память демо (маршруты, задачи) сохраняется. */
export async function spaGo(page, path, settle = 1800) {
  await page.evaluate((p) => {
    history.pushState({}, '', p)
    dispatchEvent(new PopStateEvent('popstate'))
  }, path)
  await page.waitForTimeout(settle)
}

const byRole = (page, role, name, exact = true) => page.getByRole(role, {name, exact}).first()

export const editor = {
  toPlacement: (page, lang) => byRole(page, 'button', s(lang, 'signingRouteEditor', 'blocker.toPlacement')),
  placeOnPage: (page, lang) => byRole(page, 'button', s(lang, 'signingRouteEditor', 'placements.place', {page: 1})),
  placements: (page, lang) => page.getByText(s(lang, 'signingRouteEditor', 'placements.title'), {exact: true}).first(),
  blockers: (page, lang) => page.getByText(s(lang, 'signingRouteEditor', 'send.blockers'), {exact: true}).first(),
  steps: (page, lang) => page.getByText(s(lang, 'signingRouteEditor', 'steps.title'), {exact: true}).first(),
  message: (page) => page.locator('textarea').first(),
  send: (page, lang) => byRole(page, 'button', s(lang, 'signingRouteEditor', 'send.send')),
}

export const card = {
  copyLink: (page, lang) => byRole(page, 'button', s(lang, 'signingProgress', 'action.copyLink')),
  remind: (page, lang) => byRole(page, 'button', s(lang, 'signingProgress', 'action.remind')),
  title: (page, lang) => page.getByText(s(lang, 'signingProgress', 'title'), {exact: true}).first(),
}

export const signer = {
  method: (page, method) => page.getByTestId(`signing-method-${method}`),
  howTo: (page, lang) => page.getByText(s(lang, 'signing/signing', 'method.title'), {exact: true}).first(),
  toPlace: (page, lang) => byRole(page, 'button', s(lang, 'signing/signing', 'docs.toPlace')),
  draw: (page, lang) => byRole(page, 'button', s(lang, 'signing/signing', 'image.draw')),
  drawDone: (page, lang) => byRole(page, 'button', s(lang, 'signing/signing', 'image.done')),
  remember: (page, lang) => page.getByLabel(s(lang, 'signing/signing', 'image.remember')).first(),
  approve: (page, lang) => byRole(page, 'button', s(lang, 'signing/signing', 'actions.approve')),
  approveAndSign: (page, lang) => byRole(page, 'button', s(lang, 'signing/signing', 'actions.approveAndSign')),
  returnButton: (page, lang) => byRole(page, 'button', s(lang, 'signing/signing', 'actions.return')),
  returnField: (page) => page.getByRole('dialog').locator('textarea').first(),
}

/** Сообщение автора в поле «Сообщение подписантам». */
export const authorMessage = (lang) =>
  lang === 'en' ? 'Please sign the application by Friday.' : 'Прошу подписать заявление до пятницы.'

/** Комментарий возврата на доработку. */
export const returnComment = (lang) =>
  lang === 'en' ? 'Please clarify the project goal in the second paragraph.' : 'Уточните цель проекта во втором абзаце.'

/** Включить место подписи научрука: помеха «подпись не размещена» уходит, можно отправлять. */
export async function placeSupervisor(page, lang) {
  await editor.toPlacement(page, lang).click()
  await page.waitForTimeout(600)
  await editor.placeOnPage(page, lang).click()
  await page.waitForTimeout(900)
}

/** Отправить маршрут: после отправки приложение само уходит на страницу точки. */
export async function sendRoute(page, lang) {
  await editor.send(page, lang).click()
  await page.waitForTimeout(2200)
}

/** Расписаться на поле «Нарисовать»: росчерк мышью по холсту. */
export async function drawSignature(page) {
  const canvas = page.locator('canvas').filter({visible: true}).last()
  await canvas.scrollIntoViewIfNeeded()
  const box = await canvas.boundingBox()
  if (!box) throw new Error('нет поля для подписи')
  const at = (fx, fy) => [box.x + box.width * fx, box.y + box.height * fy]
  const strokes = [
    [[0.12, 0.7], [0.2, 0.25], [0.28, 0.3], [0.3, 0.65], [0.38, 0.35], [0.45, 0.3], [0.48, 0.6], [0.56, 0.4], [0.64, 0.38], [0.66, 0.62], [0.76, 0.45], [0.88, 0.4]],
    [[0.25, 0.8], [0.55, 0.76], [0.85, 0.72]],
  ]
  for (const stroke of strokes) {
    const [x0, y0] = at(...stroke[0])
    await page.mouse.move(x0, y0)
    await page.mouse.down()
    for (const point of stroke.slice(1)) {
      const [x, y] = at(...point)
      await page.mouse.move(x, y, {steps: 6})
    }
    await page.mouse.up()
  }
  await page.waitForTimeout(300)
}

/** Прокрутить блок к верху его прокручиваемого контейнера. */
export async function scrollToTop(locator, page, offset = 0) {
  await locator.waitFor({state: 'visible', timeout: 30000})
  await locator.evaluate((el, offset) => {
    el.scrollIntoView({block: 'start'})
    let node = el.parentElement
    while (node && node.scrollHeight <= node.clientHeight) node = node.parentElement
    if (node && offset) node.scrollTop -= offset
  }, offset)
  await page.waitForTimeout(600)
}
