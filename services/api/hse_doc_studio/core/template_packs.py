"""Откуда Студия взяла каталог шаблонов и совпадает ли он с тем, что вшит в её образ.

Образ all-in-one несёт свои паки (`/app/packs`) и их опись (манифест, его пишет
сборка образа). Каталог можно подменить: смонтировать поверх `/app/packs` папку
с хоста (оверлей `compose.build.yml` для разработки) или указать другой путь в
`HSE_STUDIO__PACKS_DIR`. Такой каталог живёт своей жизнью и после обновления
Студии остаётся прежним. Тогда версии шаблона, которая вшита в эту же Студию,
в нём может не оказаться, и совет «обновите Студию» был бы неправдой: Студия
свежая, отстал подключённый каталог.

Здесь только модель и правила, чтение диска и манифеста живёт в
`infra.template.packs_source`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol


@dataclass(frozen=True, order=True)
class TemplateKey:
    pack_id: str
    template_id: str
    version: str


class PacksKind(StrEnum):
    # Каталог, вшитый в образ, и он не подменён.
    builtin = "builtin"
    # Каталог подключён извне: смонтирован поверх вшитого или указан другой путь.
    external = "external"
    # Описи вшитых паков нет (запуск из исходников): сравнивать не с чем.
    source = "source"


@dataclass(frozen=True)
class PacksSource:
    # Путь каталога, как его видит процесс Студии (в контейнере это путь внутри него).
    path: str
    kind: PacksKind
    # Каталог (или папка над ним) смонтирован поверх файловой системы образа.
    mounted: bool = False
    # Версии шаблонов, которые вшиты в образ этой Студии; None, если описи нет.
    builtin: frozenset[TemplateKey] | None = None
    # Версия Студии, сборка которой записала опись.
    builtin_studio: str | None = None
    # Версии, которые реально лежат в каталоге.
    available: frozenset[TemplateKey] = field(default_factory=frozenset)

    def lags_for(self, key: TemplateKey) -> bool:
        """Версия есть во вшитых паках этой Студии, но её нет в подключённом каталоге."""
        return (
            self.kind is PacksKind.external
            and self.builtin is not None
            and key in self.builtin
            and key not in self.available
        )

    @property
    def missing_builtin(self) -> tuple[TemplateKey, ...]:
        """Вшитые версии, которых нет в каталоге: чем он отстаёт от Студии."""
        if self.kind is not PacksKind.external or self.builtin is None:
            return ()
        return tuple(sorted(self.builtin - self.available))


class ITemplatePacksSource(Protocol):
    """Сведения о каталоге шаблонов. Каталог читается один раз на старте, ответ не меняется."""

    def describe(self) -> PacksSource: ...


def classify_packs(*, packs_dir: str, builtin_dir: str | None, mounted: bool) -> PacksKind:
    """Вид каталога: вшитый, подключённый извне или запуск без описи.

    `builtin_dir` — путь, по которому сборка образа положила паки (из манифеста);
    None — манифеста нет. Подключённым считается и каталог по другому пути, и
    каталог, смонтированный поверх вшитого: в обоих случаях файлы не из образа.
    """
    if builtin_dir is None:
        return PacksKind.source
    if mounted or packs_dir.rstrip("/") != builtin_dir.rstrip("/"):
        return PacksKind.external
    return PacksKind.builtin
