// «Локальная версия»: клонирование с сервера Студии и настройки синхронизации проекта.
export default {
  stand: 'local',
  start: '/',
  steps: [
    async (d) => d.pause(800),
    async (d) => d.pause(600),
    async (d) => {
      await d.click(d.role('button', d.ui('welcome', 'Клонировать из git')).first(), {shot: false, settle: 1500})
      await d.pointIf(d.text(d.ui('gitRemote', 'Сервер HSE Doc Studio')).first())
    },
    async (d) => d.pause(400),
    async (d) => d.pause(400),
    async (d, w) => d.goto(`/projects/${w.local.projects[w.lang].id}/project-settings/sync`, {settle: 1800}),
  ],
}
