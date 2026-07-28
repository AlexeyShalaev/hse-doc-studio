# hse-doc-studio — Backend

FastAPI backend для hse-doc-studio. Хранит метаданные проектов и сборок на файловой системе. Запускает LaTeX-сборку и ГОСТ-проверки внутри контейнера.

## Architecture

- **`hse_doc_studio/core/`**: Доменные сущности, протоколы репозиториев, доменные сервисы (без сторонних зависимостей кроме pydantic).
- **`hse_doc_studio/use_cases/`**: Бизнес-логика — оркестрация доменных объектов, принимает `AsyncUnitOfWork`.
- **`hse_doc_studio/infra/`**: Реализации репозиториев (filesystem/SQLite), Docker-runner, DI (Dishka).
- **`hse_doc_studio/api/`**: FastAPI-роутеры и Pydantic-схемы.

## Quick Start

```bash
make install  # uv sync
make run-api  # uvicorn on :8000
```

## Testing

```bash
make test
```
