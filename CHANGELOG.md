# Changelog

All notable changes to this project are documented here.

Generated from `release-notes.json` via `make changelog` — do not edit by hand.
Release notes are hand-written and bilingual (RU/EN); the app shows them in the
selected interface language.

## [0.1.1](https://github.com/AlexeyShalaev/hse-doc-studio/compare/v0.1.0...v0.1.1) (2026-07-28)


### Bug Fixes

* **agent:** локализация новых инструментов в меню агента (PDF, версии, проекты, вопрос) ([4062aa4](https://github.com/AlexeyShalaev/hse-doc-studio/commit/4062aa4484f1b7ae9c29d70f33a6a34bd3d1aa71))
* **ai:** живая Ollama сама становится провайдером (синк на старте) + предложение подключить в настройках ([bb56580](https://github.com/AlexeyShalaev/hse-doc-studio/commit/bb565808ef71d907ebc5aade05bd9f06d92ac6f5))
* **deploy:** BOM в install.ps1 ломал запуск через irm | iex в Windows PowerShell 5.1 ([8ec48a1](https://github.com/AlexeyShalaev/hse-doc-studio/commit/8ec48a199f0c06d594da6c0f122be2c2bd07d8c1))
* **deploy:** инсталляторы говорят по-английски, HSE_STUDIO_LANG=ru включает русский; дока подставляет флаг по языку страницы ([6f45549](https://github.com/AlexeyShalaev/hse-doc-studio/commit/6f45549dfbcf171b8657df97b42fa1a802a79c71))
* **setup:** каталог данных получает готовую папку projects, мастер проектов предлагает её чипом ([7f98d50](https://github.com/AlexeyShalaev/hse-doc-studio/commit/7f98d507dfe4220c2349f52729596e3356a91c70))
* правки 0.1.1 по итогам живого тестирования ([ab7e679](https://github.com/AlexeyShalaev/hse-doc-studio/commit/ab7e679e43f08b1fe1f4b9f984e4da9841ec4867))

## 0.1.0 - 2026-07-28

- First release: a local studio for academic documents — projects from templates (thesis, coursework, Project Proposal) with every accompanying document and presentation
- One-click PDF builds: LaTeX runs inside a Docker container, nothing to install on your machine
- Code and visual editors with a built-in PDF viewer and text↔layout jumps (SyncTeX)
- GOST formatting checks: findings are anchored to source lines, many fix themselves automatically
- Submissions: the studio assembles the checkpoint package together with signatures and forms
- An AI assistant inside your project: bring your own provider (Claude, OpenAI and compatibles) or a local model via Ollama
- Project version history: timeline, diffs and restore — no git knowledge required
