"""Храповик слоёв: core <- use_cases <- infra/api.

use_cases не должны импортировать infra и api. Сейчас нарушений много, поэтому
они записаны в allowlist-файлы рядом с тестом (по паре «файл модуль» на строку).
Новое нарушение роняет тест, а исправленное нужно удалить из списка (иначе упадёт
проверка устаревших записей), так что список может только сокращаться.
См. docs/design/collaboration.md, раздел 3.2.
"""

from __future__ import annotations

import ast
from pathlib import Path

import hse_doc_studio

_PACKAGE = "hse_doc_studio"
_ROOT = Path(hse_doc_studio.__file__).resolve().parent
_USE_CASES = _ROOT / "use_cases"
_CORE = _ROOT / "core"
_HERE = Path(__file__).resolve().parent

_INFRA = f"{_PACKAGE}.infra"
_API = f"{_PACKAGE}.api"

Pair = tuple[str, str]


def _module_name(path: Path) -> str:
    rel = path.relative_to(_ROOT.parent).with_suffix("")
    return ".".join(rel.parts)


def _resolve_from(node: ast.ImportFrom, path: Path) -> list[str]:
    """Модули, которые затрагивает `from ... import ...`, с учётом относительных импортов."""
    if node.level:
        package = _module_name(path).split(".")
        if path.name != "__init__.py":
            package = package[:-1]
        base = package[: len(package) - (node.level - 1)]
        parts = [*base, *([node.module] if node.module else [])]
        module = ".".join(parts)
    else:
        module = node.module or ""
    # `from hse_doc_studio import infra` тянет hse_doc_studio.infra, а не пакет целиком
    if module == _PACKAGE:
        return [f"{_PACKAGE}.{alias.name}" for alias in node.names]
    return [module]


def _imported_modules(path: Path) -> set[str]:
    """Все модули, импортируемые в файле, на любой глубине (TYPE_CHECKING, функции)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.update(_resolve_from(node, path))
    return modules


def _is_under(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(f"{prefix}.")


def _scan(root: Path, prefix: str) -> set[Pair]:
    pairs: set[Pair] = set()
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        pairs.update((rel, module) for module in _imported_modules(path) if _is_under(module, prefix))
    return pairs


def _load_allowlist(name: str) -> set[Pair]:
    pairs: set[Pair] = set()
    for line in (_HERE / name).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        file, module = line.split()
        pairs.add((file, module))
    return pairs


def _format(pairs: set[Pair]) -> str:
    return "\n".join(f"  {file}: {module}" for file, module in sorted(pairs))


def test__use_cases__infra_imports__only_allowlisted() -> None:
    new = _scan(_USE_CASES, _INFRA) - _load_allowlist("infra_allowlist.txt")

    assert not new, (
        "use_cases не должны импортировать infra: заведите порт в core и подставьте "
        "реализацию через DI (docs/design/collaboration.md, раздел 3.2). Новые нарушения:\n" + _format(new)
    )


def test__use_cases__infra_allowlist__has_no_stale_entries() -> None:
    stale = _load_allowlist("infra_allowlist.txt") - _scan(_USE_CASES, _INFRA)

    assert not stale, "Нарушение исправлено, удалите строки из infra_allowlist.txt:\n" + _format(stale)


def test__use_cases__api_imports__only_allowlisted() -> None:
    new = _scan(_USE_CASES, _API) - _load_allowlist("api_allowlist.txt")

    assert not new, (
        "use_cases не должны импортировать api: передайте значения через конструктор "
        "(docs/design/collaboration.md, раздел 3.2). Новые нарушения:\n" + _format(new)
    )


def test__use_cases__api_allowlist__has_no_stale_entries() -> None:
    stale = _load_allowlist("api_allowlist.txt") - _scan(_USE_CASES, _API)

    assert not stale, "Нарушение исправлено, удалите строки из api_allowlist.txt:\n" + _format(stale)


def test__core__imports__nothing_from_outer_layers() -> None:
    violations: set[Pair] = set()
    for prefix in (f"{_PACKAGE}.use_cases", _INFRA, _API):
        violations |= _scan(_CORE, prefix)

    assert not violations, "core не должен импортировать use_cases, infra и api:\n" + _format(violations)


def test__allowlists__paths__exist() -> None:
    missing = {
        (name, file)
        for name in ("infra_allowlist.txt", "api_allowlist.txt")
        for file, _ in _load_allowlist(name)
        if not (_USE_CASES / file).is_file()
    }

    assert not missing, "Allowlist ссылается на несуществующие файлы:\n" + _format(missing)
