// «Входящие: на подпись»: колокольчик и вкладка «На подпись» на стенде серверного демо.
export default {
  stand: 'demo',
  start: '/inbox',
  steps: [
    async (d) => {
      await d.click(d.page.getByTestId('inbox-bell'), {shot: false})
      await d.click(d.page.getByTestId('inbox-popover-signing'))
    },
    async (d) => d.point(d.page.getByTestId('inbox-tab-signing')),
    async (d) => d.point(d.role('button', d.s('inbox', 'signing.open')).nth(1)),
  ],
}
