"""План трёхстороннего слияния двух коммитов: решение по каждому пути.

Планировщик чистый: на входе содержимое файлов трёх деревьев (база, моё, чужое), на выходе
неизменяемый план. На диск и в историю ничего не пишется, пока конфликты не решены.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from hse_doc_studio.core.git_sync.entities import SyncWarning
from hse_doc_studio.core.git_sync.merge.choices import FileChoice
from hse_doc_studio.core.git_sync.merge.jsonmerge import AutoField, FieldConflict
from hse_doc_studio.core.git_sync.merge.text import TextHunk, TextMerge
from hse_doc_studio.core.git_sync.protocols import MergeMeta


class ContentKind(StrEnum):
    text = "text"
    json = "json"
    binary = "binary"


class MergeSide(StrEnum):
    ours = "ours"
    theirs = "theirs"


class MergeAction(StrEnum):
    """Что слияние делает с файлом; значения auto-действий совпадают с AutoAction контракта."""

    take_theirs = "take_theirs"
    delete = "delete"
    merged = "merged"
    binary_newest = "binary_newest"
    conflict = "conflict"


class ConflictType(StrEnum):
    content = "content"  # текст: правили одни и те же места
    fields = "fields"  # структурированный файл: правили одни и те же поля
    deleted_by_us = "deleted_by_us"  # я удалил файл, а в чужой ветке его правили
    deleted_by_them = "deleted_by_them"  # в чужой ветке файл удалён, а я его правил
    add_add = "add_add"  # оба добавили файл с одним путём и разным текстом
    signature_group = "signature_group"  # подписанный PDF и подписи к нему правили обе стороны
    invalid_result = "invalid_result"  # итог слияния состояния не разбирается: решает человек


@dataclass(frozen=True)
class MergeOp:
    """Решение слияния по одному пути."""

    path: str
    kind: ContentKind
    action: MergeAction
    conflict_type: ConflictType | None = None
    base: bytes | None = None
    ours: bytes | None = None
    theirs: bytes | None = None
    # Итог слияния: чистый результат или, для конфликта, «моя» версия с неспорными чужими правками.
    merged: bytes | None = None
    # Разобранное слияние текста; у файла, который нельзя разобрать на участки, участков нет.
    text: TextMerge | None = None
    # Бинарный файл с обеими правками: чья версия новее и куда сохранить проигравшую.
    winner: MergeSide | None = None
    copy_path: str | None = None
    copy_content: bytes | None = None
    # Структурированный файл: спорные поля, решённые правилами поля и предупреждения. `meta` нужен, чтобы
    # повторное слияние с решениями человека выбрало тех же победителей, что и первое.
    fields: tuple[FieldConflict, ...] = ()
    auto: tuple[AutoField, ...] = ()
    warnings: tuple[SyncWarning, ...] = ()
    meta: MergeMeta = MergeMeta()

    @property
    def needs_decision(self) -> bool:
        return self.action is MergeAction.conflict

    @property
    def hunks(self) -> tuple[TextHunk, ...]:
        return self.text.hunks if self.text is not None else ()

    def allowed_choices(self) -> tuple[FileChoice, ...]:
        """Решения по файлу целиком; пусто, если решать нечего."""
        if self.action is MergeAction.conflict:
            return (FileChoice.mine, FileChoice.theirs)
        if self.action is MergeAction.binary_newest:
            return (FileChoice.newest, FileChoice.mine, FileChoice.theirs)
        return ()

    @property
    def default_choice(self) -> FileChoice | None:
        return FileChoice.newest if self.action is MergeAction.binary_newest else None


@dataclass(frozen=True)
class MergePlan:
    base_commit: str | None
    theirs_commit: str | None
    ops: tuple[MergeOp, ...]
    fingerprint: str
    warnings: tuple[SyncWarning, ...] = ()

    @property
    def conflicts(self) -> tuple[MergeOp, ...]:
        return tuple(op for op in self.ops if op.needs_decision)

    @property
    def is_clean(self) -> bool:
        return not self.conflicts

    def op(self, path: str) -> MergeOp | None:
        return next((op for op in self.ops if op.path == path), None)
