// «Мои раннеры: диск»: окно «Диск» своего раннера, очистка с флажком отката и уведомление об
// очистке администратором. Стенд серверного демо, сценарий runners_ready: те же экраны, что раздел
// галереи «Мои раннеры: диск» (живая запись live_disk_notice).
const D = 'runnerDisk'
const R = 'runners'
const HOME = 'Домашний сервер'
const dialog = (d) => d.page.getByRole('dialog').last()
const doneText = (d) =>
  new RegExp('^' + d.s(D, 'job.done', {size: '@'}).replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace('@', '[\\d.,]+\\s?\\S+') + '$')
const exact = (d, role, name) => dialog(d).getByRole(role, {name, exact: true})

export default {
  stand: 'demo',
  demo: 'runners_ready',
  start: '/settings/runners',
  steps: [
    async (d) => d.point(d.page.getByRole('button', {name: d.s('appChrome', 'settingsPage.sections.runners')}).or(d.page.getByRole('link', {name: d.s('appChrome', 'settingsPage.sections.runners')})).first()),
    async (d) => {
      await d.click(d.role('button', d.s(R, 'mine.actionsLabel', {name: HOME})), {shot: false, settle: 700})
      await d.click(d.role('menuitem', d.s(R, 'mine.disk'), {exact: true}), {settle: 1500})
    },
    async (d) => d.pause(400),
    async (d) => {
      await d.click(exact(d, 'button', d.s(D, 'old.action')), {shot: false, settle: 900})
      const box = dialog(d).getByRole('checkbox').first()
      await d.click(box, {shot: false, settle: 500})
      await d.point(exact(d, 'button', d.s(D, 'confirm.remove')))
    },
    async (d) => {
      await d.click(exact(d, 'button', d.s(D, 'confirm.remove')), {shot: false, settle: 900})
      // Итог «Освобождено N» целиком, а не «освобождено 0 MB» в строке хода.
      const done = dialog(d).getByText(doneText(d)).first()
      await done.waitFor({timeout: 120000})
      await done.scrollIntoViewIfNeeded()
      await d.pause(600)
    },
    async (d) => {
      // Уведомление лежит во «Входящих» демо-мира (ntf_demo_runner_disk): «Домашний сервер», 7.25 ГБ.
      await d.goto('/inbox', {settle: 1500})
      const notice = d.s('inbox', 'kind.runner_disk_cleaned', {name: HOME, size: ''}).split('“')[0].split('«')[0].trim()
      await d.point(d.page.getByText(notice).filter({visible: true}).first())
    },
  ],
}
