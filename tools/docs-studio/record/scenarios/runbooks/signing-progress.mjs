// «Ход подписания»: карточка «Подписание» после отправки, стенд серверного демо.
// Маршрут отправляется в начале первого шага, дальше всё на странице точки без перезагрузки.
import {ROUTE_EDITOR, authorMessage, card, editor, placeSupervisor, sendRoute} from '../../lib/signing.mjs'

export default {
  stand: 'demo',
  start: ROUTE_EDITOR,
  steps: [
    async (d, w) => {
      await placeSupervisor(d.page, w.lang)
      await editor.message(d.page).fill(authorMessage(w.lang))
      await sendRoute(d.page, w.lang)
      await d.mount()
      await d.point(card.title(d.page, w.lang))
    },
    async (d, w) => d.point(card.remind(d.page, w.lang)),
    async (d, w) => d.click(card.copyLink(d.page, w.lang), {shot: false}),
    async (d) => d.pause(400),
    async (d) => d.pause(200),
    async (d) => d.pause(200),
  ],
}
