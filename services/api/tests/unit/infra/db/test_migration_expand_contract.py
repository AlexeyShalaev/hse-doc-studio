"""Правило expand/contract: новая миграция не ломает предыдущую версию api, пока идёт обновление.

В `upgrade()` нельзя удалять и переименовывать таблицы и колонки, менять тип, снимать значение
или ужесточать NOT NULL: такие шаги (contract) делаются отдельной миграцией в следующем выпуске,
когда прежняя версия api уже не работает. Список исключений только сокращается.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from hse_doc_studio.infra.db.migrator import MIGRATIONS_DIR

pytestmark = pytest.mark.unit

_DESTRUCTIVE = {"drop_column", "drop_table", "rename_table", "drop_constraint"}
# Ревизии, написанные до правила: данные ещё не жили в выпущенных установках.
_LEGACY_ALLOWED = {"0004_invite_scope"}


def _alter_violation(keywords: dict[str, ast.expr]) -> str | None:
    if "type_" in keywords or "new_column_name" in keywords:
        return "alter_column(type_/rename)"
    nullable = keywords.get("nullable")
    if isinstance(nullable, ast.Constant) and nullable.value is False:
        return "alter_column(nullable=False)"
    return None


def _call_violation(call: ast.Call) -> str | None:
    if not isinstance(call.func, ast.Attribute):
        return None
    if call.func.attr in _DESTRUCTIVE:
        return call.func.attr
    if call.func.attr == "alter_column":
        return _alter_violation({kw.arg: kw.value for kw in call.keywords if kw.arg})
    return None


def _violations(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    upgrades = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"]
    calls = [c for fn in upgrades for c in ast.walk(fn) if isinstance(c, ast.Call)]
    return [found for call in calls if (found := _call_violation(call))]


def _revision_files() -> list[Path]:
    return sorted((MIGRATIONS_DIR / "versions").glob("*.py"))


def test__upgrade__no_contract_steps_outside_legacy_allowlist() -> None:
    offenders = {}
    for path in _revision_files():
        stem = path.stem.split("-", 1)[-1]
        if stem in _LEGACY_ALLOWED:
            continue
        if found := _violations(path):
            offenders[stem] = found

    assert offenders == {}, "contract-шаги вынесите в отдельную миграцию следующего выпуска"


def test__legacy_allowlist__only_lists_existing_offenders() -> None:
    stems = {path.stem.split("-", 1)[-1]: path for path in _revision_files()}

    for revision in _LEGACY_ALLOWED:
        assert revision in stems
        assert _violations(stems[revision]), f"{revision} больше не нарушает правило: уберите из списка"
