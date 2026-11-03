---
name: docs-add-runbook
description: Написать или обновить статью пользовательской справки (services/user-docs) — рантбук ru/en со шагами, привязка к экрану приложения (help.routes), значок «?» у поля, сценарий съёмки скриншотов и ролика (tools/docs-studio) и проверки.
---

# Skill: рантбук пользовательской справки

Справка «как пользоваться» живёт в `services/user-docs` (Astro Starlight, ru/en) и открывается
по `/help/` на хосте Студии и из самого приложения: меню «Справка» в шапке, клавиша `?`, ⌘K → «Справка по
этому экрану», значки «?» у полей. Инженерная документация «как устроено» — это `docs/` (Zensical),
её не трогаем.

## Когда

- появился пользовательский сценарий или экран;
- экран изменился, и статья описывает уже не то (`verified.sources` поменялись после `verified.at`);
- в приложении у сложного поля нужен значок «?».

## Шаг 1. Понять, что на экране на самом деле

1. Точные надписи берите из словарей `services/web-app/src/shared/lib/i18n/locales/{ru,en}/*.json`
   (админка: `locales/{ru,en}/admin/*.json`). Человек ищет глазами строку интерфейса.
2. Порядок кликов — из страницы и её features (`services/web-app/src/pages`, `features`, `widgets`).
   Не выдумывайте кнопки; ограничения экрана (ошибки, блокировки) — часть инструкции.
3. Маршрут экрана — из `services/web-app/src/app/router.tsx` или разделов `pages/AdminPage/AdminApp.tsx`.

## Шаг 2. Файлы статьи

Ключ статьи = путь без языка: `runbooks/<имя>` (пользователь), `admin/<имя>` (администратор),
`start/<имя>`. Два файла с одинаковым числом шагов и одинаковыми `shot`/`video`:
`src/content/docs/ru/<ключ>.mdx` и `src/content/docs/en/<ключ>.mdx`. Образец —
`runbooks/create-project.mdx`.

```mdx
---
title: 'Синхронизировать с git'
description: 'Одна строка: идёт в поиск и в карточку.'
sidebar:
  order: 7
access: user                    # user | admin. admin/ — только admin. Статьи admin нет в сборке user.
help:
  routes: ['/projects/:projectId/sync/conflicts', '/projects/:projectId/project-settings/sync']
  summary: 'Одно предложение над шагами в панели справки.'
  steps:
    - text: 'Откройте **Настройки проекта** → **Синхронизация**.'
      hint: 'Необязательная оговорка.'
      shot: runbooks/git-sync/step-01       # кадр: <ключ>/step-NN, NN = номер шага
  video:
    src: runbooks/git-sync/clip             # необязательно
verified:
  at: 2026-11-03                            # день, когда шаги пройдены в живом интерфейсе
  app_version: '0.3.0'
  sources:                                  # что сделает статью подозрительной
    - services/web-app/src/features/git-sync
---

import Steps from '~/components/Steps.astro'
import Video from '~/components/Video.astro'

Абзац: зачем это и что получится.

<Video />

<Steps />

## Если что-то пошло не так
```

Правила:

- **Все строки frontmatter в одинарных кавычках**: `: ` внутри голой строки ломает YAML.
- В `text`/`hint` только `**жирный**`, `*курсив*`, `` `код` `` и `[ссылки](/help/ru/<ключ>/)`:
  ровно это рисует панель в приложении (`features/help-center/lib/inlineMarkdown.tsx`).
- `help.routes` — шаблоны путей react-router; можно с вкладкой (`...?tab=checks`) или конкретным
  разделом (`/settings/providers`). Маршрут, стоящий у статьи первым, значит «статья про этот экран».
  Приложение ключей статей не знает: карта `help-map.json` строится из этих полей.
- Медиа руками не кладут: их снимает сценарий (шаг 4). До съёмки статья работает без картинок.
- Статья пользователя не ссылается на статьи `admin/`: в сборке `user` такая ссылка битая, и
  `check-links.mjs` это поймает.

## Шаг 3. Значок «?» у сложного поля (по желанию)

```tsx
import { HelpAnchor } from "@entities/help";

<label>
  {t("remote.urlLabel")}
  <HelpAnchor article="runbooks/git-sync" step={3} />
</label>
```

`step` — номер шага с единицы: панель прокрутит к нему и подсветит. Значок можно ставить в
features, widgets и pages (это entity).

## Шаг 4. Сценарий съёмки

`tools/docs-studio/record/scenarios/<ключ>.mjs`, ровно столько функций в `steps`, сколько шагов
в статье (рекордер сверяет):

```js
export default {
  stand: 'local',                    // 'local' (:17790, засеянные ВКР) или 'server' (server-lite :8110)
  persona: null,                     // для server: 'admin' | 'anna' | 'victor'
  start: (w) => `/projects/${w.local.projects[w.lang].id}/documents/thesis`,
  steps: [
    async (d) => d.click(d.role('button', d.t('Синхронизировать', 'Sync'))),
    async (d) => d.point(d.text(d.t('Конфликт', 'Conflict'))),   // обвести без клика
  ],
}
```

`d.click` подводит курсор, обводит элемент, снимает кадр шага (если у шага есть `shot`) и
нажимает; `d.point` только обводит и снимает; шаг без нажатия снимается в конце. Селекторы — по
ролям и строкам интерфейса через `d.t(ru, en)`.

Запуск:

```sh
make docs-stand-local                  # и/или make docs-stand-server
make docs-record SCENARIO=runbooks/git-sync          # ru/en × light/dark
LANGS=ru THEMES=dark make docs-record SCENARIO=...    # быстрый прогон одного варианта
make docs-media                        # всё одной командой: стенды, съёмка, остановка
```

Выход: `services/user-docs/public/media/<shot>.<lang>.<theme>.webp`, ролик
`<src>.<lang>.<theme>.mp4` и постер `.webp`. При ошибке кадр экрана лежит в
`tools/docs-studio/.build/record/fail-*.png`.

## Шаг 5. Проверить

```sh
make user-docs-check      # маршруты, sources, пары ru/en, сборка user/admin, битые ссылки
CHECK_MEDIA=1 node services/user-docs/scripts/check.mjs   # все кадры и ролики на месте
```

## Частые ошибки

- Свои названия кнопок вместо строк интерфейса.
- Пересказ архитектуры вместо инструкции.
- `verified.at` без реального прохода по экрану.
- Шаг в ru есть, в en нет (или кадры у шагов разные): `check.mjs` падает.
