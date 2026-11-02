// «Приглашения»: новое приглашение без почты и ссылка-приглашение.
export default {
  stand: 'server',
  persona: 'admin',
  start: '/admin/users',
  steps: [
    async (d) => d.click(d.role('button', d.ui('admin/users', 'Пригласить')), {settle: 1200}),
    async (d) => {
      await d.scrollTo(d.text(d.ui('admin/users', 'Новое приглашение')).first())
      await d.click(d.role('button', d.ui('admin/users', 'Создать приглашение')), {settle: 1500})
    },
    async (d) => d.pointIf(d.text(d.ui('admin/users', 'Ссылка-приглашение')).first()),
    async (d) => d.pause(600),
    async (d) => d.goto('/admin/settings', {settle: 1500}),
    async (d) => d.goto('/admin/users?tab=approvals', {settle: 1500}),
  ],
}
