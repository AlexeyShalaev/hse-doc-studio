// «Подписать документы»: страница подписанта на стенде серверного демо. Студента демо просят
// подписать заявление в чужом проекте; подпись научрука размещена, поэтому способов два.
import {SIGNER_TASK, drawSignature, signer} from '../../lib/signing.mjs'

export default {
  stand: 'demo',
  start: SIGNER_TASK,
  steps: [
    async (d) => d.point(d.text(d.s('signing/signing', 'progress.title'), {exact: true})),
    async (d, w) => d.click(signer.toPlace(d.page, w.lang), {shot: false}),
    async (d, w) => {
      await d.click(signer.method(d.page, 'detached'), {shot: false})
      await d.point(d.text(d.s('signing/signing', 'esign.ways'), {exact: true}))
    },
    async (d, w) => {
      await d.click(signer.method(d.page, 'image'), {shot: false})
      await d.click(signer.draw(d.page, w.lang), {shot: false})
      await drawSignature(d.page)
      await d.point(signer.drawDone(d.page, w.lang))
      await d.locator(signer.drawDone(d.page, w.lang)).click()
      await d.pause(500)
    },
    async (d, w) => {
      await d.click(signer.approve(d.page, w.lang), {shot: false, settle: 1800})
      await d.page.evaluate(() => document.querySelectorAll('*').forEach((el) => el.scrollTop > 0 && (el.scrollTop = 0)))
      await d.pause(500)
    },
    async (d) => d.pause(300),
  ],
}
