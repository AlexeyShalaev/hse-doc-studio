// Съёмка медиа справки: один сценарий = одна статья services/user-docs.
//
//   node run.mjs [ключ …]          # например runbooks/create-project admin/runners; без ключей — все
//   LANGS=ru THEMES=dark node run.mjs runbooks/build
//
// Для каждого варианта (язык интерфейса × тема) дубль идёт с нуля в новом контексте браузера:
// кадры шагов → public/media/<shot>.<lang>.<theme>.webp, ролик (если у статьи есть video) →
// <src>.<lang>.<theme>.{webm,mp4} и постер .webp. Число функций-шагов сценария обязано
// совпадать с help.steps статьи: рекордер сверяет.
import {chromium} from 'playwright'
import {existsSync, readFileSync, readdirSync, statSync} from 'node:fs'
import {mkdir, rm} from 'node:fs/promises'
import {dirname, join, relative, resolve} from 'node:path'
import {parse} from 'yaml'

import {mark, posterPng, startCapture, stopCapture} from './lib/capture.mjs'
import {Director} from './lib/director.mjs'
import {saveShot} from './lib/media.mjs'
import {LOCAL_BASE, SERVER_BASE, seedLocal, serverPersonas, signIn, waitFor} from './lib/stands.mjs'

const HERE = import.meta.dirname
const ROOT = resolve(HERE, '../../..')
const DOCS = join(ROOT, 'services/user-docs/src/content/docs/ru')
const MEDIA = join(ROOT, 'services/user-docs/public/media')
const BUILD = join(HERE, '../.build/record')
const LANGS = (process.env.LANGS ?? 'ru,en').split(',')
const THEMES = (process.env.THEMES ?? 'light,dark').split(',')
const VIEWPORT = {width: 1280, height: 800}
const SCALE = 2
const NO_VIDEO = process.env.NO_VIDEO === '1'

const walk = (dir) => readdirSync(dir).flatMap((e) => (statSync(join(dir, e)).isDirectory() ? walk(join(dir, e)) : [join(dir, e)]))
const scenarioKeys = walk(join(HERE, 'scenarios'))
  .filter((f) => f.endsWith('.mjs'))
  .map((f) => relative(join(HERE, 'scenarios'), f).replace(/\.mjs$/, ''))
  .sort()

const wanted = process.argv.slice(2)
const keys = wanted.length ? wanted : scenarioKeys
const unknown = keys.filter((k) => !scenarioKeys.includes(k))
if (unknown.length) throw new Error(`нет сценария: ${unknown.join(', ')} (есть: ${scenarioKeys.join(', ')})`)

const articleOf = (key) => {
  const file = [join(DOCS, `${key}.mdx`), join(DOCS, `${key}.md`)].find(existsSync)
  if (!file) throw new Error(`нет статьи ${key}`)
  return parse(readFileSync(file, 'utf-8').split(/^---$/m)[1])
}

const browser = await chromium.launch({args: ['--hide-scrollbars', '--font-render-hinting=none']})
let local = null
let failures = 0

for (const key of keys) {
  const scenario = (await import(join(HERE, 'scenarios', `${key}.mjs`))).default
  const article = articleOf(key)
  const steps = article.help?.steps ?? []
  if (scenario.steps.length !== steps.length) {
    throw new Error(`${key}: в сценарии ${scenario.steps.length} шаг(ов), в статье ${steps.length}`)
  }
  const base = scenario.stand === 'server' ? SERVER_BASE : LOCAL_BASE
  if (scenario.stand === 'server') await waitFor(SERVER_BASE)
  else local ??= await seedLocal()

  for (const lang of LANGS) {
    for (const theme of THEMES) {
      const variant = `${key} ${lang}/${theme}`
      const context = await browser.newContext({
        viewport: VIEWPORT,
        deviceScaleFactor: SCALE,
        colorScheme: theme,
        locale: lang === 'ru' ? 'ru-RU' : 'en-US',
        reducedMotion: 'no-preference',
      })
      // Тема и язык до загрузки приложения: загрузочный скрипт index.html читает их синхронно.
      await context.addInitScript(
        ([theme, lang]) => {
          try {
            localStorage.setItem('hse-studio-theme', JSON.stringify({state: {theme, density: 'comfortable', lang}, version: 0}))
            localStorage.setItem('hse-studio-onboarding', JSON.stringify({state: {dismissed: true}, version: 0}))
          } catch {}
        },
        [theme, lang],
      )
      const world = {key, lang, theme, baseUrl: base, local, personas: scenario.stand === 'server' ? serverPersonas() : null}
      if (scenario.stand === 'server' && scenario.persona) {
        await signIn(context, world.personas[scenario.persona])
        // Проекты персоны: id в адресах экранов знает только стенд.
        const listed = await (await context.request.get(`${SERVER_BASE}/api/v1/projects?limit=100`)).json()
        world.projects = Array.isArray(listed) ? listed : listed.items ?? []
      }
      const page = await context.newPage()
      const d = new Director(page, world, {
        onShot: async (index) => {
          const shot = steps[index].shot
          const png = await page.screenshot()
          await saveShot(png, join(MEDIA, `${shot}.${lang}.${theme}.webp`))
        },
      })
      try {
        if (scenario.prepare) await scenario.prepare(world)
        await d.goto(typeof scenario.start === 'function' ? scenario.start(world) : scenario.start)
        const video = article.help.video && !NO_VIDEO ? article.help.video.src : null
        const capture = video ? await startCapture(page, join(BUILD, 'frames'), {...VIEWPORT, scale: 1}) : null
        if (capture) await d.pause(600)
        for (let i = 0; i < scenario.steps.length; i++) {
          d.stepIndex = i
          d.shotWanted = Boolean(steps[i].shot)
          d.shotTaken = false
          if (capture) mark(capture)
          await scenario.steps[i](d, world)
          // Шаг ничего не нажал, а кадр ему нужен: снимаем итог шага.
          await d.shot()
        }
        if (capture) {
          await d.pause(800)
          const out = join(MEDIA, `${video}.${lang}.${theme}`)
          await mkdir(dirname(out), {recursive: true})
          const result = await stopCapture(capture, {base: out, width: VIEWPORT.width})
          const png = join(BUILD, 'poster.png')
          await posterPng(`${out}.mp4`, png, Math.min(1.0, result.seconds / 2))
          await saveShot(readFileSync(png), `${out}.webp`)
          await rm(png, {force: true})
          console.log(`  ролик ${variant}: ${result.seconds.toFixed(1)} с`)
        }
        console.log(`снято ${variant}`)
      } catch (error) {
        failures++
        await mkdir(BUILD, {recursive: true})
        await page.screenshot({path: join(BUILD, `fail-${key.replaceAll('/', '_')}-${lang}-${theme}.png`)}).catch(() => {})
        console.error(`ОШИБКА ${variant}: ${String(error?.message ?? error).split('\n')[0]}`)
      } finally {
        if (scenario.cleanup) await scenario.cleanup(world).catch((e) => console.error(`  уборка ${variant}: ${e.message}`))
        await context.close()
      }
    }
  }
}

await browser.close()
if (failures) {
  console.error(`дублей с ошибкой: ${failures} (кадры ошибок в tools/docs-studio/.build/record)`)
  process.exit(1)
}
console.log('съёмка завершена; проверка: make user-docs-check')
