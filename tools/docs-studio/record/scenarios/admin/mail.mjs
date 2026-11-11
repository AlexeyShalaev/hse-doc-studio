// «Письма»: журнал писем админки. Стенд серверного демо: обычный день (admin_ready), затем тот же
// раздел без почты (admin_sso) и со сбоем входа на SMTP (ops_services_degraded). Те же экраны, что
// живые записи галереи «Админка: письма» (admin-mail-live, admin-mail-card-live).
import {switchServerDemo} from '../../../stand/server-demo.mjs'

const M = 'admin/mail'
const esc = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const startsWith = (text) => new RegExp('^' + esc(text) + '(\\s|$)')
const card = (d) => d.page.getByRole('dialog')
const heading = (d, key) => card(d).getByRole('heading', {name: d.s(M, key), exact: true})

export default {
  stand: 'demo',
  demo: 'admin_ready',
  start: '/admin/mail',
  steps: [
    // Пункт меню со счётчиком «2 письма не ушли за сутки».
    async (d) => d.point(d.page.getByRole('navigation').getByRole('link', {name: startsWith(d.s('admin/shell', 'nav.mail'))})),
    async (d) => d.click(d.role('button', startsWith(d.s(M, 'day.failed', {n: ''}).trim())), {settle: 1500}),
    // Приглашение в проект на reject-x@example.org: 550, ссылка с токеном и сообщение приглашающего.
    async (d) => {
      await d.click(d.page.getByRole('row', {name: /reject-x@example\.org/}), {shot: false, settle: 1500})
      await d.point(card(d).getByTestId('mail-card-reason'))
    },
    async (d) => {
      await d.scrollTo(heading(d, 'card.preview'))
      await d.point(card(d).getByText(d.s(M, 'card.linkHidden')))
    },
    async (d) => {
      await d.scrollTo(heading(d, 'card.next.title'))
      await d.point(card(d).getByRole('list').last())
    },
    async (d) => {
      await switchServerDemo(d.page, 'admin_sso')
      await d.goto('/admin/mail', {settle: 1500})
      await d.point(d.role('link', d.s(M, 'smtpOff.action'), {exact: true}))
    },
    async (d) => {
      await switchServerDemo(d.page, 'ops_services_degraded')
      await d.goto('/admin/mail', {settle: 1500})
      await d.point(d.role('link', d.s(M, 'hint.open'), {exact: true}))
    },
  ],
}
