"""Перевод сессии конфликтов и решений человека между телами запросов (api.schemas.git_sync) и сценариями."""

from __future__ import annotations

from collections.abc import Mapping

from hse_doc_studio.api.schemas import git_sync as schema
from hse_doc_studio.core.git_sync.error_messages import resolution_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode
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
from hse_doc_studio.use_cases.git_sync.conflict_views import (
    BinaryDetail,
    ConflictDiff,
    ConflictFileDetail,
    ConflictFileView,
    ConflictSessionView,
    DeleteDetail,
    FileSide,
    FileSides,
    JsonDetail,
    SessionSide,
    TextClean,
    TextDetail,
)


def resolution_from_body(body: schema.FileResolutionBody, path: str) -> FileResolution:
    """Решение из тела запроса; незнакомое слово выбора — invalid_resolution."""
    try:
        if isinstance(body, schema.FileChoiceResolution):
            return FileChoiceResolution(FileChoice(body.choice))
        if isinstance(body, schema.HunksResolution):
            return HunksResolution(
                {key: HunkDecision(HunkChoice(item.choice), item.text) for key, item in body.hunks.items()}
            )
        if isinstance(body, schema.FieldsResolution):
            return FieldsResolution(
                {pointer: FieldDecision(FieldChoice(item.choice)) for pointer, item in body.fields.items()}
            )
    except ValueError as exc:
        raise resolution_error(GitErrorCode.invalid_resolution, path) from exc
    return TextResolution(body.content)


def resolutions_from_body(bodies: Mapping[str, schema.FileResolutionBody]) -> dict[str, FileResolution]:
    return {path: resolution_from_body(body, path) for path, body in bodies.items()}


def resolution_to_body(resolution: FileResolution | None) -> schema.FileResolutionBody | None:
    match resolution:
        case None:
            return None
        case FileChoiceResolution():
            return schema.FileChoiceResolution(kind="file", choice=resolution.choice.value)
        case HunksResolution():
            return schema.HunksResolution(
                kind="hunks",
                hunks={
                    key: schema.HunkChoice(choice=item.choice.value, text=item.text)
                    for key, item in resolution.hunks.items()
                },
            )
        case FieldsResolution():
            return schema.FieldsResolution(
                kind="fields",
                fields={
                    pointer: schema.FieldChoice(choice=item.choice.value) for pointer, item in resolution.fields.items()
                },
            )
        case TextResolution():
            return schema.TextResolution(kind="text", content=resolution.content)


def _side(side: SessionSide) -> schema.ConflictSide:
    return schema.ConflictSide(commit=side.commit, author=side.author, at=side.at, message=side.message)


def _file_side(side: FileSide) -> schema.ConflictFileSide:
    return schema.ConflictFileSide(exists=side.exists, size=side.size, author=side.author, at=side.at)


def _sides(sides: FileSides) -> schema.ConflictFileSides:
    return schema.ConflictFileSides(
        ours=_file_side(sides.ours), theirs=_file_side(sides.theirs), base=_file_side(sides.base)
    )


def _file(item: ConflictFileView) -> schema.ConflictFile:
    return schema.ConflictFile(
        path=item.path,
        owner=item.owner,
        kind=item.kind,
        action=item.action,
        conflict_type=item.conflict_type,
        hunks=item.hunks,
        open_hunks=item.open_hunks,
        fields=item.fields,
        open_fields=item.open_fields,
        resolved=item.resolved,
        resolution=resolution_to_body(item.resolution),
        allowed=list(item.allowed),
        default_resolution=item.default_resolution,
        sides=_sides(item.sides),
        copy_path=item.copy_path,
        doc_id=item.doc_id,
    )


def map_session(view: ConflictSessionView) -> schema.ConflictSessionResponse:
    return schema.ConflictSessionResponse(
        id=view.id,
        fingerprint=view.fingerprint,
        ours=_side(view.ours),
        theirs=_side(view.theirs),
        base=_side(view.base) if view.base is not None else None,
        counts=schema.ConflictSessionCounts(
            conflict=view.counts.conflict, auto=view.counts.auto, total=view.counts.total
        ),
        unresolved=view.unresolved,
        drafts_saved_at=view.drafts_saved_at,
        warnings=[schema.OperationWarning(code=w.code.value, paths=list(w.paths)) for w in view.warnings],
        files=[_file(item) for item in view.files],
    )


def map_file_detail(detail: ConflictFileDetail) -> schema.ConflictFileDetailBody:
    if isinstance(detail, TextDetail):
        segments: list[schema.TextCleanSegment | schema.TextHunkSegment] = [
            schema.TextCleanSegment(type="clean", lines=list(seg.lines))
            if isinstance(seg, TextClean)
            else schema.TextHunkSegment(
                type="hunk",
                key=seg.key,
                ours=list(seg.ours),
                base=list(seg.base),
                theirs=list(seg.theirs),
                ours_start=seg.ours_start,
                result_start=seg.result_start,
            )
            for seg in detail.segments
        ]
        return schema.TextFileDetail(kind="text", eol=detail.eol, truncated=detail.truncated, segments=segments)
    if isinstance(detail, JsonDetail):
        return schema.JsonFileDetail(
            kind="json",
            fields=[
                schema.JsonFieldConflict(
                    pointer=f.pointer,
                    label=f.label,
                    type=f.type,
                    base=f.base,
                    ours=f.ours,
                    theirs=f.theirs,
                    allowed=list(f.allowed),
                    status=f.status,
                )
                for f in detail.fields
            ],
        )
    if isinstance(detail, BinaryDetail):
        return schema.BinaryFileDetail(
            kind="binary",
            ours=_file_side(detail.ours),
            theirs=_file_side(detail.theirs),
            newer=detail.newer,
            copy_path=detail.copy_path,
        )
    assert isinstance(detail, DeleteDetail)  # noqa: S101 — union исчерпан
    return schema.DeleteFileDetail(kind="delete", deleted_by=detail.deleted_by)


def map_diff(diff: ConflictDiff) -> schema.ConflictDiffResponse:
    return schema.ConflictDiffResponse(path=diff.path, binary=diff.binary, patch=diff.patch, truncated=diff.truncated)
