// «Сборка PDF»: запуск сборки, журнал на вкладке «Сборка», готовый PDF в «Превью».
export default {
  stand: 'local',
  start: (w) => `/projects/${w.local.projects[w.lang].id}/documents/thesis`,
  steps: [
    async (d) => d.click(d.role('button', new RegExp(`^(${d.s('documents', 'header.build')}|${d.s('documents', 'header.rebuild')})$`)), {settle: 600}),
    async (d) => d.click('#document-tab-compile', {shot: false, settle: 2500}).then(() => d.point('#document-tab-panel')),
    async (d) => d.pause(1500),
    async (d) => {
      await d.page.getByRole('button', {name: d.s('documents', 'header.rebuild')}).waitFor({timeout: 240000}).catch(() => {})
      await d.click('#document-tab-preview', {shot: false, settle: 2500})
      await d.page.waitForFunction(() => document.querySelector('canvas.pdf-page-canvas')?.width > 0, null, {timeout: 30000}).catch(() => {})
      await d.point('#document-tab-preview')
    },
    async (d) => d.pause(800),
  ],
}
