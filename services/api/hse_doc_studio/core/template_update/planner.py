"""Решение обновления по каждому файлу: чистая функция от трёх деревьев.

Для пути из базы (B0) или нового шаблона (B1), где шаблон что-то меняет:

    B0 == B1                      шаблон файл не менял — ничего не делаем
    O == B0                       пользователь не правил — берём B1 (update / add / delete)
    O == B1                       у пользователя уже то же — ничего не делаем
    O нет, B0 был                 пользователь удалил — не возвращаем (user_deleted)
    правили обе стороны, текст    трёхстороннее слияние: merge или conflict
    правили обе стороны, бинарник conflict, выбор целиком
    шаблон убрал правленый файл   файл остаётся (orphan)

Сравнение — по смыслу (core.template_update.text): концы строк, BOM и упаковка
zip правкой не считаются.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace

from hse_doc_studio.core.enums import TemplateFileAction
from hse_doc_studio.core.template_update.entities import FileOp
from hse_doc_studio.core.template_update.text import is_binary, normalize_text, restore_text_style, same_content


@dataclass(frozen=True)
class MergeOutcome:
    content: bytes
    conflicts: int


# (ours, base, theirs) → итог; концы строк уже приведены к LF.
MergeFn = Callable[[bytes, bytes, bytes], MergeOutcome]


@dataclass(frozen=True)
class PlanInput:
    base: Mapping[str, bytes]
    theirs: Mapping[str, bytes]
    # Содержимое файлов проекта на диске; отсутствующий ключ — файла нет.
    ours: Mapping[str, bytes]
    ignored: frozenset[str] = frozenset()
    approximate: frozenset[str] = frozenset()


def plan_files(inp: PlanInput, merge: MergeFn, doc_of: Callable[[str], str | None] = lambda _p: None) -> list[FileOp]:
    """Операции по всем путям, где шаблон что-то меняет, в порядке путей."""
    ops: list[FileOp] = []
    for path in sorted(set(inp.base) | set(inp.theirs)):
        op = _plan_path(path, inp, merge)
        if op is not None:
            ops.append(replace(op, doc_id=doc_of(path), approximate_base=path in inp.approximate))
    return ops


def _plan_path(path: str, inp: PlanInput, merge: MergeFn) -> FileOp | None:
    base, theirs, ours = inp.base.get(path), inp.theirs.get(path), inp.ours.get(path)
    if same_content(path, base, theirs):
        return None
    binary = is_binary(path, base, theirs, ours)
    if path in inp.ignored:
        return FileOp(path, TemplateFileAction.ignored, binary, base=base, ours=ours, theirs=theirs)
    if theirs is None:
        return _plan_removed(path, binary, base, ours)
    if ours is None:
        return _plan_missing(path, binary, base, theirs)
    return _plan_present(path, binary, base, ours, theirs, merge)


def _plan_present(
    path: str, binary: bool, base: bytes | None, ours: bytes, theirs: bytes, merge: MergeFn
) -> FileOp | None:
    """Файл есть и на диске, и в новом шаблоне."""
    if same_content(path, ours, theirs):
        return None
    if base is not None and same_content(path, ours, base):
        return FileOp(path, TemplateFileAction.update, binary, base=base, ours=ours, theirs=theirs)
    return _plan_both_changed(path, binary, base, ours, theirs, merge)


def _plan_missing(path: str, binary: bool, base: bytes | None, theirs: bytes) -> FileOp:
    """Файла на диске нет: новый файл шаблона или удалённый пользователем."""
    if base is None:
        return FileOp(path, TemplateFileAction.add, binary, theirs=theirs)
    return FileOp(path, TemplateFileAction.user_deleted, binary, base=base, theirs=theirs)


def _plan_removed(path: str, binary: bool, base: bytes | None, ours: bytes | None) -> FileOp | None:
    if ours is None:
        return None
    if same_content(path, ours, base):
        return FileOp(path, TemplateFileAction.delete, binary, base=base, ours=ours)
    return FileOp(path, TemplateFileAction.orphan, binary, base=base, ours=ours)


def _plan_both_changed(
    path: str, binary: bool, base: bytes | None, ours: bytes, theirs: bytes, merge: MergeFn
) -> FileOp:
    if binary:
        return FileOp(path, TemplateFileAction.conflict, binary, base=base, ours=ours, theirs=theirs)
    outcome = merge(normalize_text(ours), normalize_text(base or b""), normalize_text(theirs))
    merged = restore_text_style(outcome.content, ours)
    # Новый файл шаблона на месте своего файла пользователя: общей базы нет, и
    # «чистое» слияние двух чужих текстов было бы склейкой — только решение человека.
    conflicts = outcome.conflicts if base is not None else max(outcome.conflicts, 1)
    action = TemplateFileAction.conflict if conflicts else TemplateFileAction.merge
    return FileOp(path, action, binary, conflicts=conflicts, base=base, ours=ours, theirs=theirs, merged=merged)


def plan_fingerprint(ops: Iterable[FileOp], *, to_version: str, base_digest: str, ignored: Iterable[str] = ()) -> str:
    """Отпечаток того, что видел пользователь: применение сверяет его с диском.

    Входят только пути операций (правка файла, который шаблон не меняет, план
    не портит), содержимое «моего» по ним, целевая версия, содержимое базы и
    снятые с отслеживания пути.
    """
    digest = hashlib.sha256()
    digest.update(f"to={to_version}\nbase={base_digest}\n".encode())
    for path in sorted(ignored):
        digest.update(f"ignored={path}\n".encode())
    for op in sorted(ops, key=lambda o: o.path):
        ours = hashlib.sha256(op.ours).hexdigest() if op.ours is not None else "-"
        digest.update(f"{op.path}\0{op.action.value}\0{ours}\n".encode())
    return digest.hexdigest()
