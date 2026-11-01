"""Храповик изоляции личных раннеров: кэш, разделяемый между проектами, кормит только выход общего раннера.

Сегодня выходы задач живут под префиксом задачи и в общий блоб-реестр не попадают. Любой будущий модуль
кэша в `infra/jobs` или `infra/storage` (выходы сборки по ключу входа, кэш конвертаций, кэш проверок)
обязан решать по `may_feed_shared_cache`, иначе выход личного раннера отравил бы чужие проекты.
"""

from __future__ import annotations

import ast
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[3] / "hse_doc_studio" / "infra"
_GUARD = "may_feed_shared_cache"


def _cache_modules() -> list[Path]:
    return sorted(p for folder in ("jobs", "storage") for p in (_ROOT / folder).glob("*cache*.py"))


def _imports_guard(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "hse_doc_studio.core.jobs.routing"
        and any(alias.name == _GUARD for alias in node.names)
        for node in ast.walk(tree)
    )


def test__shared_caches__decide_by_runner_scope() -> None:
    assert [str(p.relative_to(_ROOT)) for p in _cache_modules() if not _imports_guard(p)] == []


def test__guard__is_where_the_rule_says() -> None:
    from hse_doc_studio.core.jobs import routing  # noqa: PLC0415

    assert callable(getattr(routing, _GUARD))
