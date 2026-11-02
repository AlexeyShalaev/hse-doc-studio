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
    async (d) => d.click(d.page.locator('a[href^="/projects/"], button.card, [data-testid^="project-card"]').first(), {settle: 2500}),
    async (d) => d.point(d.page.locator('nav.activity-bar').first()),
    async (d) => d.click(d.role('button', d.s('appChrome', 'titlebar.projects')), {settle: 1500}),
    async (d) => d.click('[data-testid="help-button"]', {settle: 1500}),
  ],
}
