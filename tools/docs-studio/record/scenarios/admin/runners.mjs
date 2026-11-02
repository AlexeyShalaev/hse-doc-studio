// «Раннеры сборки»: раздел, токен регистрации, команда запуска, очередь.
const nav = (d, ru) => d.page.getByRole('link', {name: d.ui('admin/shell', ru)}).first()

export default {
  stand: 'server',
  persona: 'admin',
  start: '/admin',
  steps: [
    async (d) => d.click(nav(d, 'Раннеры и очередь'), {settle: 1500}),
    async (d) => {
      await d.click(d.role('button', d.ui('admin/runners', 'Создать токен')), {settle: 900})
      const name = d.page.getByRole('dialog').getByRole('textbox').first()
      if (await name.isVisible().catch(() => false)) await d.type(name, d.t('Сборочная машина кафедры', 'Department build box'))
    },
    async (d) => {
      await d.click(d.page.getByRole('dialog').getByRole('button', {name: d.ui('admin/runners', 'Создать'), exact: true}), {shot: false, settle: 1500})
      const command = d.text(d.ui('admin/runners', 'Команда запуска')).first()
      await command.waitFor({timeout: 15000}).catch(() => {})
      await d.pointIf(command)
    },
    async (d) => {
      await d.press('Escape')
      await d.pause(600)
    },
    async (d) => d.pause(500),
    async (d) => d.click(d.role('tab', d.ui('admin/runners', 'Очередь')), {settle: 1200}),
  ],
}
