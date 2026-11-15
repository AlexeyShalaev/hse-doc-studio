"""Мастер «Новая версия» Студии шаблонов (docs/design/template-studio.md, раздел 7; срез T10): сущности.

- `TemplateRef` шаблон пака в рабочем пространстве, `NewVersionOptions` выбор базы и номера для копии;
- `VersionState` живой класс черновика по классификатору (7.2), предложенные номера, заметки и черновик заметок
  из отчёта (7.4), выпущенность и правка мимо Студии (7.3);
- входы и итоги шагов: заметки, новый номер, перенос правок, выпуск.

Выпущенной версия считается по реестру базовой ветки (D10): мастер выпускает в рабочей ветке, выпущенной версия
становится после слияния PR.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field

from hse_doc_studio.core.enums import TemplateUpdateClass as UpdateClass
from hse_doc_studio.core.pack_studio.paths import TEMPLATES_DIR, VERSIONS_DIR, VersionRef

LANGS = ("ru", "en")
Localized = Mapping[str, str]
LocalizedList = Mapping[str, tuple[str, ...]]


@dataclass(frozen=True)
class TemplateRef:
    pack: str
    template: str

    @property
    def dir(self) -> str:
        return f"{self.pack}/{TEMPLATES_DIR}/{self.template}"

    def version(self, version: str) -> VersionRef:
        return VersionRef(self.pack, self.template, version)

    def version_dir(self, version: str) -> str:
        return f"{self.dir}/{VERSIONS_DIR}/{version}"


@dataclass(frozen=True)
class VersionChoice:
    """Версия шаблона в списке баз: статус манифеста, выпущена ли в базе, внесена ли в реестр рабочего дерева."""

    version: str
    status: str | None
    released: bool
    registered: bool
    modified: bool = False


@dataclass(frozen=True)
class NewVersionOptions:
    template: TemplateRef
    versions: tuple[VersionChoice, ...]
    # База по умолчанию: последняя выпущенная (нет выпущенных: последняя версия).
    default_base: str | None
    # Номер новой версии по классу: свободный и после последней известной (на диске и в базе).
    numbers: Mapping[UpdateClass, str]
    default_version: str | None = None


@dataclass(frozen=True)
class ReasonView:
    """Причина класса из отчёта классификатора (`core/template_diff.ChangeReason`) для интерфейса."""

    code: str
    path: str
    change: str
    minimum: UpdateClass
    suggested: UpdateClass
    hard: bool
    exception: bool
    message: Localized


@dataclass(frozen=True)
class VersionState:
    """Состояние версии в мастере: черновик с живым классом или выпущенная (только база для копии, 7.3)."""

    ref: VersionRef
    status: str | None
    # Выпущена в базовой ветке (D10): каталог только для чтения.
    released: bool
    # Каталог выпущенной версии отличается от выпуска: правили мимо Студии или номер выпущен в базе раньше (7.3, 4.3).
    modified: bool
    # Внесена в реестр рабочего дерева (выпуск в ветке, PR ещё не слит).
    registered: bool
    # С какой версией сверяется класс; None у первой версии шаблона.
    base: str | None
    minimum: UpdateClass | None
    suggested: UpdateClass | None
    by_number: UpdateClass | None
    # `release.kind` и `release.note` манифеста.
    declared: UpdateClass | None
    note: str | None
    # Номер не мягче минимума по жёстким правилам (и `release.kind` тоже).
    number_ok: bool
    headline: Localized
    reasons: tuple[ReasonView, ...]
    # Номер черновика по каждому классу (свободный, после последней известной версии; свой номер, если подходит).
    numbers: Mapping[UpdateClass, str]
    changes: LocalizedList
    breaking_changes: LocalizedList
    # Черновик заметок из отчёта классификатора (7.4): пункты парами ru и en.
    draft_changes: LocalizedList
    draft_breaking: LocalizedList
    # Номер для «Перенести правки в новую версию» (у изменённой выпущенной версии).
    move_to: str | None = None
    # Ошибка разбора: класс не посчитан (битый YAML), текст для «Проблем».
    error: str | None = None
    is_default: bool = False
    # Выпуск записан в ветке, а каталог после него правили: выпустить заново (запись пересчитается).
    release_outdated: bool = False


@dataclass(frozen=True)
class VersionNotesInput:
    """Заметки версии (7.4) и объяснение класса `release.note` (7.2): `None` у поля значит «не менять»."""

    changes: LocalizedList | None = None
    breaking_changes: LocalizedList | None = None
    # Пустая строка убирает объяснение.
    note: str | None = None


@dataclass(frozen=True)
class CreatedVersion:
    ref: VersionRef
    base: str
    update_class: UpdateClass | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class MovedVersion:
    """Итог «нового номера» черновика или «Перенести правки в новую версию»."""

    ref: VersionRef
    previous: str
    # Запись выпуска в ветке снята: версия снова черновик.
    unreleased: bool = False
    # Выпущенный каталог возвращён к выпуску (git); у папки возвращать нечем.
    restored: bool = False
    edited: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReleasedVersionView:
    ref: VersionRef
    digest: str
    kind: UpdateClass | None
    previous: str | None
    replaced: bool
    default_set: bool
    edited: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class BaseRegistry:
    """Выпущенные в базе версии шаблона: версия -> дайджест, и текст реестра базы, если он прочитан (git)."""

    versions: Mapping[str, str] = field(default_factory=dict)
    text: str | None = None
    # Сверять запись выпуска с базовой веткой (git): у папки база это сам реестр на диске.
    from_git: bool = False
