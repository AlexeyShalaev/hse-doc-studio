// То, против чего пишется шаг сценария: страница плюс курсор и кольцо подсветки, чтобы ролик
// читался без озвучки и без титров (слова живут в шагах статьи). Оверлеи — DOM-элементы с
// pointer-events: none, анимация через Web Animations API из page.evaluate (изолированный мир,
// CSP приложения не мешает). Скриншот шага включает кольцо: обвести кнопку и есть смысл кадра.
const CURSOR = 'docs-studio-cursor'
const RING = 'docs-studio-ring'
const CSS = `#${CURSOR}{position:fixed;z-index:2147483647;width:20px;height:20px;pointer-events:none;left:50%;top:50%;opacity:0;
filter:drop-shadow(0 1px 2px rgba(0,0,0,.45))}
#${RING}{position:fixed;z-index:2147483646;border:3px solid oklch(62% 0.19 230);border-radius:8px;
box-shadow:0 0 0 4px oklch(62% 0.19 230 / .2);pointer-events:none;opacity:0}`
const SVG = `<svg viewBox="0 0 18 18" xmlns="http://www.w3.org/2000/svg"><path d="M2 1.5 L2 14.5 L5.6 11.2 L8 16.2 L10.3 15.2 L7.9 10.3 L12.6 10.1 Z" fill="#fff" stroke="#111" stroke-width="1.2" stroke-linejoin="round"/></svg>`

import {existsSync, readFileSync} from 'node:fs'
import {join, resolve} from 'node:path'

const LOCALES = resolve(import.meta.dirname, '../../../../services/web-app/src/shared/lib/i18n/locales')
const dictionaries = new Map()

/** Строка интерфейса из словаря приложения: s('projectCreate', 'wizard.next'), админка: s('admin/backups', …). */
export function uiString(lang, ns, key, vars = {}, loadOnly = false) {
  const id = `${lang}/${ns}`
  if (!dictionaries.has(id)) {
    const file = join(LOCALES, lang, `${ns}.json`)
    if (!existsSync(file)) throw new Error(`нет словаря ${id}`)
    dictionaries.set(id, JSON.parse(readFileSync(file, 'utf-8')))
  }
  if (loadOnly) return 
  const value = key.split('.').reduce((node, part) => node?.[part], dictionaries.get(id))
  if (typeof value !== 'string') throw new Error(`нет строки ${id}:${key}`)
  return value.replace(/\{\{(\w+)\}\}/g, (_m, name) => String(vars[name] ?? ''))
}

const flatten = (node, prefix = '', out = {}) => {
  for (const [k, v] of Object.entries(node)) {
    if (typeof v === 'string') out[`${prefix}${k}`] = v
    else if (v && typeof v === 'object') flatten(v, `${prefix}${k}.`, out)
  }
  return out
}

/**
 * Та же строка на языке дубля по русскому тексту: ui('admin/backups', 'Добавить') → 'Add' в en.
 * Сценарий пишется русскими строками интерфейса, а английский дубль берёт перевод из словаря.
 */
export function uiByRu(lang, ns, ruText) {
  uiString('ru', ns, '__probe__', {}, true)
  const ru = flatten(dictionaries.get(`ru/${ns}`))
  const key = Object.keys(ru).find((k) => ru[k] === ruText)
  if (!key) throw new Error(`нет строки «${ruText}» в ru/${ns}`)
  return lang === 'ru' ? ruText : uiString(lang, ns, key)
}

export class Director {
  constructor(page, world, {onShot}) {
    this.page = page
    this.world = world
    this._onShot = onShot
    this.stepIndex = 0
    this.shotWanted = false
    this.shotTaken = false
    this.state = {}
  }

  /** Строка интерфейса под язык дубля: d.t('Новый проект', 'New project'). */
  t(ru, en) {
    return this.world.lang === 'en' ? en : ru
  }

  /** Строка интерфейса на языке дубля из словарей приложения. */
  s(ns, key, vars) {
    return uiString(this.world.lang, ns, key, vars)
  }

  /** Строка интерфейса по русскому тексту: d.ui('admin/backups', 'Добавить'). */
  ui(ns, ruText) {
    return uiByRu(this.world.lang, ns, ruText)
  }

  async mount() {
    await this.page.addStyleTag({content: CSS}).catch(() => {})
    await this.page
      .evaluate(({CURSOR, RING, SVG}) => {
        if (document.getElementById(CURSOR)) return
        const c = document.createElement('div')
        c.id = CURSOR
        c.innerHTML = SVG
        document.body.appendChild(c)
        const r = document.createElement('div')
        r.id = RING
        document.body.appendChild(r)
      }, {CURSOR, RING, SVG})
      .catch(() => {})
  }

  async goto(path, {settle = 1200} = {}) {
    await this.page.goto(`${this.world.baseUrl}${path}`, {waitUntil: 'domcontentloaded'})
    await this.page.waitForLoadState('networkidle').catch(() => {})
    await this.page.evaluate(() => document.fonts?.ready).catch(() => {})
    await this.page.waitForTimeout(settle)
    await this.mount()
  }

  locator(target) {
    return typeof target === 'string' ? this.page.locator(target).first() : target.first()
  }

  /** По роли и подписи: d.role('button', d.t('Далее', 'Next')). */
  role(role, name, opts = {}) {
    return this.page.getByRole(role, {name, ...opts})
  }

  text(text, opts = {}) {
    return this.page.getByText(text, opts)
  }

  async pause(ms) {
    await this.page.waitForTimeout(ms)
  }

  async _box(target) {
    const loc = this.locator(target)
    await loc.waitFor({state: 'visible', timeout: 15000})
    await loc.scrollIntoViewIfNeeded().catch(() => {})
    const box = await loc.boundingBox()
    if (!box) throw new Error(`элемент не виден: ${String(target)}`)
    return box
  }

  async moveTo(target, {duration = 650} = {}) {
    const box = await this._box(target)
    const x = box.x + box.width / 2
    const y = box.y + box.height / 2
    await this.page.evaluate(({CURSOR, x, y, duration}) => {
      const c = document.getElementById(CURSOR)
      if (!c) return
      const rect = c.getBoundingClientRect()
      const from = c.style.opacity === '1' ? {l: rect.left, t: rect.top} : {l: x - 60, t: y + 40}
      c.style.opacity = '1'
      c.animate([{left: `${from.l}px`, top: `${from.t}px`}, {left: `${x}px`, top: `${y}px`}], {duration, easing: 'cubic-bezier(.45,0,.2,1)', fill: 'forwards'})
    }, {CURSOR, x, y, duration})
    await this.page.mouse.move(x, y, {steps: 8})
    await this.page.waitForTimeout(duration + 60)
    return box
  }

  async highlight(target, {pad = 5} = {}) {
    const box = await this._box(target)
    await this.page.evaluate(({RING, box, pad}) => {
      const r = document.getElementById(RING)
      if (!r) return
      r.getAnimations().forEach((a) => a.cancel())
      Object.assign(r.style, {left: `${box.x - pad}px`, top: `${box.y - pad}px`, width: `${box.width + pad * 2}px`, height: `${box.height + pad * 2}px`})
      r.animate([{opacity: 0, transform: 'scale(1.05)'}, {opacity: 1, transform: 'scale(1)'}], {duration: 240, easing: 'ease-out', fill: 'forwards'})
    }, {RING, box, pad})
    await this.page.waitForTimeout(280)
  }

  async unhighlight() {
    await this.page
      .evaluate(({RING}) => {
        document.getElementById(RING)?.animate([{opacity: 1}, {opacity: 0}], {duration: 180, fill: 'forwards'})
      }, {RING})
      .catch(() => {})
  }

  /** Главный глагол шага: подвести курсор, обвести, снять кадр шага (если нужен и ещё не снят), нажать. */
  async click(target, {settle = 900, ring = true, shot = true} = {}) {
    await this.moveTo(target)
    if (ring) await this.highlight(target)
    if (shot) await this.shot()
    await this.locator(target).click()
    await this.unhighlight()
    await this.page.waitForTimeout(settle)
    await this.mount()
  }

  /** Обвести без нажатия: «найдите поле X». */
  async point(target, {shot = true} = {}) {
    await this.moveTo(target)
    await this.highlight(target)
    if (shot) await this.shot()
  }

  /** Обвести, если элемент есть: необязательная часть экрана не роняет дубль. */
  async pointIf(target, opts) {
    const loc = this.locator(target)
    if (await loc.isVisible().catch(() => false)) await this.point(loc, opts)
  }

  /** Прокрутить к элементу так, чтобы его блок встал вверху кадра. */
  async scrollTo(target) {
    const loc = this.locator(target)
    await loc.waitFor({state: 'visible', timeout: 15000})
    await loc.evaluate((el) => el.scrollIntoView({block: 'start'}))
    await this.page.waitForTimeout(600)
  }

  async type(target, text, {delay = 30} = {}) {
    await this.moveTo(target)
    await this.locator(target).click()
    await this.locator(target).fill('')
    await this.page.keyboard.type(text, {delay})
    await this.page.waitForTimeout(300)
  }

  async press(key, {settle = 700} = {}) {
    await this.page.keyboard.press(key)
    await this.page.waitForTimeout(settle)
    await this.mount()
  }

  /** Кадр текущего шага, если статья его ждёт и он ещё не снят. */
  async shot() {
    if (!this.shotWanted || this.shotTaken) return
    this.shotTaken = true
    await this._onShot(this.stepIndex)
  }
}
