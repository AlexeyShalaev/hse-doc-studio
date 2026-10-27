"""Подробности одного файла сессии конфликтов и содержимое его сторон."""

from __future__ import annotations

import asyncio
import mimetypes
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Final, Literal
from uuid import UUID

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.merge.choices import FileResolution, HunkChoice, HunksResolution
from hse_doc_studio.core.git_sync.merge.drafts import prune
from hse_doc_studio.core.git_sync.merge.entities import ConflictType, ContentKind, MergeAction, MergeOp, MergeSide
from hse_doc_studio.core.git_sync.merge.jsonmerge import AutoField, FieldConflict
from hse_doc_studio.core.git_sync.merge.text import (
    CleanText,
    TextHunk,
    hunk_key,
    result_starts,
    split_lines,
    to_text_lines,
)
from hse_doc_studio.core.git_sync.protocols import IGitRepoReader
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.use_cases.git_sync.conflict_support import ConflictSessions, LoadedSession
from hse_doc_studio.use_cases.git_sync.conflict_views import (
    BinaryDetail,
    ConflictBlob,
    ConflictFileDetail,
    DeleteDetail,
    JsonDetail,
    JsonFieldView,
    TextClean,
    TextDetail,
    TextHunkView,
)
from hse_doc_studio.use_cases.git_sync.get_conflicts import Briefs, file_sides

# Сколько чистых строк текста отдаётся за раз: спорные участки отдаются всегда, иначе решать было бы нечего.
MAX_CLEAN_LINES: Final = 20_000
_INLINE_TYPES: Final = {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}

BlobSide = Literal["ours", "theirs", "base"]


@dataclass
class GetConflictFileInput:
    project_id: UUID
    path: str


@dataclass
class GetConflictBlobInput:
    project_id: UUID
    path: str
    side: BlobSide


class GetConflictFileUC:
    def __init__(self, *, sessions: ConflictSessions, reader: IGitRepoReader) -> None:
        self._sessions = sessions
        self._reader = reader

    async def execute(self, inp: GetConflictFileInput) -> ConflictFileDetail:
        loaded = await self._sessions.load(inp.project_id)
        return await asyncio.to_thread(self._detail, loaded, loaded.op(inp.path))

    def _detail(self, loaded: LoadedSession, op: MergeOp) -> ConflictFileDetail:
        draft = prune(op, loaded.pending.drafts.get(op.path))
        if op.conflict_type in (ConflictType.deleted_by_us, ConflictType.deleted_by_them):
            return DeleteDetail("ours" if op.conflict_type is ConflictType.deleted_by_us else "theirs")
        if op.kind is ContentKind.binary:
            briefs = Briefs(self._reader, loaded.project.folder)
            sides = file_sides(self._reader, loaded, op, briefs)
            newer = "theirs" if op.winner is MergeSide.theirs else "ours"
            return BinaryDetail(sides.ours, sides.theirs, newer, op.copy_path)
        if op.kind is ContentKind.json and op.action is not MergeAction.take_theirs:
            return _json_detail(op)
        return _text_detail(op, draft)


def _json_detail(op: MergeOp) -> JsonDetail:
    fields = [_field(item, "conflict") for item in op.fields]
    fields += [_field(item, "auto") for item in op.auto]
    return JsonDetail(tuple(fields))


def _field(item: FieldConflict | AutoField, status: str) -> JsonFieldView:
    return JsonFieldView(
        pointer=item.pointer,
        label=None,
        type=item.type.value,
        base=item.base,
        ours=item.ours,
        theirs=item.theirs,
        allowed=tuple(c.value for c in item.allowed),
        status=status,
    )


def _text_detail(op: MergeOp, draft: FileResolution | None) -> TextDetail:
    eol = "crlf" if op.ours is not None and b"\r\n" in op.ours else "lf"
    merge = op.text
    if merge is None or not merge.segments:
        # Файл не делится на участки: он показан одним целым, а решается файлом целиком или набранным текстом.
        whole = TextHunkView(
            key=hunk_key(op.ours or b"", op.theirs or b""),
            ours=tuple(to_text_lines(op.ours or b"")),
            base=tuple(to_text_lines(op.base or b"")),
            theirs=tuple(to_text_lines(op.theirs or b"")),
            ours_start=1,
            result_start=1,
        )
        return TextDetail(eol, False, (whole,))
    decisions = draft.hunks if isinstance(draft, HunksResolution) else {}
    starts = result_starts(merge, decisions, HunkChoice.mine)
    budget, truncated = MAX_CLEAN_LINES, False
    segments: list[TextClean | TextHunkView] = []
    for segment in merge.segments:
        if isinstance(segment, CleanText):
            lines = [line.rstrip(b"\n").decode("utf-8", "replace") for line in split_lines(segment.content)]
            if len(lines) > budget:
                lines, truncated = lines[:budget], True
            budget -= len(lines)
            segments.append(TextClean(tuple(lines)))
        elif isinstance(segment, TextHunk):
            segments.append(
                TextHunkView(
                    key=segment.key,
                    ours=tuple(to_text_lines(segment.ours)),
                    base=tuple(to_text_lines(segment.base)),
                    theirs=tuple(to_text_lines(segment.theirs)),
                    ours_start=segment.ours_start,
                    result_start=starts[segment.key],
                )
            )
    return TextDetail(eol, truncated, tuple(segments))


class GetConflictBlobUC:
    def __init__(self, *, sessions: ConflictSessions) -> None:
        self._sessions = sessions

    async def execute(self, inp: GetConflictBlobInput) -> ConflictBlob:
        loaded = await self._sessions.load(inp.project_id)
        op = loaded.op(inp.path)
        content = {"ours": op.ours, "theirs": op.theirs, "base": op.base}[inp.side]
        if content is None:
            raise _missing(inp.path, inp.side)
        return ConflictBlob(content, _media_type(op.path), PurePosixPath(op.path).name)


def _missing(path: str, side: str) -> NotFoundError:
    return NotFoundError(localized_error(f"У стороны {side} нет файла {path}", f"The {side} side has no {path}"))


def _media_type(path: str) -> str:
    """Безопасные для показа типы отдаются как есть; всё остальное скачивается как бинарные данные."""
    guessed, _ = mimetypes.guess_type(path)
    return guessed if guessed in _INLINE_TYPES else "application/octet-stream"
