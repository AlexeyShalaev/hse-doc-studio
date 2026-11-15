"""Схемы манифестов пака для `hse-doc-studio pack check` (docs/design/template-studio.md, D12, 4.4).

Источник правды `contracts/pack/*.schema.json`; в пакете лежит их побайтная копия (`schemas/`), потому что образ
и установленный CLI монорепы не видят. Совпадение копии с контрактом сверяет тест
`tests/unit/infra/pack_studio/test_pack_schemas_copy.py`.
"""

from __future__ import annotations

import json
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

SCHEMAS_DIR = Path(__file__).with_name("schemas")


@cache
def schemas() -> dict[str, dict[str, Any]]:
    """Схемы по имени файла без `.schema.json`: `version`, `doc`, `template`, `releases`, `pack`, `common`."""
    return {
        path.name.removesuffix(".schema.json"): json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(SCHEMAS_DIR.glob("*.schema.json"))
    }


@cache
def _validators() -> dict[str, Any]:
    # jsonschema приходит зависимостью mcp; импорт ленивый, чтобы остальной CLI от него не зависел.
    from jsonschema import Draft202012Validator, FormatChecker  # noqa: PLC0415
    from referencing import Registry, Resource  # noqa: PLC0415

    registry: Registry[Any] = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas().values()
    )
    return {
        name: Draft202012Validator(schema, registry=registry, format_checker=FormatChecker())
        for name, schema in schemas().items()
        if name != "common"
    }


def schema_for(path: Path) -> str | None:
    """Какая схема описывает файл пака; None у правил проверок (`checks/*.yaml`) и прочих файлов."""
    if path.parent.name == "checks":
        return None
    if path.name == "doc.yaml":
        return "doc"
    name = path.name.removesuffix(".yaml")
    return name if name in {"version", "template", "releases", "pack"} else None


def as_json(value: Any) -> Any:
    """Данные `yaml.safe_load` в виде JSON: даты строкой ISO, ключи строками."""
    if isinstance(value, dict):
        return {str(k): as_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [as_json(v) for v in value]
    if isinstance(value, date):
        return value.isoformat()
    return value


def validation_errors(name: str, data: Any) -> list[tuple[tuple[str | int, ...], str]]:
    """Ошибки данных по схеме `name`: путь в данных (ключи и индексы) и сообщение, в порядке путей."""
    errors = _validators()[name].iter_errors(as_json(data))
    found = [(tuple(error.absolute_path), error.message) for error in errors]
    return sorted(found, key=lambda item: (pointer_of(item[0]), item[1]))


def pointer_of(path: tuple[str | int, ...]) -> str:
    """JSON-указатель пути в данных: `/meta_fields/year`, корень `/`."""
    return "".join(f"/{part}" for part in path) or "/"


def validate(name: str, data: Any) -> list[str]:
    """Ошибки данных по схеме `name`: «/путь/в/файле: сообщение», в порядке путей."""
    return [f"{pointer_of(path)}: {message}" for path, message in validation_errors(name, data)]
