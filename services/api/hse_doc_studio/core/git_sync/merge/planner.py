"""План слияния: чистая функция от трёх деревьев файлов.

Для каждого пути (B — база, O — моё, T — чужое; «~» значит «одинаково по смыслу»):

    O ~ T                      уже одно и то же — ничего не делаем (в том числе оба удалили)
    B ~ T                      чужая сторона путь не меняла — моё остаётся
    B ~ O, T нет               чужая сторона удалила — удаляем (delete)
    B ~ O, T есть              берём чужое (take_theirs, в том числе новый файл)
    O нет, T правили           конфликт deleted_by_us
    T нет, O правили           конфликт deleted_by_them
    B нет, оба добавили        текст — add_add (всегда решает человек), бинарник — побеждает новее
    правили обе стороны        слияние по виду файла: текст, структурированный JSON, бинарник

Сравнение по смыслу — как у обновления шаблона (core.template_update.text): концы строк,
BOM и упаковка zip правкой не считаются. Результат не зависит от того, какая сторона «моя».
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace

from hse_doc_studio.core.git_sync.entities import SyncWarning, SyncWarningCode
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.merge.binary import blob_sha, conflict_copy_name, merge_binary
from hse_doc_studio.core.git_sync.merge.choices import (
    FieldsResolution,
    FileChoice,
    FileChoiceResolution,
    FileResolution,
    HunkChoice,
    HunksResolution,
    TextResolution,
)
from hse_doc_studio.core.git_sync.merge.entities import (
    ConflictType,
    ContentKind,
    MergeAction,
    MergeOp,
    MergePlan,
    MergeSide,
)
from hse_doc_studio.core.git_sync.merge.jsonmerge import InvalidFieldChoiceError
from hse_doc_studio.core.git_sync.merge.paths import collision_groups, is_safe_path
from hse_doc_studio.core.git_sync.merge.text import (
    TextMerge,
    has_hse_markers,
    merge_text,
    render,
    single_hunk,
)
from hse_doc_studio.core.git_sync.protocols import IFieldResolver, IFileMergeStrategy, MergeMeta
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.template_update.entities import FileWrite, FileWriteKind
from hse_doc_studio.core.template_update.protocols import IMergeEngine
from hse_doc_studio.core.template_update.text import is_binary, restore_text_style, same_content

_STUDIO_PREFIX = ".hse-studio/"


@dataclass(frozen=True)
class MergeInput:
    """Содержимое файлов трёх коммитов; ключ — путь от корня проекта (POSIX).

    Достаточно передать пути, где деревья различаются: путь, которого нет ни в одном
    из трёх словарей, слиянию неинтересен. Если путь есть в одном словаре, он должен быть
    во всех, где файл существует.
    """

    base: Mapping[str, bytes]
    ours: Mapping[str, bytes]
    theirs: Mapping[str, bytes]
    base_commit: str | None = None
    theirs_commit: str | None = None
    # Время и коммит последней правки пути с каждой стороны: по ним выбирается более новый бинарник.
    meta: Mapping[str, MergeMeta] = field(default_factory=dict)
    # Пути, которые читатель дерева отверг сам (символьные ссылки, подмодули).
    blocked: frozenset[str] = frozenset()


def plan_merge(inp: MergeInput, engine: IMergeEngine, structured: IFileMergeStrategy | None = None) -> MergePlan:
    """План слияния.

    `engine` сливает текст и обязан подписывать маркеры подписями из core.git_sync.merge.text.
    `structured` сливает файлы состояния `.hse-studio/*.json` по полям; без него они сливаются как текст.
    Файл, который стратегия не смогла разобрать, тоже сливается как текст.
    """
    paths = sorted(set(inp.base) | set(inp.ours) | set(inp.theirs))
    unsafe = [path for path in paths if path in inp.blocked or not is_safe_path(path)]
    skipped = set(unsafe)
    ops = [op for path in paths if path not in skipped if (op := _plan_path(path, inp, engine, structured))]
    ops, collided = _resolve_collisions(ops, inp.ours)
    ops.sort(key=lambda op: op.path)
    warnings = [
        SyncWarning(code, tuple(found))
        for code, found in ((SyncWarningCode.unsafe_path, unsafe), (SyncWarningCode.case_collision, collided))
        if found
    ]
    warnings.extend(warning for op in ops for warning in op.warnings)
    fingerprint = plan_fingerprint(ops, base_commit=inp.base_commit, theirs_commit=inp.theirs_commit)
    return MergePlan(inp.base_commit, inp.theirs_commit, tuple(ops), fingerprint, tuple(warnings))


def _kind(path: str, structured: IFileMergeStrategy | None, *contents: bytes | None) -> ContentKind:
    if path.lower().endswith(".pdf") or is_binary(path, *contents):
        return ContentKind.binary
    if structured is not None and path.startswith(_STUDIO_PREFIX) and path.endswith(".json"):
        return ContentKind.json
    return ContentKind.text


def _plan_path(
    path: str, inp: MergeInput, engine: IMergeEngine, structured: IFileMergeStrategy | None
) -> MergeOp | None:
    base, ours, theirs = inp.base.get(path), inp.ours.get(path), inp.theirs.get(path)
    if same_content(path, ours, theirs) or same_content(path, base, theirs):
        return None
    kind = _kind(path, structured, base, ours, theirs)
    if same_content(path, base, ours):
        action = MergeAction.delete if theirs is None else MergeAction.take_theirs
        return MergeOp(path, kind, action, base=base, ours=ours, theirs=theirs)
    if ours is None or theirs is None:
        conflict = ConflictType.deleted_by_us if ours is None else ConflictType.deleted_by_them
        return MergeOp(path, kind, MergeAction.conflict, conflict, base=base, ours=ours, theirs=theirs)
    meta = inp.meta.get(path, MergeMeta())
    if kind is ContentKind.binary:
        return _merge_binary(path, base, ours, theirs, meta)
    if kind is ContentKind.json and structured is not None:
        return _merge_structured(path, base, ours, theirs, meta, structured, engine)
    return _merge_text(path, base, ours, theirs, engine)


def _merge_binary(path: str, base: bytes | None, ours: bytes, theirs: bytes, meta: MergeMeta) -> MergeOp:
    outcome = merge_binary(path, ours, theirs, meta)
    return MergeOp(
        path,
        ContentKind.binary,
        MergeAction.binary_newest,
        base=base,
        ours=ours,
        theirs=theirs,
        winner=outcome.winner,
        copy_path=outcome.copy_path,
        copy_content=outcome.copy_content,
    )


def _merge_structured(
    path: str,
    base: bytes | None,
    ours: bytes,
    theirs: bytes,
    meta: MergeMeta,
    strategy: IFileMergeStrategy,
    engine: IMergeEngine,
) -> MergeOp | None:
    decision = strategy.merge(path, base, ours, theirs, meta)
    if decision.as_text:
        return _merge_text(path, base, ours, theirs, engine)
    op = MergeOp(
        path,
        ContentKind.json,
        MergeAction.merged,
        base=base,
        ours=ours,
        theirs=theirs,
        fields=decision.fields,
        auto=decision.auto,
        warnings=decision.warnings,
        meta=meta,
    )
    if decision.conflict:
        conflict = ConflictType(decision.conflict_type or ConflictType.fields)
        return replace(op, action=MergeAction.conflict, conflict_type=conflict, merged=decision.content)
    if decision.deleted:
        return replace(op, action=MergeAction.delete)
    return _clean_result(op, decision.content)


def _merge_text(path: str, base: bytes | None, ours: bytes, theirs: bytes, engine: IMergeEngine) -> MergeOp | None:
    op = MergeOp(path, ContentKind.text, MergeAction.merged, base=base, ours=ours, theirs=theirs)
    if base is None:
        return _text_conflict(replace(op, conflict_type=ConflictType.add_add), single_hunk(ours, theirs))
    merge = merge_text(engine, ours, base, theirs)
    if merge.conflicted:
        return _text_conflict(replace(op, conflict_type=ConflictType.content), merge)
    return _clean_result(op, restore_text_style(merge.clean_content, ours))


def _text_conflict(op: MergeOp, merge: TextMerge) -> MergeOp:
    # Пока человек не решил, в итоге «моя» сторона: проект остаётся рабочим.
    placeholder = (
        op.ours if merge.opaque or op.ours is None else restore_text_style(render(merge, {}, HunkChoice.mine), op.ours)
    )
    return replace(op, action=MergeAction.conflict, text=merge, merged=placeholder)


def _clean_result(op: MergeOp, content: bytes | None) -> MergeOp | None:
    """Чистое слияние: если итог совпал с одной из сторон, это не слияние, а выбор стороны."""
    if content is None or same_content(op.path, content, op.ours):
        return None
    if same_content(op.path, content, op.theirs):
        return replace(op, action=MergeAction.take_theirs)
    return replace(op, merged=content)


def _resolve_collisions(ops: list[MergeOp], ours: Mapping[str, bytes]) -> tuple[list[MergeOp], list[str]]:
    """Имена, совпадающие после NFC без учёта регистра, на таких файловых системах — один файл.

    Побеждает имя, уже лежащее у меня (иначе первое по порядку). Добавленный чужой файл с
    другим написанием не пропадает: он ложится рядом под именем с хешем содержимого.
    """
    present = {path for path in ours if is_safe_path(path)}
    added = {op.path for op in ops if _adds_file(op)}
    present = (present - {op.path for op in ops if op.action is MergeAction.delete}) | added
    displaced: set[str] = set()
    for names in collision_groups(present):
        keeper = next((name for name in names if name in ours), names[0])
        displaced.update(name for name in names if name != keeper and name in added)
    if not displaced:
        return ops, []
    return [_beside(op) if op.path in displaced else op for op in ops], sorted(displaced)


_MAX_LISTED_CLASHES = 5


def ensure_tree_shape(plan: MergePlan, ours_paths: Iterable[str]) -> None:
    """Файл и каталог с одним именем в итоговом дереве не уживаются: запись упала бы посреди применения.

    Чужая ветка добавила файл `notes`, а у меня лежит `notes/x.txt` (или наоборот). Слияние само это не решит и
    не должно молча терять один из вариантов, поэтому синхронизация останавливается до записи на диск с понятным
    указанием, какие пути столкнулись: один из них нужно переименовать.

    `ours_paths` это все пути моего дерева, а не только затронутые планом: `MergeInput` их не несёт.
    """
    ops = plan.ops
    removed = {op.path for op in ops if op.action is MergeAction.delete}
    final = {path for path in ours_paths if is_safe_path(path)} - removed
    final |= {op.path for op in ops if op.action is not MergeAction.delete and (op.theirs is not None or op.merged)}
    parents = {parent for path in final for parent in _parents(path)}
    clashes = sorted(final & parents)
    if not clashes:
        return
    shown = ", ".join(clashes[:_MAX_LISTED_CLASHES])
    raise git_error(
        GitErrorCode.git_error,
        tail=localized_error(
            f"Файл и папка с одним именем не могут лежать рядом: {shown}. Переименуйте один из них и повторите",
            f"A file and a folder cannot share a name: {shown}. Rename one of them and try again",
        ),
        paths=clashes[:_MAX_LISTED_CLASHES],
    )


def _parents(path: str) -> list[str]:
    parts = path.split("/")
    return ["/".join(parts[:end]) for end in range(1, len(parts))]


def _adds_file(op: MergeOp) -> bool:
    return op.action is MergeAction.take_theirs and op.ours is None


def _beside(op: MergeOp) -> MergeOp:
    return replace(op, path=conflict_copy_name(op.path, op.theirs or b""))


def plan_fingerprint(ops: Iterable[MergeOp], *, base_commit: str | None, theirs_commit: str | None) -> str:
    """Отпечаток того, что решает человек: общая база, чужая вершина и «моё» с «чужим» в конфликтных путях.

    Правки и сборки в остальных файлах отпечаток не меняют, поэтому открытое слияние не
    устаревает, пока человек продолжает работать. Меняется он, когда пришёл новый коммит
    с чужой стороны или правился сам конфликтный файл.
    """
    digest = hashlib.sha256()
    digest.update(f"base={base_commit or '-'}\ntheirs={theirs_commit or '-'}\n".encode())
    for op in sorted((o for o in ops if o.needs_decision), key=lambda o: o.path):
        ours = blob_sha(op.ours) if op.ours is not None else "-"
        theirs = blob_sha(op.theirs) if op.theirs is not None else "-"
        conflict = op.conflict_type.value if op.conflict_type else "-"
        digest.update(f"{op.path}\0{op.action.value}\0{conflict}\0{ours}\0{theirs}\n".encode())
    return digest.hexdigest()


class _UnresolvedError(Exception):
    """Внутренний сигнал «решения по файлу нет»: наружу выходит как unresolved_conflicts со списком путей."""


def resolve_plan(
    plan: MergePlan, resolutions: Mapping[str, FileResolution], resolver: IFieldResolver | None = None
) -> list[FileWrite]:
    """Записи на диск по плану и решениям человека; решения по неконфликтным файлам игнорируются.

    Пока по конфликтному файлу решены не все участки или поля, это ошибка unresolved_conflicts
    со списком путей: на диск не пишется ничего. Решения по полям структурированного файла
    применяет `resolver`: он пересчитывает слияние файла с ними.
    """
    writes: list[FileWrite] = []
    unresolved: list[str] = []
    for op in plan.ops:
        try:
            writes.extend(_resolve_op(op, resolutions.get(op.path), resolver))
        except _UnresolvedError:
            unresolved.append(op.path)
    if unresolved:
        raise GitSyncError(GitErrorCode.unresolved_conflicts, paths=unresolved)
    return writes


def _write(op: MergeOp, content: bytes | None, path: str | None = None) -> FileWrite:
    """Запись файла; текст получает концы строк и BOM моего файла."""
    if content is not None and op.kind is not ContentKind.binary:
        content = restore_text_style(content, op.ours)
    return FileWrite(path or op.path, FileWriteKind.write, content)


def _resolve_op(op: MergeOp, resolution: FileResolution | None, resolver: IFieldResolver | None) -> list[FileWrite]:
    match op.action:
        case MergeAction.take_theirs:
            return [_write(op, op.theirs)]
        case MergeAction.delete:
            return [FileWrite(op.path, FileWriteKind.delete)]
        case MergeAction.merged:
            return [FileWrite(op.path, FileWriteKind.write, op.merged)]
        case MergeAction.binary_newest:
            return _resolve_newest(op, resolution)
        case MergeAction.conflict:
            return _resolve_conflict(op, resolution, resolver)


def _invalid(op: MergeOp) -> GitSyncError:
    return GitSyncError(GitErrorCode.invalid_resolution, path=op.path)


def _file_choice(op: MergeOp, resolution: FileResolution) -> FileChoice:
    if not isinstance(resolution, FileChoiceResolution) or resolution.choice not in op.allowed_choices():
        raise _invalid(op)
    return resolution.choice


def _take(op: MergeOp, choice: FileChoice) -> list[FileWrite]:
    """Файл целиком: моё остаётся как есть, чужое пишется или удаляет файл."""
    if choice is FileChoice.mine:
        return []
    if op.theirs is None:
        return [FileWrite(op.path, FileWriteKind.delete)]
    return [_write(op, op.theirs)]


def _resolve_newest(op: MergeOp, resolution: FileResolution | None) -> list[FileWrite]:
    choice = FileChoice.newest if resolution is None else _file_choice(op, resolution)
    if choice is not FileChoice.newest:
        return _take(op, choice)
    writes = [_write(op, op.theirs)] if op.winner is MergeSide.theirs else []
    if op.copy_path is not None and op.copy_content is not None:
        writes.append(FileWrite(op.copy_path, FileWriteKind.write, op.copy_content))
    return writes


def _resolve_conflict(
    op: MergeOp, resolution: FileResolution | None, resolver: IFieldResolver | None
) -> list[FileWrite]:
    if resolution is None:
        raise _UnresolvedError
    if isinstance(resolution, FieldsResolution) and op.fields:
        return _resolve_fields(op, resolution, resolver)
    text = op.kind is ContentKind.text
    if isinstance(resolution, HunksResolution) and text:
        return _resolve_hunks(op, resolution)
    if isinstance(resolution, TextResolution) and text:
        return _resolved_text(op, resolution.content.encode())
    return _take(op, _file_choice(op, resolution))


def _resolve_fields(op: MergeOp, resolution: FieldsResolution, resolver: IFieldResolver | None) -> list[FileWrite]:
    if resolver is None:
        raise _invalid(op)
    choices = {pointer: decision.choice for pointer, decision in resolution.fields.items()}
    try:
        decision = resolver.resolve(op.path, op.base, op.ours, op.theirs, op.meta, choices)
    except InvalidFieldChoiceError as exc:
        raise _invalid(op) from exc
    if decision.conflict or decision.content is None:
        raise _UnresolvedError
    if same_content(op.path, decision.content, op.ours):
        return []
    return [FileWrite(op.path, FileWriteKind.write, decision.content)]


def _resolve_hunks(op: MergeOp, resolution: HunksResolution) -> list[FileWrite]:
    keys = {hunk.key for hunk in op.hunks}
    if op.text is None or not keys or not set(resolution.hunks) <= keys:
        raise _invalid(op)
    if any(d.choice is HunkChoice.custom and d.text is None for d in resolution.hunks.values()):
        raise _invalid(op)
    if keys - set(resolution.hunks):
        raise _UnresolvedError
    return _resolved_text(op, render(op.text, resolution.hunks))


def _resolved_text(op: MergeOp, content: bytes) -> list[FileWrite]:
    """Текст, собранный человеком: маркеры конфликта в историю не пускаем, если их не было во входах."""
    inputs = (op.base, op.ours, op.theirs)
    if has_hse_markers(content) and not any(has_hse_markers(item) for item in inputs if item is not None):
        raise GitSyncError(GitErrorCode.unresolved_markers, path=op.path)
    content = restore_text_style(content, op.ours)
    if same_content(op.path, content, op.ours):
        return []
    return [FileWrite(op.path, FileWriteKind.write, content)]
