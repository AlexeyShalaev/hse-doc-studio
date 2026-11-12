"""Правило expand/contract: новая миграция не ломает предыдущую версию api, пока идёт обновление.

В `upgrade()` нельзя удалять и переименовывать таблицы и колонки, менять тип, снимать значение
или ужесточать NOT NULL: такие шаги (contract) делаются отдельной миграцией в следующем выпуске,
когда прежняя версия api уже не работает. Список исключений только сокращается.

Contract-миграция помечает себя тремя переменными модуля: `contract_drops` (таблицы, которые она
удаляет), `contract_retired_by` (ревизия, которая вывела их из употребления) и `contract_released_in`
(выпуск, в который та ревизия вошла). Разрушающие шаги в её `upgrade()` разрешены только над
этими таблицами, и только если у таблиц уже нет моделей, ревизия вывода стоит раньше в цепочке,
а выпуск уже вышел и, по его тегу, содержит ревизию вывода, но не саму contract-миграцию.
"""

from __future__ import annotations

import ast
import shutil
import subprocess
from functools import cache
from pathlib import Path
from types import ModuleType

import pytest
from alembic.script import ScriptDirectory
from hse_doc_studio import __version__
from hse_doc_studio.infra.db import migrator
from hse_doc_studio.infra.db.migrator import MIGRATIONS_DIR

pytestmark = pytest.mark.unit

_DESTRUCTIVE = {"drop_column", "drop_table", "rename_table", "drop_constraint"}
# Ревизии, написанные до правила: данные ещё не жили в выпущенных установках.
_LEGACY_ALLOWED = {"0004_invite_scope"}
_CONTRACT_MARKERS = ("contract_drops", "contract_retired_by", "contract_released_in")
_VERSIONS_DIR = MIGRATIONS_DIR / "versions"


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


def _call_table(call: ast.Call) -> str | None:
    """Таблица шага: `table_name=` или позиционный аргумент (у `drop_constraint` второй)."""
    keywords = {kw.arg: kw.value for kw in call.keywords if kw.arg}
    position = 1 if isinstance(call.func, ast.Attribute) and call.func.attr == "drop_constraint" else 0
    node = keywords.get("table_name") or (call.args[position] if len(call.args) > position else None)
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _steps(path: Path) -> list[tuple[str, str | None]]:
    """Разрушающие шаги `upgrade()`: что за шаг и над какой таблицей."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    upgrades = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"]
    calls = [c for fn in upgrades for c in ast.walk(fn) if isinstance(c, ast.Call)]
    return [(found, _call_table(call)) for call in calls if (found := _call_violation(call))]


def _violations(path: Path, allowed_tables: frozenset[str] = frozenset()) -> list[str]:
    return [found for found, table in _steps(path) if table is None or table not in allowed_tables]


def _revision_files() -> list[Path]:
    return sorted(_VERSIONS_DIR.glob("*.py"))


def _stem(path: Path) -> str:
    return path.stem.split("-", 1)[-1]


@cache
def _scripts() -> ScriptDirectory:
    return ScriptDirectory.from_config(migrator._config())


def _contracts() -> dict[str, ModuleType]:
    """Contract-миграции: ревизии, у модуля которых есть хоть одна пометка."""
    modules = {script.revision: script.module for script in _scripts().walk_revisions()}
    return {
        revision: module
        for revision, module in modules.items()
        if any(hasattr(module, marker) for marker in _CONTRACT_MARKERS)
    }


def _ancestors(revision: str) -> set[str]:
    seen: set[str] = set()
    pending = [revision]
    while pending:
        script = _scripts().get_revision(pending.pop())
        down = script.down_revision if script is not None else None
        parents = [] if down is None else [down] if isinstance(down, str) else list(down)
        for parent in parents:
            if parent not in seen:
                seen.add(parent)
                pending.append(parent)
    return seen


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def test__upgrade__no_contract_steps_outside_legacy_allowlist() -> None:
    contracts = _contracts()
    offenders = {}
    for path in _revision_files():
        stem = _stem(path)
        if stem in _LEGACY_ALLOWED:
            continue
        allowed = frozenset(getattr(contracts.get(stem), "contract_drops", ()))
        if found := _violations(path, allowed):
            offenders[stem] = found

    assert offenders == {}, "contract-шаги вынесите в отдельную миграцию следующего выпуска"


def test__legacy_allowlist__only_lists_existing_offenders() -> None:
    stems = {_stem(path): path for path in _revision_files()}

    for revision in _LEGACY_ALLOWED:
        assert revision in stems
        assert _violations(stems[revision]), f"{revision} больше не нарушает правило: уберите из списка"


@pytest.mark.parametrize("revision", sorted(_contracts()))
def test__contract_migration__drops_only_tables_retired_in_a_released_version(revision: str) -> None:
    module = _contracts()[revision]
    assert all(hasattr(module, marker) for marker in _CONTRACT_MARKERS), f"нужны все пометки {_CONTRACT_MARKERS}"
    drops = set(module.contract_drops)
    path = next(path for path in _revision_files() if _stem(path) == revision)

    assert drops, "contract_drops пуст"
    assert drops == {table for _, table in _steps(path)}, "пометка не совпадает с шагами upgrade()"
    assert not drops & set(migrator.Base.metadata.tables), "у удаляемой таблицы есть модель: код ей пользуется"
    assert not drops & migrator.RETIRED_TABLES, "удалённую таблицу уберите из RETIRED_TABLES"
    assert module.contract_retired_by in _ancestors(revision), "ревизия вывода из употребления должна идти раньше"
    assert _version(module.contract_released_in) <= _version(__version__), "выпуск с выводом ещё не вышел"


@pytest.mark.parametrize("revision", sorted(_contracts()))
def test__contract_migration__retiring_revision_shipped_in_declared_release(revision: str) -> None:
    """По тегу выпуска: ревизия вывода в нём уже была, а сама contract-миграция ещё нет."""
    module = _contracts()[revision]
    tag = f"v{module.contract_released_in}"
    git = shutil.which("git")
    if git is None:
        pytest.skip("нет git")
    found = subprocess.run(
        [git, "rev-parse", "--verify", "--quiet", f"{tag}^{{commit}}"],
        cwd=_VERSIONS_DIR,
        capture_output=True,
        check=False,
    )
    if found.returncode != 0:
        pytest.skip(f"тега {tag} нет в этой копии (неглубокий checkout)")

    listing = subprocess.run(
        [git, "ls-tree", "--name-only", tag, "."], cwd=_VERSIONS_DIR, capture_output=True, text=True, check=True
    ).stdout
    shipped = {_stem(Path(name)) for name in listing.split()}

    assert module.contract_retired_by in shipped
    assert revision not in shipped
