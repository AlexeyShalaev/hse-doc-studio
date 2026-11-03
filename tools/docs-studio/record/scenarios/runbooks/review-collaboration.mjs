// «Ревью и совместная работа»: участники проекта, входящие, редактор с комментариями.
const project = (w) => w.projects[0]?.id

export default {
  stand: 'server',
  persona: 'anna',
  start: (w) => `/projects/${project(w)}/project-settings/people`,
  steps: [
    async (d) => d.pause(1500),
    async (d) => d.pointIf(d.page.getByRole('textbox').first()),
    async (d) => d.pause(600),
    async (d) => d.goto('/inbox', {settle: 1500}),
    async (d, w) => {
      await d.goto(`/projects/${project(w)}/documents`, {settle: 1500})
      const doc = d.page.locator('a[href*="/documents/"]').first()
      if (await doc.isVisible().catch(() => false)) {
        await d.click(doc, {shot: false, settle: 1500})
        await d.click('#document-tab-editor', {shot: false, settle: 2000})
      }
    },
    async (d) => d.pause(600),
  ],
}
