"""Вычислитель результата Студии шаблонов не читает файлы, часы и случайность и не ходит в сеть (раздел 8 дизайна
`docs/design/template-studio-outcome.md`, риск «побочные эффекты симуляции», R15).

Проверка по исходникам: ни один модуль пакетов вычислителя не импортирует ввод-вывод, время, случайность и слои
infra и api, и не зовёт `open`, `now`, `today`, чтение и запись файлов."""

from __future__ import annotations

import ast
from pathlib import Path

import hse_doc_studio
import pytest

_ROOT = Path(hse_doc_studio.__file__).resolve().parent
_PACKAGES = (_ROOT / "core" / "pack_studio" / "outcome", _ROOT / "use_cases" / "pack_studio" / "outcome")

_FORBIDDEN_MODULES = frozenset(
    {
        "os",
        "pathlib",
        "shutil",
        "subprocess",
        "socket",
        "asyncio",
        "threading",
        "multiprocessing",
        "concurrent",
        "time",
        "random",
        "secrets",
        "uuid",
        "tempfile",
        "io",
        "sqlite3",
        "httpx",
        "requests",
        "urllib",
        "sqlalchemy",
    }
)
_FORBIDDEN_LAYERS = ("hse_doc_studio.infra", "hse_doc_studio.api")
_FORBIDDEN_CALLS = frozenset({"open", "now", "today", "utcnow", "read_text", "write_text", "read_bytes", "write_bytes"})


def _files() -> list[Path]:
    files = sorted(path for package in _PACKAGES for path in package.rglob("*.py"))
    assert files, "пакеты вычислителя не найдены"
    return files


def _imports(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.relative_to(_ROOT).as_posix())
def test__outcome__module_has_no_io_clock_or_random_imports(path: Path) -> None:
    modules = _imports(ast.parse(path.read_text(encoding="utf-8"), filename=str(path)))

    bad = {m for m in modules if m.split(".")[0] in _FORBIDDEN_MODULES}
    layers = {m for m in modules if any(m == layer or m.startswith(f"{layer}.") for layer in _FORBIDDEN_LAYERS)}

    assert not bad, f"ввод-вывод, время или случайность: {sorted(bad)}"
    assert not layers, f"слои infra и api: {sorted(layers)}"


@pytest.mark.parametrize("path", _files(), ids=lambda p: p.relative_to(_ROOT).as_posix())
def test__outcome__module_has_no_io_or_clock_calls(path: Path) -> None:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    calls: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
            if name in _FORBIDDEN_CALLS:
                calls.add(name)

    assert not calls, f"вызовы ввода-вывода или часов: {sorted(calls)}"
