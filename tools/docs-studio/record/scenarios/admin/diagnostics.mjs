// «Самодиагностика»: итог, проверка сейчас, строки с причинами, пороги.
export default {
  stand: 'server',
  persona: 'admin',
  start: '/admin/diagnostics',
  steps: [
    async (d) => d.pause(1500),
    async (d) => d.click(d.role('button', d.ui('admin/diagnostics', 'Проверить сейчас')), {settle: 3000}),
    async (d) => d.pause(800),
    async (d) => d.pause(500),
    async (d) => {
      await d.scrollTo(d.text(d.ui('admin/diagnostics', 'Пороги и уведомления')).first())
      await d.point(d.text(d.ui('admin/diagnostics', 'Пороги и уведомления')).first())
    },
    async (d) => d.pause(500),
  ],
}
