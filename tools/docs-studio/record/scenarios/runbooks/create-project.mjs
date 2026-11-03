// «Создать проект из шаблона»: мастер от экрана «Проекты» до «Проверки». Последний шаг только
// обводит «Создать проект»: дубль не плодит проекты на стенде.
const next = (d, shot = false) => d.click(d.role('button', d.s('projectCreate', 'wizard.next')), {settle: 700, shot})
const card = (d, text) => d.page.locator('button.card', {hasText: text}).first()

export default {
  stand: 'local',
  start: '/',
  steps: [
    async (d) => d.click(d.role('button', d.s('welcome', 'header.newProject')), {settle: 1200}),
    async (d) => {
      await d.click(d.page.locator('button.card').first(), {shot: false})
      await next(d)
      await d.click(card(d, d.t('ВКР', 'Thesis')))
      await next(d)
    },
    async (d) => next(d, true),
    async (d, w) => {
      await d.click(card(d, d.s('projectCreate', 'kind.projectTitle')), {shot: false})
      await next(d)
      await d.type(d.page.getByPlaceholder(d.s('projectCreate', 'folder.namePlaceholder')), d.t('Сервис бронирования переговорных', 'Meeting room booking service'))
      await d.type(d.page.getByPlaceholder(d.s('projectCreate', 'folder.folderPlaceholder')), `${w.projectsHome}/${d.t('booking', 'booking-en')}`, {delay: 15})
      await d.point(d.page.getByPlaceholder(d.s('projectCreate', 'folder.namePlaceholder')))
      await next(d)
    },
    async (d) => {
      await next(d) // язык
      if (await d.text(d.s('projectCreate', 'steps.presentation.title'), {exact: true}).first().isVisible().catch(() => false)) await next(d)
      await d.type(d.page.getByPlaceholder(d.s('projectCreate', 'authors.namePlaceholder')).first(), d.t('Смирнова Анна Сергеевна', 'Anna Smirnova'))
      await next(d)
      await d.type(d.page.getByPlaceholder(d.s('projectCreate', 'supervisor.namePlaceholderUniversity')).first(), d.t('Петров Пётр Петрович', 'Peter Petrov'))
      await next(d)
      // «Мета»: обязательных полей у ВКР нет, идём к «Проверке».
      if (!(await d.role('button', d.s('projectCreate', 'wizard.create')).isVisible().catch(() => false))) await next(d)
    },
    async (d) => d.point(d.role('button', d.s('projectCreate', 'wizard.create'))),
  ],
}
