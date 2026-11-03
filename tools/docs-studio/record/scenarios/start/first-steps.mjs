// «Начало работы»: вход на сервер, список проектов, документ, возврат, справка по экрану.
export default {
  stand: 'server',
  persona: null,
  start: '/login',
  steps: [
    async (d) => d.pause(1200),
    async (d, w) => {
      const who = w.personas[w.lang === 'en' ? 'victor' : 'anna']
      await d.type(d.page.getByLabel(d.ui('auth', 'Почта')).first(), who.email)
      await d.type(d.page.getByLabel(d.ui('auth', 'Пароль')).first(), who.password, {delay: 10})
      await d.click(d.role('button', d.ui('auth', 'Войти'), {exact: true}), {settle: 2500})
    },
    // Проект из сида server-lite (scripts/dev/server-lite/seed.py): у Анны русский, у Виктора английский.
    async (d) => d.click(d.text(d.t('Курсовая: анализ CI/CD', 'Coursework: static analysis'), {exact: true}).first(), {settle: 2500}),
    async (d) => d.point(d.page.locator('nav.activity-bar').first()),
    async (d) => d.click(d.role('button', d.s('appChrome', 'titlebar.projects')), {settle: 1500}),
    async (d) => {
      await d.click('[data-testid="help-menu-trigger"]', {settle: 700})
      await d.click('[data-testid="help-menu-screen"]', {settle: 1500})
    },
  ],
}
