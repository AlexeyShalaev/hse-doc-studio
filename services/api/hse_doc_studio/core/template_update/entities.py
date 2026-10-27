"""Обновление проекта на новую версию шаблона: база, план, история.

Три дерева файлов одного проекта:

* база (B0) — чистый рендер ТЕКУЩЕЙ версии шаблона с данными проекта, то, от
  чего пользователь начинал править (хранится в скрытом git, `refs/hse/template/<версия>`);
* «моё» (O) — файлы на диске;
* шаблон (B1) — чистый рендер НОВОЙ версии с текущими данными проекта.

План — решение по каждому файлу, где шаблон что-то меняет (core.template_update.planner).
Применение исполняет ровно план, отпечаток которого видел пользователь.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from hse_doc_studio.core.enums import (
    ConflictResolution,
    TemplateBaseProvenance,
    TemplateFileAction,
    TemplateUpdateClass,
)
from hse_doc_studio.core.template_update.text import restore_text_style


@dataclass(frozen=True)
class TemplateBase:
    """Чистый рендер версии шаблона для проекта — база трёхстороннего слияния."""

    version: str
    # Путь от корня проекта (POSIX) → содержимое.
    files: Mapping[str, bytes]
    provenance: TemplateBaseProvenance
    # Коммит в `refs/hse/template/<версия>`; None — база ещё не сохранена.
    commit: str | None = None
    # Файлы, для которых база восстановлена приблизительно (рендер с текущими
    # данными): их «правки» могут оказаться вшитыми данными, а не правками.
    approximate_paths: frozenset[str] = frozenset()


@dataclass(frozen=True)
class FileOp:
    """Решение обновления по одному файлу."""

    path: str
    action: TemplateFileAction
    binary: bool
    doc_id: str | None = None
    # Число конфликтных участков текстового слияния (0 — нет или не текст).
    conflicts: int = 0
    base: bytes | None = None
    ours: bytes | None = None
    theirs: bytes | None = None
    # Итог слияния: чистый для merge, с маркерами для текстового conflict.
    merged: bytes | None = None
    approximate_base: bool = False

    @property
    def needs_decision(self) -> bool:
        return self.action == TemplateFileAction.conflict

    def allowed_resolutions(self) -> tuple[ConflictResolution, ...]:
        if not self.needs_decision:
            return ()
        if self.binary or self.merged is None:
            return (ConflictResolution.mine, ConflictResolution.theirs)
        return (ConflictResolution.mine, ConflictResolution.theirs, ConflictResolution.markers)


class FileWriteKind(StrEnum):
    write = "write"
    delete = "delete"


@dataclass(frozen=True)
class FileWrite:
    """Что применение делает с файлом на диске (после выбора по конфликтам)."""

    path: str
    kind: FileWriteKind
    content: bytes | None = None
    # Файл записан с маркерами конфликта — его надо доразрешить руками.
    with_markers: bool = False


def resolve_op(op: FileOp, resolution: ConflictResolution | None) -> FileWrite | None:
    """Запись на диск для операции плана; None — файл не трогаем."""
    match op.action:
        case TemplateFileAction.update:
            # Файл пользователя не правлен, но концы строк у него могут быть свои.
            content = op.theirs if op.binary or op.theirs is None else restore_text_style(op.theirs, op.ours)
            return FileWrite(op.path, FileWriteKind.write, content)
        case TemplateFileAction.add:
            return FileWrite(op.path, FileWriteKind.write, op.theirs)
        case TemplateFileAction.merge:
            return FileWrite(op.path, FileWriteKind.write, op.merged)
        case TemplateFileAction.delete:
            return FileWrite(op.path, FileWriteKind.delete)
        case TemplateFileAction.conflict:
            return _resolve_conflict(op, resolution or ConflictResolution.mine)
        case _:
            return None


def _resolve_conflict(op: FileOp, resolution: ConflictResolution) -> FileWrite | None:
    if resolution not in op.allowed_resolutions() or resolution == ConflictResolution.mine:
        return None
    if resolution == ConflictResolution.theirs:
        if op.theirs is None:
            return FileWrite(op.path, FileWriteKind.delete)
        return FileWrite(op.path, FileWriteKind.write, op.theirs)
    return FileWrite(op.path, FileWriteKind.write, op.merged, with_markers=True)


class UpdateWarningCode(StrEnum):
    # База восстановлена приблизительно: часть «правок» — вшитые данные.
    approximate_base = "approximate_base"
    # Обновление меняет исходники документа, PDF которого зафиксирован на подпись
    # или уже подписан: после пересборки подписи устареют.
    frozen_documents = "frozen_documents"
    # Шаблон менял файлы документа с включёнными размещениями подписей.
    signature_placements = "signature_placements"
    # Командный проект: проекты сокомандников обновляются отдельно.
    team_project = "team_project"


@dataclass(frozen=True)
class UpdateWarning:
    code: UpdateWarningCode
    doc_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class UpdatePlan:
    from_version: str
    to_version: str
    update_class: TemplateUpdateClass | None
    provenance: TemplateBaseProvenance
    base_commit: str | None
    ops: tuple[FileOp, ...]
    fingerprint: str
    warnings: tuple[UpdateWarning, ...] = ()

    @property
    def counts(self) -> dict[TemplateFileAction, int]:
        return dict(Counter(op.action for op in self.ops))

    @property
    def conflicts(self) -> tuple[FileOp, ...]:
        return tuple(op for op in self.ops if op.needs_decision)

    @property
    def is_clean(self) -> bool:
        return not self.conflicts

    def op(self, path: str) -> FileOp | None:
        return next((op for op in self.ops if op.path == path), None)


@dataclass(frozen=True)
class TemplateUpdateRecord:
    """Запись истории обновлений проекта (`.hse-studio/template.json`)."""

    id: str
    from_version: str
    to_version: str
    at: str  # ISO 8601, UTC
    pre_commit: str
    commit: str | None = None
    # Файлы, записанные с маркерами конфликта.
    markers: tuple[str, ...] = ()
    reverted: bool = False
    # Обновление отменой другого (id отменённого).
    reverts: str | None = None


@dataclass(frozen=True)
class TemplateTrackingState:
    """Отношение проекта к шаблону, которое переживает обновления."""

    # Файлы, которые пользователь снял с отслеживания: обновления их не трогают.
    ignored: frozenset[str] = frozenset()
    history: tuple[TemplateUpdateRecord, ...] = ()

    def last_applied(self) -> TemplateUpdateRecord | None:
        for record in reversed(self.history):
            if not record.reverted and record.reverts is None:
                return record
        return None


class UpdateJournalState(StrEnum):
    applying = "applying"


class UpdateJournalKind(StrEnum):
    # Обновление (или отмена обновления) шаблона.
    template = "template"
    # Применение слияния с удалённым репозиторием (Git-синхронизация).
    sync = "sync"


@dataclass(frozen=True)
class UpdateJournal:
    """Журнал идущего обновления (`.hse-studio/update/journal.json`, вне истории).

    Перед первой записью каждый файл, который обновление меняет или удаляет
    (включая `project.json` и `template.json`), копируется в
    `.hse-studio/update/backup/`. Откат — вернуть копии и удалить добавленные
    файлы; он не зависит ни от git, ни от того, отслеживается ли файл историей.
    Журнал переживает падение процесса: при старте Студия по нему откатывает
    проект или, если коммит обновления уже сделан, доводит обновление.

    Журнал один на проект и общий для обоих видов (`kind`): так проект остаётся
    «только для чтения» и при применении слияния, а обновление шаблона не
    стартует поверх синхронизации и наоборот. Журналы старой Студии без `kind`
    читаются как журналы обновления шаблона.
    """

    id: str
    state: UpdateJournalState
    from_version: str
    to_version: str
    pre_commit: str
    # База целевой версии, на которую после коммита передвинется ссылка.
    base_commit: str | None
    # Файлы, существовавшие до обновления и затронутые им (их копии — в backup).
    touched_paths: tuple[str, ...] = ()
    # Файлы, которых до обновления не было: при откате их удаляют.
    added_paths: tuple[str, ...] = ()
    started_at: str = ""
    # Это отмена обновления с таким id (None — обычное обновление).
    reverts: str | None = None
    kind: UpdateJournalKind = UpdateJournalKind.template
    # Только sync: коммит удалённой ветки, с которым сливаемся. Если после
    # падения HEAD равен ему, быстрая перемотка уже состоялась.
    merge_parent: str | None = None
    # Только sync: id операции; он же в трейлере `Hse-Sync` коммита слияния.
    sync_id: str | None = None
