// «Отправить на подписание»: экран маршрута на стенде серверного демо (stand/server-demo.mjs).
// Кадры: кнопка на карточке «Подписание», шаги маршрута, «Где подписи», отправка.
import {CHECKPOINT, editor} from '../../lib/signing.mjs'

export default {
  stand: 'demo',
  start: CHECKPOINT,
  steps: [
    async (d) => d.click(d.page.getByTestId('signing-card').getByRole('button', {name: d.s('signingProgress', 'action.send')})),
    async (d) => d.point(d.text(d.s('signingRouteEditor', 'docs.title'), {exact: true})),
    async (d, w) => d.point(editor.steps(d.page, w.lang)),
    async (d, w) => {
      await d.click(editor.toPlacement(d.page, w.lang), {shot: false})
      await d.click(editor.placeOnPage(d.page, w.lang))
    },
    async (d) => d.point(d.text(d.s('signingRouteEditor', 'mine.title'), {exact: true})),
    async (d) => d.point(editor.message(d.page)),
    async (d, w) => d.point(editor.send(d.page, w.lang)),
  ],
}
