// @ts-check
import {existsSync, readFileSync, readdirSync} from 'node:fs'
import {join} from 'node:path'

import {defineConfig} from 'astro/config'
import starlight from '@astrojs/starlight'

/**
 * Справка HSE Doc Studio: «как пользоваться», а не «как устроено» (то — docs/, Zensical).
 *
 * Живёт по пути /help/ на хосте самой Студии и раздаётся тем же процессом, что и интерфейс
 * (services/api, `help_dir`): один origin значит ноль CORS, общий localStorage (тема) и работу
 * без сети в локальной версии, где справка просто лежит в образе.
 *
 * Сайт собирается по разу на аудиторию (scripts/build-audiences.mjs): в сборке `user` статей
 * администратора физически нет, ни в навигации, ни в индексе поиска. Какую сборку отдать, решает
 * сервер по сессии.
 */
const srcDir = process.env.DOCS_SRC_DIR ?? './src'
const outDir = process.env.DOCS_OUT_DIR ?? './dist'

const LABELS = {
  start: {ru: 'Начало', en: 'Getting started'},
  runbooks: {ru: 'Как сделать', en: 'How to'},
  admin: {ru: 'Администратору', en: 'Administration'},
}

/** Боковое меню из файлов, которые есть в ЭТОЙ сборке (autogenerate Starlight не знает про аудитории). */
const group = (directory) => {
  const dir = join(srcDir, 'content/docs/ru', directory)
  if (!existsSync(dir)) return []
  const items = readdirSync(dir)
    .filter((file) => /\.mdx?$/.test(file))
    .map((file) => {
      const read = (lang) => {
        const path = join(srcDir, 'content/docs', lang, directory, file)
        return existsSync(path) ? (readFileSync(path, 'utf-8').split('---')[1] ?? '') : ''
      }
      const title = (fm) => /^title:\s*(?:'([^']*)'|"([^"]*)"|(.+))$/m.exec(fm)?.slice(1).find(Boolean)?.trim()
      const ru = read('ru')
      const en = read('en')
      return {
        label: title(ru) ?? file,
        translations: {en: title(en) ?? title(ru) ?? file},
        slug: `${directory}/${file.replace(/\.mdx?$/, '')}`,
        order: Number(/order:\s*(\d+)/.exec(ru)?.[1] ?? 999),
      }
    })
    .sort((a, b) => a.order - b.order || a.label.localeCompare(b.label, 'ru'))
  if (!items.length) return []
  return [
    {
      label: LABELS[directory].ru,
      translations: {en: LABELS[directory].en},
      items: items.map(({label, translations, slug}) => ({label, translations, slug})),
    },
  ]
}

export default defineConfig({
  site: 'https://studio.local',
  base: '/help',
  trailingSlash: 'always',
  srcDir,
  outDir,
  integrations: [
    starlight({
      title: {ru: 'Справка HSE Studio', en: 'HSE Studio Help'},
      description: 'Как пользоваться HSE Doc Studio: пошаговые инструкции со скриншотами и короткими роликами.',
      defaultLocale: 'ru',
      locales: {
        ru: {label: 'Русский', lang: 'ru'},
        en: {label: 'English', lang: 'en'},
      },
      logo: {src: './src/assets/logo.svg'},
      components: {
        Footer: './src/components/DocFooter.astro',
        ThemeProvider: './src/components/ThemeProvider.astro',
        SocialIcons: './src/components/BackToApp.astro',
      },
      customCss: ['./src/styles/custom.css'],
      pagination: false,
      lastUpdated: false,
      sidebar: [...group('start'), ...group('runbooks'), ...group('admin')],
      social: [],
    }),
  ],
})
