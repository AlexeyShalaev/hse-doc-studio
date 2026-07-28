# tools/demo — демо-стенд, скриншоты и промо-ролик

Воспроизводимая генерация материалов сайта документации из **синтетических**
данных QA-матрицы. Всё гоняется на изолированном data dir
(`tools/demo/.build/demo/data`) — реальные данные `~/.config/hse-studio`
не затрагиваются.

Каждый материал снимается в **четырёх вариантах** — `ru/en` (язык интерфейса) ×
`light/dark` (тема): сайт показывает читателю кадр его темы и языка
(механика `#only-light/#only-dark` и файлы `*.{ru,en}.{light,dark}.*`).

```
tools/demo/
├── seed_demo.py            # изолированный стенд: копии solo-проектов матрицы (Шалаев, БПИ222)
├── run-demo.sh             # демо-backend на :17777, раздаёт собранный фронт сам (без Vite)
├── screenshots/capture.mjs # матрица экранов → docs/ru/assets/shots/<screen>.<lang>.<theme>.png
└── reel/                   # промо-ролик
    ├── gen-assets.mjs      #   фон/маска/тень «плавающего окна» под обе темы
    ├── record.mjs          #   ХОРЕОГРАФИЯ тура: сцены, титры, подписи, курсор  ← правится здесь
    └── compose.sh          #   ffmpeg → docs/ru/assets/reel/reel.<lang>.<theme>.mp4 + постеры
```

## Требования

- `uv` (backend), Node.js + pnpm (сборка фронта), **ffmpeg**;
- Docker Desktop **запущен** (иначе в кадры попадёт баннер «Docker недоступен»);
- соседний репозиторий `hse-rules-examples` рядом с `hse-doc-studio`
  (источник синтетических проектов; переопределяется `DEMO_SRC`);
- разово: `cd tools/demo && npm install && npx playwright install chromium`.

## Как запустить

Два терминала.

**Терминал 1 — демо-инстанс** (сеет стенд, поднимает backend на :17777):

```sh
make demo-up
```

**Терминал 2 — материалы:**

```sh
make shots            # матрица скриншотов → docs/ru/assets/shots/
make reel             # 4 ролика → docs/ru/assets/reel/
```

Частичные прогоны: `ONLY=workspace,checks LANGS=ru THEMES=light make shots`,
`VARIANTS=ru-dark make reel`.

## Как переделать анимацию ролика

Вся хореография — в [`reel/record.mjs`](reel/record.mjs): сцены, тексты подписей
(словарь `T`), тайминги (`sleep`), палитра директора (`D` — токены сайта).
Правки не требуют перегенерации ассетов: `node reel/record.mjs && bash reel/compose.sh`.

Анимация — `page.evaluate` + Web Animations API (работает в изолированном мире,
CSP приложения не мешает).

Захват — НЕ `recordVideo` (VP8-скринкаст Playwright «мылит» текст), а сырые
PNG-кадры через CDP `Page.startScreencast` с реальными таймстемпами →
`capture.mp4` без потерь. Темп задаёт `SPEED` в compose.sh (по умолчанию 1.5×):
паузы загрузок сжимаются, пересъёмка не нужна.

## Промежуточные файлы

`.build/` (демо-стенд, записи webm, ассеты фрейма) и `node_modules/` — в
`.gitignore`. В репозитории лежит только итог в `docs/ru/assets/{shots,reel}`.
