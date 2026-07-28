# HSE Doc Studio

Локальный инструмент для подготовки и оформления учебных документов НИУ ВШЭ (ВКР, курсовая, Project Proposal, презентация и сопутствующие документы по ЕСПД). Требования конкретной образовательной программы задаются паком шаблонов — сейчас в комплекте `hse-cs-se` (ФКН, ОП «Программная инженерия»). Работает поверх файловой системы — без облака и БД; LaTeX-сборка выполняется внутри Docker-контейнера.

[![License](https://img.shields.io/github/license/AlexeyShalaev/hse-doc-studio)](LICENSE)
[![CI](https://github.com/AlexeyShalaev/hse-doc-studio/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/AlexeyShalaev/hse-doc-studio/actions/workflows/ci.yml)
[![Image](https://img.shields.io/badge/ghcr.io-hse--doc--studio-blue?logo=docker)](https://github.com/AlexeyShalaev/hse-doc-studio/pkgs/container/hse-doc-studio)
[![Docs](https://img.shields.io/badge/docs-online-blue)](https://alexeyshalaev.github.io/hse-doc-studio/)

> **Полная документация → [alexeyshalaev.github.io/hse-doc-studio](https://alexeyshalaev.github.io/hse-doc-studio/)**

---

## Quick start

```bash
mkdir hse-doc-studio && cd hse-doc-studio
curl -O https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/all-in-one/docker-compose.yml
docker compose up -d
```

Откройте **http://localhost:17240**, создайте проект из шаблона (ВКР, курсовая, PP), и начните писать.

Никаких аккаунтов, никаких облаков, файлы остаются на диске.

---

## Возможности

| Этап | Что происходит |
|-------|-------------|
| **Project Wizard** | Выбор шаблона, языка, научника, NDA, привязка к локальной папке |
| **Workspace** | Редактирование .tex, превью PDF, ГОСТ-проверки, требования, история |
| **Compile** | XeLaTeX в контейнере, стриминг лога, статус по каждому документу |
| **Pack submission** | Финальная сборка PDF с каноничными русскими именами файлов |

Поддерживаемые типы документов: ТЗ (19.201-78), ВКР (7.32-2017), ПМИ (19.301-79), ТП (19.401-78), РП (19.504-79), РО (19.505-79), Project Proposal, презентация.

---

## Deployment

Один контейнер, один порт: FastAPI отдаёт и API, и собранный интерфейс.

```bash
mkdir hse-doc-studio && cd hse-doc-studio
curl -O https://raw.githubusercontent.com/AlexeyShalaev/hse-doc-studio/master/deploy/all-in-one/docker-compose.yml
docker compose up -d
# → http://localhost:17240
```

Образ публикуется в GitHub Container Registry:

```
ghcr.io/alexeyshalaev/hse-doc-studio:latest
```

Переменные окружения, закрепление версии и обновление — в [папке `deploy/`](deploy/).

---

## Development

```bash
make install        # uv sync (backend) + pnpm install (web-app)
make dev            # backend (:17240) + frontend (:3000)
make check          # ruff + mypy + eslint + tsc — ровно то же, что в CI
make test           # полный прогон тестов обоих сервисов
make fmt-services   # автоформат
make help           # список команд
```

Порядок работы, соглашения по коммитам и релизный процесс — в [CONTRIBUTING.md](CONTRIBUTING.md).

## Структура

| Путь | Что |
|---|---|
| [services/api/](services/api/) | FastAPI-бэкенд (Onion: `api`/`use_cases`/`core`/`infra`), тесты |
| [services/web-app/](services/web-app/) | React + Vite UI (FSD) |
| [packs/](packs/) | Паки шаблонов по образовательным программам (LaTeX + метаданные) |
| [deploy/](deploy/) | Единственный Dockerfile проекта + Compose для готового образа |
| [scripts/](scripts/) | Makefile-обвязка для dev-окружения, тестов и инструментов |
| [docs/](docs/) | Сайт документации (zensical) |

## Лицензия

Apache 2.0 — см. [LICENSE](LICENSE).
