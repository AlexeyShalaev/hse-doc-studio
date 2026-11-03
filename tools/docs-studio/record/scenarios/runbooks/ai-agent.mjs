// «ИИ-агент»: провайдеры в настройках, чат агента проекта, черновик запроса (без отправки:
// у стенда нет ключа модели, а ответ модели в кадре был бы невоспроизводим).
export default {
  stand: 'local',
  start: '/settings/providers',
  steps: [
    async (d) => d.pause(1200),
    async (d, w) => {
      await d.goto(`/projects/${w.local.projects[w.lang].id}/documents/thesis`, {settle: 1500})
      await d.click(d.page.locator('nav.activity-bar button', {hasText: d.t('Агент', 'Agent')}), {settle: 1500})
    },
    async (d) => {
      const fresh = d.page.locator('.chat-dock button', {hasText: d.t('Новый чат', 'New chat')}).first()
      if (await fresh.isVisible().catch(() => false)) await d.click(fresh, {settle: 1200})
    },
    async (d) => d.pause(800),
    async (d) => {
      const box = d.page.locator('.agent-composer-textarea').first()
      await box.waitFor({timeout: 8000})
      await d.type(box, d.t('Исправь опечатки в разделе «Введение»', 'Fix the typos in the Introduction'))
      await d.point(box)
    },
    async (d) => d.pause(600),
  ],
}
