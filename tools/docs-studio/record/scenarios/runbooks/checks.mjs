// «Замечания и проверки»: вкладка «Замечания», переход к строке, трассировка требований.
export default {
  stand: 'local',
  start: (w) => `/projects/${w.local.projects[w.lang].id}/documents/thesis`,
  steps: [
    async (d) => d.point(d.role('button', new RegExp(`^(${d.s('documents', 'header.build')}|${d.s('documents', 'header.rebuild')})$`)), {shot: false}),
    async (d) => d.click('#document-tab-checks', {shot: false, settle: 1800}).then(() => d.point('#document-tab-panel')),
    async (d) => {
      const line = d.page.locator('#document-tab-panel button, #document-tab-panel a').filter({hasText: /^:\d+$/}).first()
      if (await line.isVisible().catch(() => false)) await d.point(line)
    },
    async (d) => d.pause(600),
    async (d) => d.pause(600),
    async (d, w) => d.goto(`/projects/${w.local.projects[w.lang].id}/submit/requirements`, {settle: 2000}),
  ],
}
