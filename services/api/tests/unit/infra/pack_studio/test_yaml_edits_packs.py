"""Точечные правки на настоящих файлах паков репозитория (template-studio.md, раздел 15).

Для каждого YAML пака: нулевая правка ничего не меняет; правка и обратная правка дают тот же байтовый файл; diff
правки затрагивает только строки узла. Узлы берутся выборкой, равномерно по файлу: полный перебор занял бы минуты.
Отдельно правки исключения patch (места, метки даты, пресет точки, подсказка срока) на копии версии проходят лоадер
и линтер пака.
"""

from __future__ import annotations

import copy
import difflib
import shutil
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from hse_doc_studio.infra.pack_studio.yaml_edits import YamlPath, delete, insert_item, move_item, set_value
from hse_doc_studio.infra.template.pack_lint import lint_version_dir
from hse_doc_studio.infra.template.yaml_template_repository import _parse_version
from yaml.nodes import MappingNode, Node, ScalarNode, SequenceNode

# .../services/api/tests/unit/infra/pack_studio/<this> -> корень репозитория.
PACKS_ROOT = Path(__file__).resolve().parents[6] / "packs"
PACK_FILES = sorted(PACKS_ROOT.rglob("*.yaml"))
SSE_VERSION = PACKS_ROOT / "hse-cs-sse" / "templates" / "coursework" / "versions" / "2026.1.5"

_LOADER: Any = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

# Сколько узлов каждого вида проверять в одном файле.
_LEAVES = 6
_LISTS = 3
_KEYS = 3


def _ids(path: Path) -> str:
    return path.relative_to(PACKS_ROOT).as_posix()


def _walk(
    node: Node | None, path: YamlPath = (), parent: Node | None = None
) -> list[tuple[YamlPath, Node, Node | None]]:
    """Узлы документа с путями и родителями."""
    out: list[tuple[YamlPath, Node, Node | None]] = []
    if node is None:
        return out
    out.append((path, node, parent))
    if isinstance(node, MappingNode):
        for key, value in node.value:
            out.extend(_walk(value, (*path, key.value), node))
    elif isinstance(node, SequenceNode):
        for i, item in enumerate(node.value):
            out.extend(_walk(item, (*path, i), node))
    return out


def _spread[T](items: list[T], count: int) -> list[T]:
    if len(items) <= count:
        return items
    step = len(items) / count
    return [items[int(i * step)] for i in range(count)]


def _get(text: str, path: YamlPath) -> Any:
    node = yaml.load(text, Loader=_LOADER)  # noqa: S506 — безопасный загрузчик
    for key in path:
        node = node[key]
    return node


def _bumped(value: Any) -> Any:
    if isinstance(value, bool):
        return not value
    if isinstance(value, int | float):
        return value + 1
    if isinstance(value, date):
        return value + timedelta(days=1)
    if isinstance(value, str):
        return "правка " + value
    return "правка"


def _changed_old_lines(before: str, after: str) -> tuple[set[int], int]:
    """Номера изменённых или удалённых строк исходного текста и число вставленных строк."""
    matcher = difflib.SequenceMatcher(a=before.splitlines(), b=after.splitlines(), autojunk=False)
    old: set[int] = set()
    inserted = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            old.update(range(i1, i2))
            inserted += (j2 - j1) if tag == "insert" else 0
    return old, inserted


def _lines(node: Node, text: str | None = None) -> set[int]:
    """Строки узла; с `text` ещё и комментарий прямо над ним (он принадлежит первому элементу списка)."""
    first = node.start_mark.line
    if text is not None:
        lines = text.splitlines()
        while first > 0 and lines[first - 1].lstrip().startswith("#"):
            first -= 1
    return set(range(first, max(node.end_mark.line, node.start_mark.line) + 1))


@pytest.fixture(params=PACK_FILES, ids=_ids)
def pack_file(request: pytest.FixtureRequest) -> tuple[str, Node]:
    text = request.param.read_text(encoding="utf-8")
    return text, yaml.compose(text)


def test_repository_has_pack_files() -> None:
    assert len(PACK_FILES) > 50
    assert SSE_VERSION.is_dir()


def test_zero_edit_is_byte_identical(pack_file: tuple[str, Node]) -> None:
    text, root = pack_file
    assert set_value(text, (), _get(text, ())) == text
    for path, _, _ in _spread([w for w in _walk(root) if w[0]], _LEAVES):
        assert set_value(text, path, _get(text, path)) == text


def test_set_and_back_touches_only_the_node(pack_file: tuple[str, Node]) -> None:
    text, root = pack_file
    leaves = [(p, n) for p, n, _ in _walk(root) if p and isinstance(n, ScalarNode)]
    for path, node in _spread(leaves, _LEAVES):
        original = _get(text, path)
        edited = set_value(text, path, _bumped(original))
        changed, _ = _changed_old_lines(text, edited)
        assert changed
        assert changed <= _lines(node), path
        restored = set_value(edited, path, original)
        if node.style in ("|", ">") or node.start_mark.line == node.end_mark.line:
            assert restored == text, path
        else:
            # Многострочный простой или кавычный скаляр после правки пишется в одну строку.
            assert _get(restored, ()) == _get(text, ())


def test_insert_and_delete_are_inverse(pack_file: tuple[str, Node]) -> None:
    text, root = pack_file
    lists = [(p, n) for p, n, _ in _walk(root) if isinstance(n, SequenceNode) and n.value]
    for path, node in _spread(lists, _LISTS):
        item = copy.deepcopy(_get(text, (*path, 0)))
        flow = text[node.start_mark.index] == "["
        for index in sorted({0, len(node.value) // 2, len(node.value)}):
            edited = insert_item(text, path, index, item)
            changed, inserted = _changed_old_lines(text, edited)
            if flow:
                assert changed <= _lines(node), path
            else:
                assert not changed, path
                assert inserted > 0
            assert delete(edited, (*path, index)) == text, (path, index)


def test_move_and_back(pack_file: tuple[str, Node]) -> None:
    text, root = pack_file
    lists = [(p, n) for p, n, _ in _walk(root) if isinstance(n, SequenceNode) and len(n.value) > 1]
    for path, node in _spread(lists, _LISTS):
        last = len(node.value) - 1
        for src, dst in ((0, last), (last, 0)):
            moved = move_item(text, path, src, dst)
            changed, _ = _changed_old_lines(text, moved)
            assert changed <= _lines(node, text), path
            assert move_item(moved, path, dst, src) == text, (path, src, dst)


def test_delete_touches_only_the_entry(pack_file: tuple[str, Node]) -> None:
    text, root = pack_file
    # Ключи блочных словарей: в однострочном `{...}` удаление меняет строку, а не убирает её.
    entries = [
        (path, key, node)
        for path, node, parent in _walk(root)
        if len(path) > 1 and isinstance(parent, MappingNode) and len(parent.value) > 1
        if text[parent.start_mark.index] != "{"
        for key, value in parent.value
        if value is node
    ]
    for path, key, node in _spread(entries, _KEYS):
        removed = delete(text, path)
        matcher = difflib.SequenceMatcher(a=text.splitlines(), b=removed.splitlines(), autojunk=False)
        changed = [op for op in matcher.get_opcodes() if op[0] != "equal"]
        old = {line for _, i1, i2, _, _ in changed for line in range(i1, i2)}
        new = sum(j2 - j1 for *_, j1, j2 in changed)
        lines = _lines(key, text) | _lines(node)
        # Первый ключ словаря на строке с `-` уступает место следующему: эта строка переписывается, а не удаляется.
        assert old <= lines | {max(lines) + 1}, path
        assert new <= 1, path


def test_patch_edits_pass_loader_and_lint(tmp_path: Path) -> None:
    """Правки исключения patch (signing-route.md, 15.10) на копии версии: файл остаётся паком."""
    version_dir = tmp_path / "2026.1.5"
    shutil.copytree(SSE_VERSION, version_dir)
    manifest = version_dir / "version.yaml"
    text = manifest.read_text(encoding="utf-8")
    slots = _get(text, ("signatures", "slots"))
    supervisor = next(i for i, slot in enumerate(slots) if slot["id"] == "supervisor")
    place = {"page": 1, "x_mm": 112, "y_mm": 131, "width_mm": 38}
    text = set_value(text, ("signatures", "slots", supervisor, "placements", "project_proposal"), place)
    mark = {"page": 1, "x_mm": 150, "y_mm": 250, "width_mm": 20, "height_mm": 5, "format": "date_numeric"}
    text = set_value(text, ("signatures", "slots", supervisor, "default_dates", "topic_application"), [mark])
    hint = {"ru": "Обычно в конце ноября", "en": "Usually at the end of November"}
    text = set_value(text, ("pack_submission", "profiles", 0, "deadline_hint"), hint)
    text = move_item(text, ("pack_submission", "profiles", 0, "signing_route"), 2, 1)
    manifest.write_text(text, encoding="utf-8")

    version = _parse_version(version_dir, pack_id="hse-cs-sse", template_id="coursework")
    assert version is not None
    slot = next(s for s in version.signatures_config.slots if s.id == "supervisor")
    assert dict(slot.placements)["project_proposal"].x_mm == 112
    assert "topic_application" in dict(slot.default_dates)
    profile = version.pack_submission.profiles[0]
    assert profile.deadline_hint == hint
    assert profile.signing_route[1] == ("academic_supervisor",)
    report = lint_version_dir(version_dir)
    assert report.ok, report.errors
