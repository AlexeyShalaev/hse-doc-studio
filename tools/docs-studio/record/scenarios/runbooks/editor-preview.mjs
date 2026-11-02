// «Редактор и превью»: превью PDF, редактор, режим «Рядом». Текст не правится: стенд остаётся чистым.
const waitPdf = (d) =>
  d.page.waitForFunction(() => document.querySelector('canvas.pdf-page-canvas')?.width > 0, null, {timeout: 30000}).catch(() => {})

export default {
  stand: 'local',
  start: (w) => `/projects/${w.local.projects[w.lang].id}/documents/thesis`,
  steps: [
    async (d) => {
      await d.click('#document-tab-preview', {shot: false})
      await waitPdf(d)
    },
    async (d) => {
      await waitPdf(d)
      await d.point('canvas.pdf-page-canvas')
    },
    async (d) => d.click('#document-tab-editor', {settle: 1800}),
    async (d) => d.pause(1200),
    async (d) => {
      await d.click('#document-tab-side', {shot: false, settle: 1500})
      await waitPdf(d)
      await d.press('Escape')
      await d.point('#document-tab-side')
    },
    async (d) => d.pause(1000),
  ],
}
