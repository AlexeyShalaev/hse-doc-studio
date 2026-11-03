// «Сборка PDF»: запуск сборки, журнал на вкладке «Сборка», готовый PDF в «Превью».
const pageTab = (d, key) =>
  d.page.getByRole('group', {name: d.s('documents', 'tabs.ariaLabel')}).getByRole('button', {name: new RegExp(d.s('workbench', key))})

export default {
  stand: 'local',
  start: (w) => `/projects/${w.local.projects[w.lang].id}/documents/thesis`,
  steps: [
    async (d) => d.click(d.role('button', new RegExp(`^(${d.s('documents', 'header.build')}|${d.s('documents', 'header.rebuild')})$`)), {settle: 600}),
    async (d) => d.click(pageTab(d, 'dock.build'), {shot: false, settle: 2500}).then(() => d.pointIf('#document-tab-panel')),
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
