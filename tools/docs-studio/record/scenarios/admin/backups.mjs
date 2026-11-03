// «Бэкапы»: назначение, расписание и хранение. Сохранения нет: стенд не настраивается дублем.
export default {
  stand: 'server',
  persona: 'admin',
  start: '/admin/backups',
  steps: [
    async (d) => d.click(d.role('button', d.ui('admin/backups', 'Добавить')), {settle: 1200}),
    async (d) => d.pointIf(d.page.getByRole('dialog').first()),
    async (d) => {
      await d.press('Escape')
      await d.scrollTo(d.text(d.ui('admin/backups', 'Расписание и хранение')).first())
      await d.point(d.text(d.ui('admin/backups', 'Расписание и хранение')).first())
    },
    async (d) => d.pause(600),
    async (d) => d.pause(600),
    async (d) => {
      await d.page.evaluate(() => window.scrollTo({top: 0}))
      await d.pause(800)
    },
    async (d) => d.pause(500),
  ],
}
