"""Схемы пака (template-studio.md, D12): настоящие паки репозитория их проходят, ключи лоадера в них описаны.

Схемы строже лоадера: лоадер терпит незнакомое (пак от более новой Студии), а схема описывает, как писать пак.
Сверка «что схема допускает, лоадер разбирает» идёт выборкой в `test_pack_schema_loader.py`.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml
from hse_doc_studio.core.template_versions import MANIFEST_FORMAT
from hse_doc_studio.infra.template import releases, yaml_template_repository
from jsonschema import Draft202012Validator

from tests.unit.contract.pack_schemas import PACKS_ROOT, as_json, schema_for, schemas, validator

PACK_FILES = sorted(PACKS_ROOT.rglob("*.yaml"))

# Известные дефекты выпущенных версий (каталог неизменен, правится новой версией). Запятая внутри
# `{ ru: Моноширинный шрифт (код, листинги), en: ... }` делит строку: ru обрезается до «(код», а «листинги)»
# становится ключом без значения. Интерфейс показывает обрезанную подпись поля. Исправлено кавычками в
# hse-cs-sse/coursework 2026.1.6, hse-cs-se/coursework и vkr 2026.1.2, hse-cs-se/pp 2026.1.1: у них исключений нет,
# а `pack_lint` (`flow_text_lint`) не даёт выпустить такой текст снова.
_TRUNCATED_LABEL = "/meta_fields/{field}/label"
KNOWN_DEFECTS: dict[str, set[str]] = {
    "hse-cs-se/templates/pp/versions/2026.1/version.yaml": {
        _TRUNCATED_LABEL.format(field="font_mono"),
        "/pack_submission/profiles/0/description",
    },
    **{
        f"hse-cs-se/templates/{tpl}/versions/{ver}/version.yaml": {
            _TRUNCATED_LABEL.format(field="font_sans"),
            _TRUNCATED_LABEL.format(field="font_mono"),
        }
        for tpl in ("coursework", "vkr")
        for ver in ("2026.1", "2026.1.1")
    },
    **{
        f"hse-cs-sse/templates/coursework/versions/{ver}/version.yaml": {_TRUNCATED_LABEL.format(field="font_mono")}
        for ver in ("2026.1", "2026.1.1", "2026.1.2", "2026.1.3", "2026.1.4", "2026.1.5")
    },
}


def _pointer(path: Any) -> str:
    return "".join(f"/{part}" for part in path)


@pytest.mark.parametrize("name", sorted(schemas()))
def test_schema_is_valid_draft_2020_12(name: str) -> None:
    Draft202012Validator.check_schema(schemas()[name])
    assert schemas()[name]["$id"].endswith(f"/{name}.schema.json")


def test_manifest_format_matches_the_loader() -> None:
    """Подъём `MANIFEST_FORMAT` поднимает и предел схемы: схема описывает формат, который понимает эта Студия."""
    assert schemas()["version"]["properties"]["manifest_format"]["maximum"] == MANIFEST_FORMAT


def test_every_pack_file_has_a_schema() -> None:
    assert len(PACK_FILES) > 50
    names = {schema_for(path) for path in PACK_FILES} - {None}
    assert names == {"version", "doc", "template", "releases", "pack"}


@pytest.mark.parametrize(
    "path", [p for p in PACK_FILES if schema_for(p)], ids=lambda p: p.relative_to(PACKS_ROOT).as_posix()
)
def test_pack_file_passes_its_schema(path: Path) -> None:
    name = schema_for(path)
    assert name is not None
    data = as_json(yaml.safe_load(path.read_text(encoding="utf-8")))
    errors = {_pointer(error.absolute_path): error.message for error in validator(name).iter_errors(data)}
    known = KNOWN_DEFECTS.get(path.relative_to(PACKS_ROOT).as_posix(), set())
    assert set(errors) - known == set(), errors
    assert known <= set(errors), "дефект из KNOWN_DEFECTS исправлен: уберите его из списка"


def _schema_keys(node: Any) -> Iterator[str]:
    if isinstance(node, dict):
        yield from node.get("properties", {})
        for key in ("required", "dependentRequired"):
            value = node.get(key)
            if isinstance(value, list):
                yield from value
        for value in node.values():
            yield from _schema_keys(value)
    elif isinstance(node, list):
        for value in node:
            yield from _schema_keys(value)


def _text(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _read_keys(source: str) -> set[str]:
    """Строковые ключи, которые код читает: `x.get("k")`, `x["k"]`, `"k" in x`."""
    keys: set[str | None] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get":
            keys.update(_text(arg) for arg in node.args[:1])
        elif isinstance(node, ast.Subscript):
            keys.add(_text(node.slice))
        elif isinstance(node, ast.Compare) and isinstance(node.ops[0], ast.In):
            keys.add(_text(node.left))
    return {key for key in keys if key is not None}


# Функции разбора `checks/*.yaml`: у правил проверок схема появится позже.
_CHECKS_PARSERS = ("_parse_checks_dir", "_parse_checks_file", "_parse_check_source", "_parse_check_rule")
# Поля записи на якоре, которые разбор читает через общий помощник `_ranged(item, "dx_mm", ...)`.
_RANGED = {"width_mm", "dx_mm", "dy_mm", "height_mm"}


def test_every_key_the_loader_reads_is_in_a_schema() -> None:
    sources = [
        inspect.getsource(obj)
        for name, obj in inspect.getmembers(yaml_template_repository, inspect.isfunction)
        if obj.__module__ == yaml_template_repository.__name__ and name not in _CHECKS_PARSERS
    ]
    sources.append(inspect.getsource(releases.load_releases))
    # `"--" in doc_id` тоже сравнение со строкой, но не чтение ключа: ключи пака это имена.
    read = {key for source in sources for key in _read_keys(source) if key.isidentifier()} | _RANGED
    described = {key for schema in schemas().values() for key in _schema_keys(schema)}
    assert read - described == set()
