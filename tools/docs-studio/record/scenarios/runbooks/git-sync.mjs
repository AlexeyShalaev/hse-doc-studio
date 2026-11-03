// «Git-синхронизация»: кнопка синхронизации и мастер подключения репозитория. Подключение
// не завершается: на стенде нет удалённого репозитория.
export default {
  stand: 'local',
  start: (w) => `/projects/${w.local.projects[w.lang].id}/documents/thesis`,
  steps: [
    async (d) => {
      await d.click(d.role('button', new RegExp(d.ui('gitSync', 'Синхронизация'))).first(), {shot: false, settle: 900})
      await d.pointIf(d.text(d.ui('gitSync', 'Подключить репозиторий')).first())
    },
    async (d) => {
      const connect = d.text(d.ui('gitSync', 'Подключить репозиторий')).first()
      if (await connect.isVisible().catch(() => false)) await d.click(connect, {shot: false, settle: 1500})
    },
    async (d) => d.pause(600),
    async (d) => d.pause(400),
    async (d) => d.press('Escape'),
    async (d) => d.pause(400),
    async (d) => d.pause(400),
  ],
}
