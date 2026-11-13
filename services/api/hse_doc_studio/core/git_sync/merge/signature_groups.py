"""Группы подписей: замороженный PDF и откреплённые подписи к нему берутся целиком с одной стороны.

Конфликт группы записан в `signatures.json` указателем `/signature_groups/<документ>`. Сами файлы группы
(`frozen[документ].path`, `detached[документ][слот].file`, версия на подписи `pinned[документ].path` и копия якорей
её сборки рядом) планировщик видит как обычные бинарники и решил бы по новизне, то есть мог бы смешать PDF одной
стороны с подписями другой. Здесь по плану определяется, какие файлы принадлежат спорной группе, чтобы они следовали
за решением по группе, а не за новизной.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Final

from hse_doc_studio.core.git_sync.merge.choices import (
    FieldChoice,
    FieldsResolution,
    FileChoice,
    FileChoiceResolution,
    FileResolution,
)
from hse_doc_studio.core.git_sync.merge.entities import MergeOp, MergePlan
from hse_doc_studio.core.git_sync.merge.jsonmerge import ConflictKind
from hse_doc_studio.core.git_sync.untrusted_json import loads_untrusted

SIGNATURES_FILE: Final = ".hse-studio/signatures.json"
# Как `use_cases.signatures.signing_source` называет версию на подписи и копию якорей её сборки.
PINNED_SUFFIX: Final = ".source.pdf"
PINNED_ANCHORS_SUFFIX: Final = ".source.anchors.json"
_GROUP_PREFIX: Final = "/signature_groups/"


@dataclass(frozen=True)
class GroupFiles:
    """Файлы одного документа у каждой стороны."""

    doc_id: str
    ours: frozenset[str]
    theirs: frozenset[str]

    @property
    def all(self) -> frozenset[str]:
        return self.ours | self.theirs


def pointer_for(doc_id: str) -> str:
    return _GROUP_PREFIX + doc_id.replace("~", "~0").replace("/", "~1")


def _doc_of(pointer: str) -> str:
    return pointer.removeprefix(_GROUP_PREFIX).replace("~1", "/").replace("~0", "~")


def _entry(data: Any, section: str, doc_id: str) -> Any:
    block = data.get(section) if isinstance(data, dict) else None
    return block.get(doc_id) if isinstance(block, dict) else None


def _referenced(raw: bytes | None, doc_id: str) -> frozenset[str]:
    if raw is None:
        return frozenset()
    try:
        data: Any = loads_untrusted(raw)
    except ValueError:
        return frozenset()
    frozen = _entry(data, "frozen", doc_id)
    detached = _entry(data, "detached", doc_id)
    pinned = _entry(data, "pinned", doc_id)
    pairs: list[tuple[object, str]] = [(frozen, "path"), (frozen, "signed_path"), (pinned, "path")]
    pairs += [(item, "file") for item in (detached.values() if isinstance(detached, dict) else ())]
    paths = {
        value for item, key in pairs if isinstance(item, dict) and isinstance(value := item.get(key), str) and value
    }
    # Копия якорей версии на подписи (signing-route.md, 15.17.6) едет вместе с её PDF.
    pinned_path = pinned.get("path") if isinstance(pinned, dict) else None
    if isinstance(pinned_path, str) and pinned_path.endswith(PINNED_SUFFIX):
        paths.add(pinned_path.removesuffix(PINNED_SUFFIX) + PINNED_ANCHORS_SUFFIX)
    return frozenset(paths)


def conflicting_groups(plan: MergePlan) -> list[GroupFiles]:
    """Группы подписей, по которым правили обе стороны и решает человек."""
    op = plan.op(SIGNATURES_FILE)
    if op is None or not op.needs_decision:
        return []
    docs = [_doc_of(item.pointer) for item in op.fields if item.kind is ConflictKind.signature_group]
    return [GroupFiles(doc, _referenced(op.ours, doc), _referenced(op.theirs, doc)) for doc in docs]


def group_paths(plan: MergePlan) -> frozenset[str]:
    """Пути файлов спорных групп вместе с копиями проигравших версий: их решает группа, а не отдельный файл."""
    paths: set[str] = set()
    for group in conflicting_groups(plan):
        paths |= group.all
    for op in plan.ops:
        if op.path in paths and op.copy_path is not None:
            paths.add(op.copy_path)
    return frozenset(paths)


def group_side(group: GroupFiles, resolution: FileResolution | None) -> FileChoice | None:
    """Чью сторону выбрал человек для группы; None, если решения нет."""
    if isinstance(resolution, FileChoiceResolution):
        return resolution.choice if resolution.choice in (FileChoice.mine, FileChoice.theirs) else None
    if isinstance(resolution, FieldsResolution):
        decision = resolution.fields.get(pointer_for(group.doc_id))
        if decision is None:
            return None
        return {FieldChoice.mine: FileChoice.mine, FieldChoice.theirs: FileChoice.theirs}.get(decision.choice)
    return None


def signatures_op(plan: MergePlan) -> MergeOp | None:
    return plan.op(SIGNATURES_FILE)


def sides_of(groups: Iterable[GroupFiles], resolutions: Mapping[str, FileResolution]) -> dict[str, FileChoice]:
    """doc_id -> выбранная сторона, только по группам с решением."""
    resolution = resolutions.get(SIGNATURES_FILE)
    return {group.doc_id: side for group in groups if (side := group_side(group, resolution)) is not None}
