"""Схемы `/api/v1/pack-studio/.../submission`: профили сдачи и порядок маршрута формой (срез T13).

Эталоны лежат в `contracts/pack-studio/fixtures`, тест `tests/unit/contract/test_pack_studio_contract.py` сверяет их
с этими моделями.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from hse_doc_studio.api.schemas.common import StrictModel
from hse_doc_studio.api.schemas.pack_studio import ReadOnlyReason

SignMethodName = Literal["image", "detached", "pades"]
KindName = Literal["research", "project"]
WhenPersonName = Literal["supervisor", "co_supervisor", "academic_supervisor"]
WhenRoleName = Literal["university", "company"]
SubmissionListName = Literal["items", "extra_items", "signing_slots"]
SubmissionOpName = Literal[
    "add_profile",
    "set_profile",
    "remove_profile",
    "move_profile",
    "set_profile_route",
    "add_entry",
    "set_entry",
    "remove_entry",
    "move_entry",
    "set_route",
]
PairSourceName = Literal["point", "preset"]
OrderSourceName = Literal["profile", "version", "builtin"]

_ID = 64
_TEXT = 2000
Localized = dict[str, str]
Steps = list[list[str]]


class PackSubmissionItem(StrictModel):
    """Пункт точки: `methods` по слоту (нет записи: любой способ), `supported_kinds` пусто: оба вида."""

    doc_id: str = Field(min_length=1, max_length=128)
    signatures: list[str] = Field(default_factory=list, max_length=16)
    methods: dict[str, list[SignMethodName]] = Field(default_factory=dict, max_length=16)
    skip_if_nda: bool = False
    supported_kinds: list[KindName] = Field(default_factory=list, max_length=2)


class PackSubmissionExtra(StrictModel):
    source: str = Field(min_length=1, max_length=512)
    output_name: str = Field(default="", max_length=255)
    format: str | None = Field(default=None, max_length=32)
    supported_kinds: list[KindName] = Field(default_factory=list, max_length=2)


class PackSubmissionWhen(StrictModel):
    person: WhenPersonName
    role: WhenRoleName | None = None


class PackSubmissionSlot(StrictModel):
    doc_id: str = Field(min_length=1, max_length=128)
    slot_id: str = Field(min_length=1, max_length=_ID)
    when: PackSubmissionWhen | None = None
    optional: bool = False


class PackIndexedItem(StrictModel):
    # Индекс в списке YAML; `entry` null, если лоадер запись не читает (`error` почему).
    index: int
    entry: PackSubmissionItem | None
    error: str | None


class PackIndexedExtra(StrictModel):
    index: int
    entry: PackSubmissionExtra | None
    error: str | None


class PackIndexedSlot(StrictModel):
    index: int
    entry: PackSubmissionSlot | None
    error: str | None


class PackSubmissionProfile(StrictModel):
    index: int
    id: str | None
    name: Localized
    description: Localized
    deadline_hint: Localized | None
    items: list[PackIndexedItem]
    extra_items: list[PackIndexedExtra]
    # Порядок точки; null: ключа нет, действует порядок версии.
    signing_route: Steps | None
    signing_slots: list[PackIndexedSlot]
    # Первая проблема строгого разбора лоадера; форма показывает её у профиля.
    error: str | None


class PackSubmissionSlotInfo(StrictModel):
    id: str
    label: Localized
    applies_to: list[str]
    required: bool
    per_author: bool


class PackSubmissionForm(StrictModel):
    id: str
    title: Localized
    # Файл ответов анкеты в проекте: значение `source` пункта `extra_items`.
    source: str
    output_name: str
    format: str | None
    required_for_pack: bool


class PackSubmissionResponse(StrictModel):
    workspace_id: str
    pack: str
    template: str
    version: str
    # Манифест версии и его ETag: правка идёт с `If-Match` по нему.
    path: str
    etag: str
    read_only: ReadOnlyReason | None
    documents: list[str]
    supported_kinds: list[KindName]
    has_nda: bool
    slots: list[PackSubmissionSlotInfo]
    forms: list[PackSubmissionForm]
    # Порядок версии `signatures.route`; null: ключа нет, действует встроенный `builtin_route`.
    route: Steps | None
    builtin_route: Steps
    profiles: list[PackSubmissionProfile]


class PackProfileHead(StrictModel):
    id: str = Field(min_length=1, max_length=_ID)
    name: Localized = Field(max_length=4)
    description: Localized = Field(default_factory=dict, max_length=4)
    # null убирает подсказку срока.
    deadline_hint: Localized | None = None


_NEEDS_PROFILE = {
    "set_profile",
    "remove_profile",
    "move_profile",
    "set_profile_route",
    "add_entry",
    "set_entry",
    "remove_entry",
    "move_entry",
}
_NEEDS_LIST = {"add_entry", "set_entry", "remove_entry", "move_entry"}
_NEEDS_INDEX = {"set_entry", "remove_entry", "move_entry"}
_NEEDS_VALUE = {"add_entry", "set_entry"}
_VALUE_FIELD = {"items": "item", "extra_items": "extra", "signing_slots": "slot"}


class PackSubmissionOp(StrictModel):
    """Правка формы: профиль по индексу в списке YAML, запись списка `entries` по индексу `index`.

    Список профиля в `entries`; запись передаётся полем по его виду: `item` у `items`, `extra` у
    `extra_items`, `slot` у `signing_slots`.
    `steps` у `set_profile_route` и `set_route`: null убирает ключ (действует порядок версии или встроенный).
    """

    op: SubmissionOpName
    profile: int | None = Field(default=None, ge=0, le=256)
    head: PackProfileHead | None = None
    entries: SubmissionListName | None = None
    index: int | None = Field(default=None, ge=0, le=256)
    to: int | None = Field(default=None, ge=0, le=256)
    item: PackSubmissionItem | None = None
    extra: PackSubmissionExtra | None = None
    slot: PackSubmissionSlot | None = None
    steps: Steps | None = Field(default=None, max_length=16)

    @model_validator(mode="after")
    def _fields(self) -> PackSubmissionOp:
        if self.op in _NEEDS_PROFILE and self.profile is None:
            raise ValueError(f"{self.op} needs profile")
        if self.op in {"add_profile", "set_profile"} and self.head is None:
            raise ValueError(f"{self.op} needs head")
        if self.op in _NEEDS_LIST and self.entries is None:
            raise ValueError(f"{self.op} needs entries")
        if self.op in _NEEDS_INDEX and self.index is None:
            raise ValueError(f"{self.op} needs index")
        if self.op in {"move_profile", "move_entry"} and self.to is None:
            raise ValueError(f"{self.op} needs to")
        if self.op in _NEEDS_VALUE and self.entries is not None and getattr(self, _VALUE_FIELD[self.entries]) is None:
            raise ValueError(f"{self.op} on {self.entries} needs {_VALUE_FIELD[self.entries]}")
        return self


class PackSubmissionPatchRequest(StrictModel):
    ops: list[PackSubmissionOp] = Field(min_length=1, max_length=50)


class PackSubmissionRoutesRequest(StrictModel):
    # Набор данных и переключатели предпросмотра (6.2); недостающие берутся из набора, затем по умолчанию.
    example: str | None = Field(default=None, max_length=255)
    combination: dict[str, str] = Field(default_factory=dict, max_length=32)


class PackRoutePerson(StrictModel):
    # Персона маршрута: слаг автора (в одиночной работе `author`) или роль руководителя.
    persona: str
    role: Literal["author", "supervisor", "co_supervisor", "academic_supervisor"]
    name: str


class PackRoutePair(StrictModel):
    doc_id: str
    slot_id: str
    persona: str
    source: PairSourceName
    optional: bool
    when: PackSubmissionWhen | None


class PackSkippedPair(StrictModel):
    doc_id: str
    slot_id: str
    when: PackSubmissionWhen | None


class PackDocSlotRef(StrictModel):
    doc_id: str
    slot_id: str


class PackProfileRoute(StrictModel):
    id: str
    # Шаги людьми, внутри шага параллельно; пусто: подписи точке не нужны.
    steps: list[list[PackRoutePerson]]
    pairs: list[PackRoutePair]
    skipped: list[PackSkippedPair]
    may_add: list[PackDocSlotRef]
    items_off: list[str]
    order_source: OrderSourceName
    # Версия задаёт пресет точки (`signing_slots` профиля или места слотов по документам).
    preset: bool


class PackSubmissionRoutesResponse(StrictModel):
    example: str
    combination: dict[str, str]
    profiles: list[PackProfileRoute]
