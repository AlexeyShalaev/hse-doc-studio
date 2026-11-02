# services/user-docs — пользовательская справка

Справка «как пользоваться Студией»: рантбуки со шагами, скриншотами и короткими роликами, ru и en.
Живёт по пути **`/help/`** на хосте самой Студии и раздаётся тем же бэкендом
(`services/api/hse_doc_studio/api/help_site.py`). В образе лежит в `/app/help`, поэтому в локальной
версии работает без сети.

Инженерная документация «как устроено и как развернуть» — это `docs/` (Zensical, GitHub Pages).
Решения и вопросы на подтверждение: [`docs/design/user-docs.md`](../../docs/design/user-docs.md).

## Кто что видит

Сайт собирается **дважды** (`scripts/build-audiences.mjs`):

| `access` | Сборка | Кто читает |
|---|---|---|
| `user` | `dist/user` и `dist/admin` | все, включая не вошедших и локальную Студию |
| `admin` | только `dist/admin` | админ установки, с host/IP, где ему открыта админка |

В сборке `user` статей администратора нет ни в навигации, ни в поиске (Pagefind), ни по адресу.
Медиа общие: `dist/media`.

## Как приложение показывает справку

Книжка в шапке, клавиша `?`, ⌘K → «Справка по этому экрану» и значки «?» у полей
(`HelpAnchor` из `@entities/help`) открывают панель (`features/help-center`). Панель читает:

- `/help/<lang>/help-map.json` — какие статьи у какого экрана (`help.routes` статей);
- `/help/<lang>/help/<ключ>.json` — статья данными: шаги, кадры под тему, ролик.

Приложение ключей статей не знает: справку экрану добавляют правкой статьи.

## Статья

`src/content/docs/<ru|en>/<раздел>/<имя>.mdx`, пара ru/en с одинаковыми шагами. Как писать —
скилл [`.claude/skills/docs-add-runbook`](../../.claude/skills/docs-add-runbook/SKILL.md).

## Медиа

`public/media/<ключ>/step-NN.<lang>.<theme>.webp`, ролики `<ключ>/clip.<lang>.<theme>.{webm,mp4}`
и постер `.webp`. Их снимает `tools/docs-studio` со стенда (`make docs-media`), руками не кладут.
Недостающий кадр не ломает ни сайт, ни панель: шаг остаётся текстом.

## Локально

```sh
pnpm install
pnpm dev                       # http://localhost:4321/help/ru/ — все статьи сразу
pnpm build                     # dist/{user,admin,media}
node scripts/check.mjs         # сверка с приложением (CI)
node scripts/check-links.mjs   # битые ссылки в собранных сайтах (CI)
```

После `pnpm build` справку отдаёт и dev-бэкенд Студии (`help_dir` по умолчанию указывает сюда),
а Vite проксирует `/help` на бэкенд: книжка в шапке работает в `make dev`.
