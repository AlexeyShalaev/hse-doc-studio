"""Схемы пака `contracts/pack/*.schema.json`: загрузка, реестр ссылок между файлами, данные YAML в виде JSON."""

from __future__ import annotations

import json
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

REPO_ROOT = Path(__file__).resolve().parents[5]
SCHEMAS_DIR = REPO_ROOT / "contracts" / "pack"
PACKS_ROOT = REPO_ROOT / "packs"


@cache
def schemas() -> dict[str, dict[str, Any]]:
    """Схемы по имени файла без `.schema.json`: `version`, `doc`, `template`, `releases`, `pack`, `common`."""
    return {
        path.name.removesuffix(".schema.json"): json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(SCHEMAS_DIR.glob("*.schema.json"))
    }


@cache
def registry() -> Registry[Any]:
    resources = [(schema["$id"], Resource.from_contents(schema)) for schema in schemas().values()]
    return Registry[Any]().with_resources(resources)


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(schemas()[name], registry=registry(), format_checker=FormatChecker())


def as_json(value: Any) -> Any:
    """Данные `yaml.safe_load` в виде JSON: даты строкой ISO, ключи строками."""
    if isinstance(value, dict):
        return {str(k): as_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [as_json(v) for v in value]
    if isinstance(value, date):
        return value.isoformat()
    return value


def schema_for(path: Path) -> str | None:
    """Какая схема описывает файл пака; None у правил проверок (`checks/*.yaml`, схема позже)."""
    if path.parent.name == "checks":
        return None
    if path.name == "doc.yaml":
        return "doc"
    return path.name.removesuffix(".yaml")
