"""Тексты интерфейса в однострочных словарях YAML пака: `{ ru: ..., en: ... }`.

В однострочном (flow) словаре запятая без кавычек заканчивает значение. `{ ru: Моноширинный шрифт (код, листинги),
en: Monospace font }` разбирается как ru «Моноширинный шрифт (код», лишний ключ «листинги)» без значения и en: интерфейс
показывает обрезанную подпись, и ни лоадер, ни схема пака этого не замечают (лоадер берёт `ru` и `en`). Здесь:

- в однострочном словаре с ключом `ru` или `en` каждый ключ это код языка со значением; иначе это остаток разрезанной
  строки;
- значение `ru`/`en` без кавычек со скобками без пары (`(`, `[`, `«`): строку разрезала запятая.

Проверяются `version.yaml`, `checks/*.yaml` и `doc.yaml` документов; прочие YAML в `files/` это содержимое проекта.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import yaml
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

from hse_doc_studio.infra.project_init.template_renderer import PACK_DOC_MANIFEST

_LOCALES = frozenset({"ru", "en"})
_LANG_RE = re.compile(r"^[a-z]{2}(?:-[A-Za-z]{2,})?$")
_PAIRS = (("(", ")"), ("[", "]"), ("«", "»"))
_HINT = "запятая без кавычек разрезала строку, возьмите значение в кавычки"


def _pack_yaml_files(version_dir: Path) -> list[Path]:
    files = [version_dir / "version.yaml", *sorted((version_dir / "checks").glob("*.yaml"))]
    files += sorted((version_dir / "files").rglob(PACK_DOC_MANIFEST))
    return [f for f in files if f.is_file() and not f.is_symlink()]


def _nodes(node: Node | None) -> Iterator[Node]:
    if node is None:
        return
    yield node
    if isinstance(node, MappingNode):
        for key, value in node.value:
            yield from _nodes(key)
            yield from _nodes(value)
    elif isinstance(node, SequenceNode):
        for item in node.value:
            yield from _nodes(item)


def _unbalanced(text: str) -> bool:
    return any(text.count(left) != text.count(right) for left, right in _PAIRS)


def _is_null(node: Node) -> bool:
    return isinstance(node, ScalarNode) and node.tag == "tag:yaml.org,2002:null"


def _mapping_problems(where: str, mapping: MappingNode) -> list[str]:
    keys = [key.value for key, _ in mapping.value if isinstance(key, ScalarNode)]
    if not _LOCALES & set(keys):
        return []
    problems: list[str] = []
    for key, value in mapping.value:
        line = f"{where}:{key.start_mark.line + 1}"
        if not isinstance(key, ScalarNode) or not _LANG_RE.match(key.value):
            name = key.value if isinstance(key, ScalarNode) else "?"
            problems.append(f"{line}: лишний ключ «{name}» в {{ ru, en }}: {_HINT}")
        elif _is_null(value):
            problems.append(f"{line}: ключ «{key.value}» без значения в {{ ru, en }}: {_HINT}")
        elif (
            key.value in _LOCALES and isinstance(value, ScalarNode) and value.style is None and _unbalanced(value.value)
        ):
            problems.append(f"{line}: {key.value} «{value.value}» со скобкой без пары: {_HINT}")
    return problems


def lint_flow_texts(version_dir: Path) -> list[str]:
    """Разрезанные запятой тексты `{ ru, en }` в YAML версии; пути относительно каталога версии."""
    problems: list[str] = []
    for path in _pack_yaml_files(version_dir):
        try:
            root = yaml.compose(path.read_text(encoding="utf-8"), Loader=yaml.SafeLoader)
        except yaml.YAMLError:
            continue  # файл, который не разбирается, называют лоадер и другие проверки
        where = path.relative_to(version_dir).as_posix()
        for node in _nodes(root):
            if isinstance(node, MappingNode) and node.flow_style:
                problems.extend(_mapping_problems(where, node))
    return problems
