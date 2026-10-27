"""Решения человека по конфликтам: проверка по плану, подсчёт нерешённого и запись в JSON.

Решение называет участки текста и поля структуры ключами, а не номерами: после нового пересчёта плана
оно остаётся верным для тех мест, которые не изменились. `prune` оставляет в решении только то, что
плану по-прежнему знакомо.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from hse_doc_studio.core.git_sync.merge.choices import (
    FieldChoice,
    FieldDecision,
    FieldsResolution,
    FileChoice,
    FileChoiceResolution,
    FileResolution,
    HunkChoice,
    HunkDecision,
    HunksResolution,
    TextResolution,
)
from hse_doc_studio.core.git_sync.merge.entities import ConflictType, ContentKind, MergeAction, MergeOp

_NO_CONTENT_CONFLICTS = frozenset({ConflictType.deleted_by_us, ConflictType.deleted_by_them})


@dataclass(frozen=True)
class FileProgress:
    """Сколько в файле осталось решить с учётом черновика."""

    open_hunks: int
    open_fields: int
    resolved: bool


def resolution_to_json(resolution: FileResolution) -> dict[str, Any]:
    """Форма совпадает с телом запроса resolve (contracts/git-sync)."""
    match resolution:
        case FileChoiceResolution():
            return {"kind": "file", "choice": resolution.choice.value}
        case HunksResolution():
            hunks = {
                key: {"choice": item.choice.value, **({"text": item.text} if item.text is not None else {})}
                for key, item in resolution.hunks.items()
            }
            return {"kind": "hunks", "hunks": hunks}
        case FieldsResolution():
            return {
                "kind": "fields",
                "fields": {pointer: {"choice": item.choice.value} for pointer, item in resolution.fields.items()},
            }
        case TextResolution():
            return {"kind": "text", "content": resolution.content}


def resolution_from_json(raw: Any) -> FileResolution | None:
    """Решение из записанного JSON; повреждённое или незнакомое даёт None."""
    if not isinstance(raw, dict):
        return None
    try:
        return _parse(raw)
    except (KeyError, TypeError, ValueError, AttributeError):
        return None


def _parse(raw: dict[str, Any]) -> FileResolution | None:
    kind = raw.get("kind")
    if kind == "file":
        return FileChoiceResolution(FileChoice(raw["choice"]))
    if kind == "text":
        return TextResolution(str(raw["content"]))
    if kind == "hunks":
        hunks = {
            str(key): HunkDecision(HunkChoice(item["choice"]), _text_or_none(item.get("text")))
            for key, item in raw["hunks"].items()
        }
        return HunksResolution(hunks)
    if kind == "fields":
        fields = {str(pointer): FieldDecision(FieldChoice(item["choice"])) for pointer, item in raw["fields"].items()}
        return FieldsResolution(fields)
    return None


def _text_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def field_choices(op: MergeOp) -> dict[str, tuple[FieldChoice, ...]]:
    """Поля файла, по которым человек вправе решать, и допустимые решения: спорные и решённые правилами."""
    allowed = {item.pointer: tuple(item.allowed) for item in op.auto if item.allowed}
    allowed.update({item.pointer: tuple(item.allowed) for item in op.fields})
    return allowed


def prune(op: MergeOp, resolution: FileResolution | None) -> FileResolution | None:
    """Решение без того, что плану неизвестно или недопустимо; None, если ничего не осталось."""
    if resolution is None or not (op.needs_decision or op.action is MergeAction.binary_newest):
        return None
    match resolution:
        case FileChoiceResolution():
            return resolution if resolution.choice in op.allowed_choices() else None
        case TextResolution():
            return resolution if _takes_text(op) else None
        case HunksResolution():
            keys = {hunk.key for hunk in op.hunks}
            kept = {
                key: item
                for key, item in resolution.hunks.items()
                if key in keys and (item.choice is not HunkChoice.custom or item.text is not None)
            }
            return HunksResolution(kept) if kept else None
        case FieldsResolution():
            allowed = field_choices(op)
            fields = {
                pointer: item for pointer, item in resolution.fields.items() if item.choice in allowed.get(pointer, ())
            }
            return FieldsResolution(fields) if fields else None


def _takes_text(op: MergeOp) -> bool:
    return (
        op.needs_decision
        and op.kind is ContentKind.text
        and op.conflict_type not in _NO_CONTENT_CONFLICTS
        and op.ours is not None
    )


def progress(op: MergeOp, resolution: FileResolution | None) -> FileProgress:
    """Состояние файла: нерешённые участки и поля, решён ли он целиком. Файл без конфликта решён всегда."""
    if not op.needs_decision:
        return FileProgress(0, 0, True)
    resolution = prune(op, resolution)
    hunks, fields = len(op.hunks), len(op.fields)
    match resolution:
        case FileChoiceResolution() | TextResolution():
            return FileProgress(0, 0, True)
        case HunksResolution():
            open_hunks = len({hunk.key for hunk in op.hunks} - set(resolution.hunks))
            return FileProgress(open_hunks, fields, open_hunks == 0 and fields == 0)
        case FieldsResolution():
            open_fields = len({item.pointer for item in op.fields} - set(resolution.fields))
            return FileProgress(hunks, open_fields, open_fields == 0 and hunks == 0)
        case None:
            return FileProgress(hunks, fields, False)


def prune_all(plan_ops: Mapping[str, MergeOp], drafts: Mapping[str, FileResolution]) -> dict[str, FileResolution]:
    """Черновики, которые подходят пересчитанному плану."""
    kept: dict[str, FileResolution] = {}
    for path, resolution in drafts.items():
        op = plan_ops.get(path)
        pruned = prune(op, resolution) if op is not None else None
        if pruned is not None:
            kept[path] = pruned
    return kept


def is_empty(resolution: FileResolution) -> bool:
    """Решение без единого выбора: так человек снимает черновик с файла."""
    if isinstance(resolution, HunksResolution):
        return not resolution.hunks
    if isinstance(resolution, FieldsResolution):
        return not resolution.fields
    return False
