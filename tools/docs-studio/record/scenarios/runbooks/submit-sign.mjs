// «Сдача и подписи»: контрольные точки, библиотека подписей, упаковка.
const base = (w) => `/projects/${w.local.projects[w.lang].id}`

export default {
  stand: 'local',
  start: (w) => `${base(w)}/submit`,
  steps: [
    async (d) => d.pointIf(d.text(d.ui('workbench', 'Открыть контрольную точку')).first()),
    async (d) => d.pause(600),
    async (d, w) => d.goto(`${base(w)}/submit/signatures`, {settle: 1800}),
    async (d) => d.pause(600),
    async (d, w) => {
      await d.goto(`${base(w)}/submit`, {settle: 1500})
      await d.pointIf(d.role('button', d.ui('workbench', 'Упаковать')).first())
    },
    async (d) => d.pause(600),
  ],
}
