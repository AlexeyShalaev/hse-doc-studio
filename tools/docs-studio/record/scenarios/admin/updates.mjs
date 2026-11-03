// «Обновления»: версия, проверка релизов, политика. Само обновление на стенде не запускается.
export default {
  stand: 'server',
  persona: 'admin',
  start: '/admin/updates',
  steps: [
    async (d) => d.pause(1500),
    async (d) => d.pointIf(d.role('button', d.ui('admin/updates', 'Проверить сейчас')), {shot: false}),
    async (d) => d.pointIf(d.role('button', d.ui('admin/updates', 'Обновить сейчас'))),
    async (d) => d.pause(500),
    async (d) => d.pause(500),
    async (d) => d.pause(500),
    async (d) => {
      await d.scrollTo(d.text(d.ui('admin/updates', 'Политика и окно')).first())
      await d.point(d.text(d.ui('admin/updates', 'Политика и окно')).first())
    },
  ],
}
