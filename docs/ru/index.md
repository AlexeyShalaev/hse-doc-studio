---
title: HSE Doc Studio
description: "Локальная студия учебных документов: ВКР и курсовые по ГОСТ — шаблоны, сборка LaTeX, нормоконтроль и упаковка сдачи. Без облака и аккаунтов."
hide:
  - navigation
  - toc
render_macros: true
hero:
  eyebrow: "Локально · Docker · ваши файлы"
  title: "От пустой формы — до подписанного PDF."
  lede: "HSE Doc Studio собирает вашу ВКР или курсовую целиком: шаблоны всех документов, сборка LaTeX в контейнере, нормоконтроль по ГОСТ и упаковка пакета сдачи — на вашем компьютере, без облака и аккаунтов."
  actions:
    - text: "Установить за одну команду →"
      href: "start/install/"
      kind: primary
    - text: "Первый проект →"
      href: "start/first-project/"
      kind: ghost
  install: "curl -fsSL https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/install.sh | HSE_STUDIO_LANG=ru sh"
  install_ps: "$env:HSE_STUDIO_LANG='ru'; irm https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/install.ps1 | iex"
  fine: "Apache-2.0 · linux/amd64 и arm64 · единственное требование — установленный и запущенный Docker."
  sheet:
    title: "Пакет сдачи · ВКР"
    stamp: "Проверено · нормоконтроль"
    items:
      - { code: "ТЗ", tone: "st1", name: "Техническое задание", done: true }
      - { code: "ПЗ", tone: "st2", name: "Пояснительная записка", done: true }
      - { code: "ПМИ", tone: "st3", name: "Программа и методика испытаний", done: true }
      - { code: "РП", tone: "st4", name: "Руководство программиста", done: true }
      - { code: "През", tone: "stsub", name: "Презентация к защите", done: false }
      - { code: "ВКР", tone: "st5", name: "Текст работы", done: false }
---

# HSE Doc Studio { .hds-visually-hidden }

<p class="hds-eyebrow" style="text-align:center; margin-top:2.5rem">Что уже описано в паке шаблонов</p>

{{ pack_stats_strip('ru') }}

<div class="hds-reel hds-wide">
  <video class="hds-only-light" src="assets/reel/reel.ru.light.mp4" poster="assets/reel/reel-poster.ru.light.png" autoplay muted loop playsinline></video>
  <video class="hds-only-dark" src="assets/reel/reel.ru.dark.mp4" poster="assets/reel/reel-poster.ru.dark.png" autoplay muted loop playsinline></video>
</div>

## Слева — исходник. Справа — то, что примут.

<p class="hds-lede">Режим «Рядом»: визуальный редактор и готовый PDF на одном экране. Ctrl+клик работает в обе стороны — из PDF в строку исходника и обратно.</p>

<figure class="hds-fig hds-wide">
  <div class="hds-shot">
    <div class="hds-shot__bar">
      <span class="hds-shot__brand">HSE DOC STUDIO</span>
      <span class="hds-shot__route">/projects/vkr/documents/thesis</span>
    </div>
    <img src="assets/shots/workspace.ru.light.png#only-light" alt="Режим «Рядом»: PDF и визуальный редактор">
    <img src="assets/shots/workspace.ru.dark.png#only-dark" alt="Режим «Рядом»: PDF и визуальный редактор">
  </div>
  <figcaption>режим «Рядом»: превью PDF и визуальный редактор бок о бок</figcaption>
</figure>

- **Поля <span class="hds-fill">\hseFill</span> подсвечены** — ++tab++ ведёт к следующему незаполненному.
- **«Поля по ГОСТ»** — направляющие 30/15/20/20 мм прямо поверх страницы PDF.
- **Счёт слов и страниц** — обновляется при каждой сборке.

## Один проект. Одни метаданные. Все документы.

<p class="hds-lede">Поменяли степень руководителя в настройках — при следующей сборке она поменялась на всех титульных листах сразу. ТЗ, ПМИ, руководства, презентации и сама работа собираются из одного проекта; курсовой и Project Proposal — так же, из своих шаблонов.</p>

<p style="text-align:center"><a href="reference/pack/">Как устроены пак, шаблоны и документы →</a></p>

## Замечания приходят на поля, а не в почту.

<p class="hds-lede">Проверяется то, что реально собралось — готовый PDF и лог сборки, а не догадки по исходнику.</p>

<div class="hds-finding hds-finding--err">
  <div class="hds-finding__rule">gost-7.32-2017/page-margins</div>
  <div class="hds-finding__msg">Поле слева 25 мм, требуется 30 мм.</div>
  <div class="hds-finding__loc">thesis/thesis.tex · стр. 1</div>
</div>
<div class="hds-finding hds-finding--warn">
  <div class="hds-finding__rule">gost-19.201-78/section-stages</div>
  <div class="hds-finding__msg">В ТЗ отсутствует раздел «Стадии и этапы разработки».</div>
  <div class="hds-finding__loc">документ целиком</div>
</div>
<div class="hds-finding hds-finding--info">
  <div class="hds-finding__rule">typography-ru/quotes</div>
  <div class="hds-finding__msg">Прямые кавычки "…" вместо «ёлочек».</div>
  <div class="hds-finding__loc">thesis/thesis.tex · строка 214</div>
</div>

Правила приходят из ГОСТов ЕСПД и ГОСТ 7.32-2017, русской типографики и LanguageTool. [Как устроен нормоконтроль →](reference/checks-rules.md)

## Ассистент, который читает ваш лог сборки, а не гадает.

<p class="hds-lede">«Починить с ИИ» на упавшей сборке: агент читает лог, правит <code>.tex</code> и пересобирает. Каждая запись на диск подтверждается вами.</p>

Провайдер — Anthropic, OpenAI, любой OpenAI-совместимый или локальная Ollama: в последнем случае текст работы не покидает машину. [Подробнее про агента →](workbench/agent.md)

## Всё — локально

<div class="hds-wide" style="display:grid; grid-template-columns:repeat(auto-fit,minmax(16rem,1fr)); gap:2rem; margin-top:1.5rem">
  <div>
    <h4 style="margin:0">Файлы — ваши</h4>
    <p style="font-size:.9rem">Проект — обычная папка с <code>.tex</code> на вашем диске. Правите её в VS Code — Студия заметит и предложит сравнить.</p>
  </div>
  <div>
    <h4 style="margin:0">Ни базы, ни облака, ни аккаунта</h4>
    <p style="font-size:.9rem">Всё состояние — файлы в выбранной вами папке, её достаточно бэкапить. <a href="reference/privacy/">Что уходит в сеть →</a></p>
  </div>
  <div>
    <h4 style="margin:0">История на всякий случай</h4>
    <p style="font-size:.9rem">Каждая правка и сборка попадают в отдельный git внутри <code>.hse-studio/git/</code>. Вернуться к «главе 3, которая работала» — одна кнопка.</p>
  </div>
</div>

## Одна команда. Дальше приложение спросит, где хранить работы.

<p class="hds-lede">Скрипт проверяет, что Docker отвечает, скачивает образ и открывает браузер; повторный запуск ничего не ломает.</p>

=== "Скрипт (macOS / Linux)"

    ```sh
    --8<-- "install-sh.txt"
    ```

=== "PowerShell (Windows)"

    ```powershell
    --8<-- "install-ps1.txt"
    ```

=== "Docker Compose"

    ```sh
    --8<-- "install-compose.txt"
    ```

Разбор каждого флага, оверлеи Compose и ручной `docker run` — в разделе [Установка](start/install.md).

## Готовы начать?

<div style="display:flex; flex-wrap:wrap; gap:.8rem; justify-content:center; margin:1.5rem 0 2rem">
  <a class="hds-btn" href="start/install/">Установить →</a>
  <a class="hds-btn hds-btn--ghost" href="start/first-project/">Первый проект</a>
</div>
