"""Профили сдачи, пункты и порядок маршрута версии шаблона в Студии шаблонов (template-studio.md, 5.5, 5.6, 5.8).

Срез T13: автор пака правит формой `pack_submission.profiles` (название, описание, подсказка срока, пункты с
подписями и способами, `extra_items`, порядок маршрута точки `signing_route`, пресет `signing_slots` с условием
`when` и отметкой `optional`) и порядок версии `signatures.route`. Студия пишет это в `version.yaml` точечными
правками (D11): меняется только фрагмент записи, комментарии, порядок и незнакомые форме ключи остаются.

Модель (`VersionSubmission`) это записи пака как их видит лоадер, но с индексами в списках YAML: битая запись
видна с причиной (`error`), индексы остальных не сдвигаются. Правки (`SubmissionOp`) структурные: профиль целиком
(добавить, убрать, переставить), шапка профиля, запись одного из трёх списков профиля по индексу, порядок маршрута.

«Маршрут в этой комбинации» (`ProfileRoute`) считает тот же код, что у проекта (`route_preset`, `default_route`),
на синтетическом проекте предпросмотра: кто подписывает по шагам, какие подписи шаблон добавил по условию, какие
условие не пропустило и какие пункты в этой комбинации не сдаются.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

# Набор правок за один запрос: формы шлют одну-две, предел только от мусорных запросов.
MAX_SUBMISSION_OPS = 50
# Персоны условия `when` (signing-route.md, 15.3) и способы подписи пункта, как у лоадера.
WHEN_PERSONS: tuple[str, ...] = ("supervisor", "co_supervisor", "academic_supervisor")
WHEN_ROLES: tuple[str, ...] = ("university", "company")
SIGN_METHODS: tuple[str, ...] = ("image", "detached", "pades")
KINDS: tuple[str, ...] = ("research", "project")


class SubmissionEditError(ValueError):
    """Правку нельзя применить: профиля или записи нет, значение не читается лоадером или схемой."""


class SubmissionList(StrEnum):
    """Списки профиля, которые форма правит по записи."""

    items = "items"
    extra_items = "extra_items"
    signing_slots = "signing_slots"


class SubmissionOpKind(StrEnum):
    # Новый профиль в конец списка: `head` (id, name, description), пунктов пока нет.
    add_profile = "add_profile"
    # Шапка профиля `profile`: id, name, description, deadline_hint (None убирает подсказку).
    set_profile = "set_profile"
    remove_profile = "remove_profile"
    # Профиль `profile` на место `to` (индекс в итоговом списке).
    move_profile = "move_profile"
    # Порядок маршрута точки (`signing_route`); `steps` None убирает ключ: действует порядок версии.
    set_profile_route = "set_profile_route"
    # Запись списка `entries` профиля: в конец, по индексу `index`, убрать, переставить на `to`.
    add_entry = "add_entry"
    set_entry = "set_entry"
    remove_entry = "remove_entry"
    move_entry = "move_entry"
    # Порядок версии (`signatures.route`); `steps` None убирает ключ: действует встроенный порядок.
    set_route = "set_route"


@dataclass(frozen=True)
class ProfileHead:
    id: str
    name: Mapping[str, str]
    description: Mapping[str, str]
    deadline_hint: Mapping[str, str] | None = None


@dataclass(frozen=True)
class SubmissionOp:
    op: SubmissionOpKind
    profile: int | None = None
    head: ProfileHead | None = None
    entries: SubmissionList | None = None
    index: int | None = None
    to: int | None = None
    # Запись списка в виде модели (`ItemEntry`, `ExtraEntry`, `SlotEntry` как словарь полей формы).
    value: Mapping[str, Any] | None = None
    steps: tuple[tuple[str, ...], ...] | None = None


@dataclass(frozen=True)
class WhenCondition:
    person: str
    role: str | None = None


@dataclass(frozen=True)
class ItemEntry:
    """Пункт точки: документ, подписи (слоты каталога), способы по слоту, NDA и виды работы (пусто: оба)."""

    doc_id: str
    signatures: tuple[str, ...] = ()
    methods: tuple[tuple[str, tuple[str, ...]], ...] = ()
    skip_if_nda: bool = False
    supported_kinds: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtraEntry:
    """Файл сверх документов, который едет в пакет: анкета (`.hse-studio/forms/<id>.json`) или другой файл."""

    source: str
    output_name: str = ""
    format: str | None = None
    supported_kinds: tuple[str, ...] = ()


@dataclass(frozen=True)
class SlotEntry:
    """Запись пресета точки: пара «документ, слот», условие для слота сверх точки, отметка «необязательна»."""

    doc_id: str
    slot_id: str
    when: WhenCondition | None = None
    optional: bool = False


@dataclass(frozen=True)
class Indexed[T]:
    """Запись списка YAML с индексом; `entry` None, если лоадер её не читает (`error` почему)."""

    index: int
    entry: T | None
    error: str | None = None


@dataclass(frozen=True)
class ProfileView:
    index: int
    id: str | None
    name: Mapping[str, str]
    description: Mapping[str, str]
    deadline_hint: Mapping[str, str] | None
    items: tuple[Indexed[ItemEntry], ...]
    extra_items: tuple[Indexed[ExtraEntry], ...]
    signing_route: tuple[tuple[str, ...], ...] | None
    signing_slots: tuple[Indexed[SlotEntry], ...]
    # Профиль не читается лоадером (нет id, битые пункты): форма показывает причину и ведёт в «Исходник».
    error: str | None = None


@dataclass(frozen=True)
class SlotInfo:
    id: str
    label: Mapping[str, str]
    applies_to: tuple[str, ...]
    required: bool
    per_author: bool


@dataclass(frozen=True)
class FormInfo:
    """Анкета версии для `extra_items`: источник в проекте, имя и формат файла в пакете, `required_for_pack`."""

    id: str
    title: Mapping[str, str]
    source: str
    output_name: str
    format: str | None
    required_for_pack: bool


@dataclass(frozen=True)
class VersionSubmission:
    documents: tuple[str, ...]
    supported_kinds: tuple[str, ...]
    has_nda: bool
    slots: tuple[SlotInfo, ...]
    forms: tuple[FormInfo, ...]
    # Порядок версии `signatures.route` (None: ключа нет, действует встроенный порядок).
    route: tuple[tuple[str, ...], ...] | None
    builtin_route: tuple[tuple[str, ...], ...]
    profiles: tuple[ProfileView, ...]


# ── «Маршрут в этой комбинации» ─────────────────────────────────────────────


class PairSource(StrEnum):
    # Подпись требует пункт точки.
    point = "point"
    # Слот сверх точки, который шаблон добавил (`signing_slots`, условие выполнено или его нет).
    preset = "preset"


@dataclass(frozen=True)
class RoutePerson:
    """Участник шага: персона маршрута (слаг автора или роль руководителя), роль и имя из набора данных."""

    persona: str
    role: str
    name: str


@dataclass(frozen=True)
class RoutePair:
    """Подпись маршрута: документ (id определения), слот каталога, чья она, откуда и необязательна ли."""

    doc_id: str
    slot_id: str
    persona: str
    source: PairSource
    optional: bool
    when: WhenCondition | None = None


@dataclass(frozen=True)
class SkippedPair:
    doc_id: str
    slot_id: str
    when: WhenCondition | None


@dataclass(frozen=True)
class ProfileRoute:
    """Маршрут точки на синтетическом проекте комбинации (профиль по id: битый профиль лоадер отбрасывает).

    `steps` шаги людьми (пусто: подписи точке не нужны); `pairs` подписи маршрута; `skipped` слоты сверх точки,
    которые условие не пропустило; `may_add` подписи, которые автор проекта может включить сам; `items_off`
    документы пунктов, которые в этой комбинации не сдаются (вид работы, NDA, документа нет). `order_source` откуда
    порядок: `profile` (`signing_route`), `version` (`signatures.route`) или `builtin`.
    """

    id: str
    steps: tuple[tuple[RoutePerson, ...], ...]
    pairs: tuple[RoutePair, ...]
    skipped: tuple[SkippedPair, ...]
    may_add: tuple[tuple[str, str], ...]
    items_off: tuple[str, ...]
    order_source: str
    preset: bool


@dataclass(frozen=True)
class SubmissionRoutes:
    example: str
    combination: Mapping[str, str]
    profiles: tuple[ProfileRoute, ...]
