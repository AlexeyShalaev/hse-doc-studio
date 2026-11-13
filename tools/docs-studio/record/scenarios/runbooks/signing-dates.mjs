// «Дата подписания»: стенд серверного демо, сценарий student_signing_dates. Свой завершённый маршрут
// студента: у научрука три метки «« 13 » ноября 2026 г.» и ЭП над итоговым PDF; проект без маршрута
// (p_01hxa4n7pq): ручная дата. Состояние демо живёт в памяти вкладки: между экранами ходим через spaGo.
import {spaGo} from '../../lib/signing.mjs'
import {DEMO_PROJECTS} from '../../../stand/server-demo.mjs'

const DOC = 'topic_application'
const SLOT = 'supervisor'
const OWN = `/projects/${DEMO_PROJECTS.own}/documents/${DOC}?tab=signatures`
// Проект демо без маршрута: подпись научрука загрузил сам автор, дату он указывает руками.
const FREE = `/projects/p_01hxa4n7pq/documents/${DOC}?tab=signatures`

export default {
  stand: 'demo',
  demo: 'student_signing_dates',
  start: OWN,
  steps: [
    async (d) => d.point(d.page.getByTestId(`slot-dates-${SLOT}`)),
    async (d) => d.point(d.page.getByTestId(`slot-date-format-${SLOT}-1`)),
    async (d) => d.point(d.text(d.s('signatureStamper', 'dates.fromRoute'), {exact: true})),
    async (d) => {
      await spaGo(d.page, FREE)
      await d.point(d.page.getByTestId(`slot-date-signed-at-${SLOT}`))
    },
    async (d) => {
      await spaGo(d.page, OWN)
      // Превью PDF в демо нет, поэтому «Добавить дату» выключена: сохранение вызывает смена формата.
      await d.page.getByTestId(`slot-date-format-${SLOT}-0`).selectOption('date_numeric')
      await d.pause(1200)
      await d.point(d.page.getByTestId('dates-reset-text'))
    },
  ],
}
