// «Замечания и проверки»: вкладка «Замечания», переход к строке, трассировка требований.
const pageTab = (d, key) =>
  d.page.getByRole('group', {name: d.s('documents', 'tabs.ariaLabel')}).getByRole('button', {name: new RegExp(d.s('workbench', key))})

export default {
  stand: 'local',
  start: (w) => `/projects/${w.local.projects[w.lang].id}/documents/thesis`,
  steps: [
    async (d) => d.point(d.role('button', new RegExp(`^(${d.s('documents', 'header.build')}|${d.s('documents', 'header.rebuild')})$`)), {shot: false}),
    async (d) => d.click(pageTab(d, 'dock.issues'), {shot: false, settle: 1800}).then(() => d.pointIf('#document-tab-panel')),
    async (d) => {
      const line = d.page.locator('#document-tab-panel button, #document-tab-panel a').filter({hasText: /^:\d+$/}).first()
      if (await line.isVisible().catch(() => false)) await d.point(line)
    },
    async (d) => d.pause(600),
    async (d) => d.pause(600),
    async (d, w) => d.goto(`/projects/${w.local.projects[w.lang].id}/submit/requirements`, {settle: 2000}),
  ],
}
