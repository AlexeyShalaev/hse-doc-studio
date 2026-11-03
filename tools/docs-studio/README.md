# tools/docs-studio — стенды и съёмка медиа справки

Скриншоты и ролики `services/user-docs` **снимаются сценарием**, а не руками: у шага статьи есть
`shot`, у статьи `video`, у статьи есть сценарий в `record/scenarios/<ключ>.mjs`.

```sh
make docs-media                                  # всё: свежие интерфейс и справка, оба стенда, съёмка
make docs-media SCENARIO="runbooks/build admin/runners"
make docs-stand-local                            # только локальный стенд
LANGS=ru THEMES=dark make docs-record SCENARIO=runbooks/build   # один вариант, стенды уже подняты
```

## Стенды

| Стенд | Адрес | Что там |
|---|---|---|
| локальный (`stand/local.sh`) | http://127.0.0.1:17790 | Студия в режиме local на изолированном каталоге `.build/local/data`; проекты в `~/Documents/hse-studio-docs` (путь виден в кадрах). Сид (`record/lib/stands.mjs`) создаёт через API русскую и английскую ВКР и собирает тезис (Docker + TeX Live). |
| серверный (`stand/server.sh`) | http://localhost:8110 | compose стенда server-lite (`scripts/dev/server-lite`) под проектом `hse-doc-studio-docs`: образ из текущих исходников в режиме server, Postgres, админ и три демо-пользователя. Секреты в `.build/server.env`. |

Реальные данные (`~/.config/hse-studio`) не затрагиваются. `stand/local.sh reset`,
`stand/server.sh reset` стирают стенды.

## Сценарий

```js
export default {
  stand: 'local',                // или 'server' + persona: 'admin' | 'anna' | 'victor'
  start: (w) => `/projects/${w.local.projects[w.lang].id}/documents/thesis`,
  steps: [async (d) => d.click('#document-tab-compile'), /* … столько же, сколько help.steps */],
}
```

`d.click` подводит курсор, обводит элемент, снимает кадр шага (если у шага есть `shot`) и
нажимает; `d.point` обводит и снимает без нажатия; шаг без кадра в сценарии снимается в конце.
`d.s(ns, key)` — строка интерфейса из словарей приложения на языке дубля, `d.t(ru, en)` — своя.

Каждый вариант (ru/en × light/dark) идёт с нуля в новом контексте браузера 1280×800 @2x:
тема и язык ставятся в `localStorage` до загрузки приложения.

## Выход

- кадр шага: PNG → WebP 1600 px, q80 (`lib/media.mjs`);
- ролик: CDP-скринкаст с реальными отметками времени (не `recordVideo`, он мылит текст),
  паузы длиннее 2,5 с сжимаются; MP4 H.264, 1280 px, 24 fps; постер WebP;
- при ошибке кадр экрана: `.build/record/fail-*.png`.

Требования: Docker запущен, `uv`, Node 24 + pnpm, ffmpeg с libx264. Chromium ставит
`make docs-record` (`playwright install chromium`).

## В CI

`.github/workflows/user-docs-media.yml`: вручную и раз в неделю, не required; медиа приходит
артефактом. Сборку и проверки справки делает обычный CI (`ci.yml`, джоб `user-docs`).
