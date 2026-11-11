// «Хранилище и место»: «Освободить место» и диск общего раннера из блока «Где ещё освободить место».
// Стенд серверного демо, сценарий admin_ready: те же экраны, что живые записи галереи
// «Хранилище: освободить место» (free_live) и «Раннеры: диск».
const S = 'admin/storage'
const D = 'runnerDisk'
const dialog = (d) => d.page.getByRole('dialog')
const doneText = (d) =>
  new RegExp('^' + d.s(D, 'job.done', {size: '@'}).replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace('@', '[\\d.,]+\\s?\\S+') + '$')
const exact = (d, role, name) => dialog(d).getByRole(role, {name, exact: true})

export default {
  stand: 'demo',
  demo: 'admin_ready',
  start: '/admin/storage',
  steps: [
    async (d) => d.click(d.role('button', d.s(S, 'storage.free.action'), {exact: true}), {settle: 1500}),
    async (d) => d.click(exact(d, 'button', d.s(S, 'storage.free.action')), {settle: 1200}),
    async (d) => {
      await dialog(d).getByText(d.t('Готово', 'Done')).first().waitFor({timeout: 20000})
      await d.pause(600)
    },
    async (d) => {
      await d.press('Escape')
      await d.click(d.role('button', d.s(S, 'storage.free.more.runnerOpen', {name: 'runner-1'})), {settle: 1500})
    },
    async (d) => d.pause(400),
    async (d) => {
      await d.click(exact(d, 'button', d.s(D, 'cleanAll')), {shot: false, settle: 900})
      await d.point(exact(d, 'button', d.s(D, 'confirm.action')))
    },
    async (d) => {
      await d.click(exact(d, 'button', d.s(D, 'confirm.action')), {shot: false, settle: 900})
      // Итог «Освобождено N» целиком, а не «освобождено 0 MB» в строке хода.
      const done = dialog(d).getByText(doneText(d)).first()
      await done.waitFor({timeout: 120000})
      await done.scrollIntoViewIfNeeded()
      await d.pause(600)
    },
  ],
}
