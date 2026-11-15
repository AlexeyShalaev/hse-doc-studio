"""Фоновые задачи use_cases не наследуют транзакцию вызывающего.

`asyncio.create_task` копирует контекст целиком, вместе с ambient-транзакцией: задача, начатая внутри неё, взяла
бы ту же `AsyncSession`, пока вызывающий ещё работает с ней (asyncpg: «another operation is in progress», так
не уходили письма-уведомления в 0.29.0). Поэтому use_cases отпускают задачи только через
`core.uow.spawn_detached`, а побочные эффекты события откладывают до коммита через `core.uow.after_commit`.
"""

from __future__ import annotations

import ast
from pathlib import Path

import hse_doc_studio
import pytest

pytestmark = pytest.mark.unit

_USE_CASES = Path(hse_doc_studio.__file__).resolve().parent / "use_cases"
_SPAWNERS = frozenset({"create_task", "ensure_future"})


def _bare_spawns(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else func.id if isinstance(func, ast.Name) else None
        # Задача с явным контекстом (например, пустым `contextvars.Context()`) транзакцию тоже не наследует.
        if name in _SPAWNERS and not any(kw.arg == "context" for kw in node.keywords):
            found.append(f"{path.relative_to(_USE_CASES).as_posix()}:{node.lineno}")
    return found


def test__use_cases__spawn_tasks_only_without_caller_transaction() -> None:
    bare = [hit for path in sorted(_USE_CASES.rglob("*.py")) for hit in _bare_spawns(path)]

    assert not bare, (
        "use_cases запускают фоновые задачи через core.uow.spawn_detached (или с явным context=), "
        "иначе задача унаследует транзакцию вызывающего и её сессию:\n" + "\n".join(f"  {hit}" for hit in bare)
    )
