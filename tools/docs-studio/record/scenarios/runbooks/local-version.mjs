// «Локальная версия»: подключение к серверу (экран /connect) и настройки синхронизации проекта.
export default {
  stand: 'local',
  start: '/',
  steps: [
    async (d) => d.pause(800),
    async (d) => d.pause(600),
    async (d) => {
      await d.click(d.role('button', d.ui('localStudio', 'Подключиться к серверу')).first(), {shot: false, settle: 1500})
      await d.pointIf(d.page.getByLabel(d.ui('localStudio', 'Адрес сервера')).first())
    },
    async (d) => d.pause(400),
    async (d) => d.pause(400),
    async (d, w) => d.goto(`/projects/${w.local.projects[w.lang].id}/project-settings/sync`, {settle: 1800}),
  ],
}
