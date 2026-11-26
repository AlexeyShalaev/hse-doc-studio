"""Места подписей и метки даты версии шаблона в Студии шаблонов (docs/design/template-studio.md, 5.6, срез T9).

Автор пака ставит рамки мышкой на PDF предпросмотра, а Студия пишет их в `version.yaml` версии точечными правками
(D11): `placements` документа, `default_placement` слота и `default_dates` документа. Записи бывают в мм и на якоре
шаблона (signing-route.md, 15.17.7); у сборки предпросмотра есть якоря, если документ их ставит.

Модель (`VersionPlaces`) это каталог слотов версии с записями пака как их читает лоадер и, для документа сборки,
рамки этой сборки: место документа или общее место слота, разрешённое по якорям сборки (`resolve_place`), и метки
даты с индексом в списке YAML (битая метка в модели не видна, но индексы остальных не сдвигаются).

Правки (`PlaceOp`) высокоуровневые: «место слота на документе такое-то», «убрать место», «сделать местом по
умолчанию», «привязать к строке шаблона» и «отвязать», метки даты по индексу. Как они ложатся в YAML (запись на
якоре относительно линии, запасное место, порядок ключей), решает адаптер порта `IPackPlaces`.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from hse_doc_studio.core.catalog import PackDate, PackPlace, SignatureDefaultDate, SignatureDefaultPlacement
from hse_doc_studio.core.enums import AnchorState, DateMarkAlign, DateMarkFormat
from hse_doc_studio.core.signatures.anchors import AnchorKind, split_author_name

# Набор правок за один запрос: столько рамок автор не двигает и за час.
MAX_PLACE_OPS = 50


class PlaceOpKind(StrEnum):
    # Место слота на документе (`doc`) или общее место слота (`doc` пусто): рамка `box` этой сборки.
    set_place = "set_place"
    # Убрать место документа: документ получает общее место слота.
    remove_place = "remove_place"
    # Место документа становится общим местом слота (`default_placement`), запись документа уходит.
    make_default = "make_default"
    # Место встаёт на строку шаблона (якорь с id слота в сборке) относительно линии; запасное место это рамка сейчас.
    bind_anchor = "bind_anchor"
    # Место на якоре становится местом в мм по рамке этой сборки (или по запасному месту).
    unbind_anchor = "unbind_anchor"
    # Метка даты документа: в мм (`mark`) или на строке даты (`anchor`, «слот.часть»).
    add_date = "add_date"
    # Метка даты по индексу в списке YAML: рамка, формат и выравнивание `mark`.
    set_date = "set_date"
    remove_date = "remove_date"


@dataclass(frozen=True)
class PlaceBox:
    """Рамка подписи на странице, мм от левого верхнего угла."""

    page: int
    x_mm: float
    y_mm: float
    width_mm: float


@dataclass(frozen=True)
class MarkBox:
    """Рамка метки даты на странице, её формат и выравнивание."""

    page: int
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    format: DateMarkFormat
    align: DateMarkAlign = DateMarkAlign.centered


@dataclass(frozen=True)
class PlaceOp:
    op: PlaceOpKind
    slot: str
    doc: str | None = None
    box: PlaceBox | None = None
    index: int | None = None
    mark: MarkBox | None = None
    anchor: str | None = None


class PlaceEditError(ValueError):
    """Правку нельзя применить: слота или документа нет, рамка за краем листа, строки шаблона нет в сборке."""


@dataclass(frozen=True)
class AnchorRef:
    """Якорь записи пака и есть ли он в сборке (`unknown`: у сборки нет якорей)."""

    id: str
    state: AnchorState


@dataclass(frozen=True)
class DocDate:
    """Метка даты документа в сборке: индекс в списке YAML, запись пака и рамка (None: в этой сборке её нет)."""

    index: int
    entry: PackDate
    box: SignatureDefaultDate | None
    anchor: AnchorRef | None


class FrameKind(StrEnum):
    # Своя запись `placements` документа.
    place = "place"
    # Общее место слота (`default_placement`).
    default = "default"


@dataclass(frozen=True)
class DocFrame:
    """Место слота на документе сборки: чья запись, рамка по якорям сборки (None: места нет) и метки даты."""

    kind: FrameKind
    entry: PackPlace
    box: SignatureDefaultPlacement | None
    anchor: AnchorRef | None
    dates: tuple[DocDate, ...]


@dataclass(frozen=True)
class SlotPlaces:
    """Слот каталога версии с записями мест и меток даты.

    `default_place` общее место, как его читает лоадер (без ключа в YAML это место по умолчанию лоадера, тогда
    `default_set` ложно). `document` рамки документа сборки, если слот к нему применим.
    """

    id: str
    label: dict[str, str]
    applies_to: tuple[str, ...]
    per_author: bool
    required: bool
    default_place: PackPlace
    default_set: bool
    places: tuple[tuple[str, PackPlace], ...]
    dates: tuple[tuple[str, tuple[tuple[int, PackDate], ...]], ...]
    document: DocFrame | None


@dataclass(frozen=True)
class AnchorView:
    """Якорь сборки словами: чей он слот и чья это строка в команде.

    Общий документ команды ставит строку на каждого автора (signing-route.md, 15.17.20), её якорь это
    `author__ivanov`: `slot` имя без слага (`author`, якорь называют по слоту), `author` слаг, `author_name` имя
    автора из набора данных сборки (None: сборка авторов не запомнила). У обычной строки `slot` это имя якоря, автора
    нет. `part` часть даты (`day`) у якоря даты. Рамку такого автора `pack_signature_check` и
    `pack_signature_render` называют `<slot>--<author>`.
    """

    id: str
    kind: AnchorKind
    slot: str
    part: str | None = None
    author: str | None = None
    author_name: str | None = None


def anchor_views(
    sign_anchors: Sequence[str], date_anchors: Sequence[str], authors: Mapping[str, str]
) -> tuple[AnchorView, ...]:
    """Якоря подписи, затем якоря даты, в порядке сборки; `authors` это слаг -> имя автора команды сборки."""
    views: list[AnchorView] = []
    for kind, ids in ((AnchorKind.sign, sign_anchors), (AnchorKind.date, date_anchors)):
        for anchor_id in ids:
            name, _, part = anchor_id.partition(".")
            slot, author = split_author_name(name)
            views.append(
                AnchorView(
                    id=anchor_id,
                    kind=kind,
                    slot=slot,
                    part=part or None,
                    author=author,
                    author_name=authors.get(author) if author is not None else None,
                )
            )
    return tuple(views)


@dataclass(frozen=True)
class VersionPlaces:
    """Каталог слотов версии и якоря сборки документа (`document`), если сборка передана.

    `sign_anchors` и `date_anchors` это id якорей как в `anchors.json` сборки; `anchor_views` те же якоря словами
    (слот и автор команды у строки `author__<слаг>`), их дописывает сценарий: имена авторов знает сборка."""

    documents: tuple[str, ...]
    slots: tuple[SlotPlaces, ...]
    document: str | None
    anchors_known: bool
    sign_anchors: tuple[str, ...]
    date_anchors: tuple[str, ...]
    anchor_views: tuple[AnchorView, ...] = ()
