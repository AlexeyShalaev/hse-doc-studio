# Changelog

All notable changes to this project are documented here.

Generated from `release-notes.json` via `make changelog` — do not edit by hand.
Release notes are hand-written and bilingual (RU/EN); the app shows them in the
selected interface language.

## [0.2.0](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.1.3...v0.2.0) (2026-10-26)


### Features

* **catalog:** подсказка в поле «Группа» задаётся паком (author_group_placeholder) ([df21c76](https://github.com/AlexeyShalaev/hse-doc-studio/commit/df21c7654384037c2299c11a051ec304f76fe3c2))
* **packs:** неизменные выпущенные версии шаблонов и совместимость данных проекта между Студиями ([67eb5e4](https://github.com/AlexeyShalaev/hse-doc-studio/commit/67eb5e493756ec46bd6883198f499d8d458fe04a))
* **packs:** пак hse-cs-sse — курсовой проект 1 курса магистратуры СПИ ([cb52ef0](https://github.com/AlexeyShalaev/hse-doc-studio/commit/cb52ef0201a3f9a8ea6e6ef70c9e202f06572daa))
* **packs:** пак магистратуры СПИ — курсовой проект 1 курса ([7c3b3c2](https://github.com/AlexeyShalaev/hse-doc-studio/commit/7c3b3c20ade0d8b0d0ca2b2cd9b8fce8e8796c8b))
* **signatures:** открепленные электронные подписи - фиксация PDF, OpenPGP, CMS/ГОСТ, плашка, КриптоПро ([a7781d1](https://github.com/AlexeyShalaev/hse-doc-studio/commit/a7781d1ec34b35e4c9f475ab2fe4d3cf4d756a9e))
* **signatures:** открепленные ЭП на бэкенде - фиксация PDF, OpenPGP и CMS/ГОСТ, пакет сдачи ([7319efb](https://github.com/AlexeyShalaev/hse-doc-studio/commit/7319efbe092dd718cf32b410db332cd1a6022e09))
* **signatures:** плашка подписи как у ВШЭ - сертификат, владелец, срок, дата; подписант из сертификата или ключа, контроль совпадения и устаревания ([d676efb](https://github.com/AlexeyShalaev/hse-doc-studio/commit/d676efb3ab08318525a829c5a5057ff9ddff8857))
* **signatures:** подпись УКЭП через КриптоПро ЭЦП Browser plug-in, достройка цепочки УЦ по AIA, доверие корню, подсказка уровня по политике КС ([1a1db0d](https://github.com/AlexeyShalaev/hse-doc-studio/commit/1a1db0d0ecf7226ce7dd99b2285219865f1cf9e5))
* **signatures:** уровень подписи (усиленная квалифицированная / неквалифицированная) второй строкой заголовка плашки ([e4b46cd](https://github.com/AlexeyShalaev/hse-doc-studio/commit/e4b46cd9832cdc80ebcb918df910f01ae172ff0c))
* **template-update:** обновление проекта на новую версию шаблона с трёхсторонним слиянием ([69bb937](https://github.com/AlexeyShalaev/hse-doc-studio/commit/69bb937789c4a88714ce43b14abc211b986a4f3a))
* **template-update:** обновление проектов на новую версию шаблона ([4690ec9](https://github.com/AlexeyShalaev/hse-doc-studio/commit/4690ec95f4c82082d469782b213599aee7d1c887))
* **web-app:** версия шаблона в настройках проекта, предпросмотр и отмена обновления, баннер «только чтение» ([7284126](https://github.com/AlexeyShalaev/hse-doc-studio/commit/728412687a6450093ab0e2965b84368914ccbbb4))
* **web-app:** группа документов «Тема и заявка» и имя академрука в слоте подписи ([8de68d7](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8de68d74299f8418c5c1283a2f35aea7c8bc2dfc))
* **web-app:** открепленные ЭП в интерфейсе - фиксация PDF, загрузка и подпись в Студии, ключи OpenPGP, доверенные корни ([b37302c](https://github.com/AlexeyShalaev/hse-doc-studio/commit/b37302cbb143b0775dad718930d2b59a1a41eecb))
* **web-app:** подписант плашки - сертификат, ключ, вручную; превью плашки и предупреждения ([0e63a63](https://github.com/AlexeyShalaev/hse-doc-studio/commit/0e63a630ad0b39ae34ab31af9e7005c3ca52e38a))
* **web-app:** сигналы об обновлении шаблона ([4e16a00](https://github.com/AlexeyShalaev/hse-doc-studio/commit/4e16a001539f0bb2c4937a03199e0871b717b2ec))
* **web-app:** сигналы об обновлении шаблона - бейдж на «Настройках проекта», точка в оглавлении, строка состояния, уведомление при открытии ([eabd434](https://github.com/AlexeyShalaev/hse-doc-studio/commit/eabd434a019521f6486845f01cbb63cc8e200e8e))


### Bug Fixes

* **deps:** Anthropic SDK 2 и OpenAI SDK 3 на httpx2, pdfjs 6.4 без convertToViewportRectangle, чистый uv.lock ([0c6e795](https://github.com/AlexeyShalaev/hse-doc-studio/commit/0c6e7955f809e6aa47a929e48156c212b16e832e))
* **deps:** закрыты HIGH/CRITICAL из скана образа; OpenPGP-тесты не гоняются на Windows ([4c991da](https://github.com/AlexeyShalaev/hse-doc-studio/commit/4c991da47be261510b87fb7f87d0e16a66966145))
* **hse-cs-sse:** в заявке на проект у студента только ФИО, без группы ([19b33ec](https://github.com/AlexeyShalaev/hse-doc-studio/commit/19b33ecba5cca6a487b2ac2cf9da5c650133ed72))
* **hse-cs-sse:** весь текст черный - заголовки, ссылки и колонтитул заявки, ссылки отчета ([6a1dce8](https://github.com/AlexeyShalaev/hse-doc-studio/commit/6a1dce800266bf339a9a56e962f5d3878d2a0652))
* **packs:** титульный слайд КП СПИ — обе темы влезают в окно, вторая на другом языке ([0058d07](https://github.com/AlexeyShalaev/hse-doc-studio/commit/0058d07452f8e570b702eff6435f8c3ac4576557))
* **signatures:** кривые КриптоПро XchA/XchB - алиасы CryptoPro-A/C, настоящая УКЭП ВШЭ проверяется ([0193ca9](https://github.com/AlexeyShalaev/hse-doc-studio/commit/0193ca913aeccfa8823d036c7daa464bd17e8aff))
* **signatures:** при загрузке открытого ключа к подписи принимается только PUBLIC KEY BLOCK ([dc90fe1](https://github.com/AlexeyShalaev/hse-doc-studio/commit/dc90fe15844fe8821310035071faa812992a9561))
* **web-app:** размер зафиксированного PDF в КБ, у OpenPGP не дублируется алгоритм ([a4a4792](https://github.com/AlexeyShalaev/hse-doc-studio/commit/a4a4792078a900a460f37701d92d1cd9b2bd7661))

## [0.1.3](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.1.2...v0.1.3) - 2026-07-28

- The AI agent now works with any local model: if a model lacks tool support (e.g. phi3.5), it switches to a text protocol and keeps answering
- Agent errors are no longer lost — the failure reason shows up right in the chat
- Terminal updates: the update.sh and update.ps1 scripts run the same updater as the Update button — settings preserved, automatic rollback on failure
- Docs site polish: the banner always announces the current release; fixed the What's-new link, tab underline and buttons

## [0.1.2](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.1.1...v0.1.2) - 2026-07-28

- Fixed the app-error crash on the AI agent's very first reply (a duplicate router instance after a dependency update)
- The error screen now has a “Report an issue” button: it opens GitHub with the error, stack trace and version pre-filled — just add what you were doing

## [0.1.1](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.1.0...v0.1.1) - 2026-07-28

- The one-command install now also works in stock Windows PowerShell 5.1
- Install scripts speak English by default and Russian with HSE_STUDIO_LANG=ru; the docs pick the flag to match the page language
- A running local Ollama now registers itself as a provider — no more manual setup; the settings offer a one-click connect as well
- Every AI-agent tool is now translated in the tools menu: PDF reading, versions, projects, ask-the-user
- The data folder now ships with a ready-made projects directory — the project wizard suggests it right away

## 0.1.0 - 2026-07-28

- First release: a local studio for academic documents — projects from templates (thesis, coursework, Project Proposal) with every accompanying document and presentation
- One-click PDF builds: LaTeX runs inside a Docker container, nothing to install on your machine
- Code and visual editors with a built-in PDF viewer and text↔layout jumps (SyncTeX)
- GOST formatting checks: findings are anchored to source lines, many fix themselves automatically
- Submissions: the studio assembles the checkpoint package together with signatures and forms
- An AI assistant inside your project: bring your own provider (Claude, OpenAI and compatibles) or a local model via Ollama
- Project version history: timeline, diffs and restore — no git knowledge required
