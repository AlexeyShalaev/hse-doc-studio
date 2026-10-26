"""Каким станет файл при текущем черновике: нерешённые места показывают мою сторону."""

from __future__ import annotations

from hse_doc_studio.core.git_sync.merge.choices import (
    FieldsResolution,
    FileChoice,
    FileChoiceResolution,
    FileResolution,
    HunkChoice,
    HunksResolution,
    TextResolution,
)
from hse_doc_studio.core.git_sync.merge.drafts import prune
from hse_doc_studio.core.git_sync.merge.entities import MergeAction, MergeOp, MergeSide
from hse_doc_studio.core.git_sync.merge.text import render
from hse_doc_studio.core.git_sync.protocols import IFieldResolver
from hse_doc_studio.core.template_update.text import restore_text_style


def preview_result(op: MergeOp, resolution: FileResolution | None, resolver: IFieldResolver | None) -> bytes | None:
    """Содержимое файла после слияния (None: файл удаляется). Решение, которое плану не подходит, не учитывается."""
    match op.action:
        case MergeAction.take_theirs:
            return op.theirs
        case MergeAction.delete:
            return None
        case MergeAction.merged:
            return op.merged
        case MergeAction.binary_newest:
            return _newest(op, prune(op, resolution))
        case MergeAction.conflict:
            return _conflict(op, prune(op, resolution), resolver)


def _newest(op: MergeOp, resolution: FileResolution | None) -> bytes | None:
    if isinstance(resolution, FileChoiceResolution) and resolution.choice is not FileChoice.newest:
        return op.theirs if resolution.choice is FileChoice.theirs else op.ours
    return op.theirs if op.winner is MergeSide.theirs else op.ours


def _conflict(op: MergeOp, resolution: FileResolution | None, resolver: IFieldResolver | None) -> bytes | None:
    match resolution:
        case FileChoiceResolution():
            return op.theirs if resolution.choice is FileChoice.theirs else op.ours
        case TextResolution():
            return restore_text_style(resolution.content.encode(), op.ours)
        case HunksResolution() if op.text is not None:
            joined = render(op.text, resolution.hunks, HunkChoice.mine)
            return restore_text_style(joined, op.ours) if op.ours is not None else joined
        case FieldsResolution() if resolver is not None:
            choices = {pointer: item.choice for pointer, item in resolution.fields.items()}
            decision = resolver.resolve(op.path, op.base, op.ours, op.theirs, op.meta, choices)
            return decision.content if decision.content is not None else op.ours
    return op.ours
