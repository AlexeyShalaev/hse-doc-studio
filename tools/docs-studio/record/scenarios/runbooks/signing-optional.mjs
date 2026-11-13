// «Необязательные подписи и пропуск»: стенд серверного демо, сценарий student_signing_optional.
// Студент добавил к заявлению подпись академрука и отметил её необязательной; научрук согласовал,
// очередь академрука. Состояние демо живёт в памяти вкладки: между экранами ходим через spaGo.
import {CHECKPOINT, spaGo} from '../../lib/signing.mjs'
import {DEMO_PROJECTS} from '../../../stand/server-demo.mjs'

const SIGNATURES = `/projects/${DEMO_PROJECTS.own}/documents/topic_application?tab=signatures`
const SLOT = 'academic_supervisor'

export default {
  stand: 'demo',
  demo: 'student_signing_optional',
  start: SIGNATURES,
  steps: [
    async (d) => d.point(d.page.getByTestId(`doc-optional-${SLOT}`)),
    async (d) => {
      await spaGo(d.page, CHECKPOINT)
      await d.point(d.page.getByTestId('signing-card'))
    },
    async (d) => {
      const skip = d.page.locator('[data-testid^="signing-skip-"]:not([data-testid="signing-skip-confirm"]):not([data-testid^="signing-skip-hint"]):not([data-testid^="signing-skip-blocker"]):not([data-testid^="signing-skip-returns"]):not([data-testid="signing-skip-lines"])').first()
      await d.click(skip, {shot: false, settle: 800})
      await d.point(d.page.getByTestId('signing-skip-lines'))
    },
    async (d) => {
      await d.click(d.page.getByTestId('signing-skip-confirm'), {shot: false, settle: 1800})
      await d.pause(500)
    },
  ],
}
