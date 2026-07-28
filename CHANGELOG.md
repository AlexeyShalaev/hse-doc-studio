# Changelog

All notable changes to this project are documented here.

Generated from `release-notes.json` via `make changelog` — do not edit by hand.
Release notes are hand-written and bilingual (RU/EN); the app shows them in the
selected interface language.

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
