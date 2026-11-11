"""«Старые версии»: что после обновлений безопасно считать устаревшим.

Обновление Студии (кнопка, `update.sh` или ручной pull) качает новый образ и
пересоздаёт контейнер, а прежние образы остаются на диске: каждая версия — это
отдельный тег `ghcr.io/…/hse-doc-studio:X.Y.Z`. Рядом копятся устаревшие теги
вспомогательных образов (когда релиз сменил версию TeX Live, LanguageTool и т. п.)
и остановленный контейнер апдейтера.

Старой считается только вещь, которая одновременно:
* не нужна текущей установке: версия образа Студии строго ниже текущей; тег
  вспомогательного образа отличается от активного в его репозитории;
* не занята: ни один контейнер (даже остановленный) на ней не основан;
* не настроена и не зашита как «активная» (`protected` из отчёта об использовании).

Из старых версий Студии самая свежая (ниже текущей) — «откат»: её по умолчанию
не трогаем, чтобы можно было вернуться на предыдущую версию без скачивания.
Образы новее текущей (после отката) и теги без номера версии (`latest`, `sha-…`,
собственные сборки) не считаются старыми никогда.

Чистая функция без обращения к docker: вход — отчёт об использовании.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from hse_doc_studio.core.docker_disk.usage import (
    DANGLING_CATEGORY,
    OTHER_CATEGORY,
    DockerDiskUsage,
    ImageUsage,
)
from hse_doc_studio.core.update.services import parse_version

OldVersionKind = Literal["studio_image", "service_image", "container"]

_SEMVER_TAG_RE = re.compile(r"^v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
_NON_SERVICE = (OTHER_CATEGORY, DANGLING_CATEGORY, "app")


@dataclass(frozen=True)
class OldVersionItem:
    kind: OldVersionKind
    # Ссылка образа (repo:tag) или имя контейнера — то, что принимает очистка.
    ref: str
    # Версия Студии для её образов; для остальных пусто.
    version: str
    size_bytes: int
    created: str


@dataclass(frozen=True)
class OldVersions:
    current_version: str
    # Последняя предыдущая версия: по умолчанию не удаляется (откат).
    rollback: OldVersionItem | None = None
    items: list[OldVersionItem] = field(default_factory=list)

    @property
    def reclaimable_bytes(self) -> int:
        return sum(item.size_bytes for item in self.items)

    @property
    def rollback_bytes(self) -> int:
        return self.rollback.size_bytes if self.rollback else 0

    @property
    def refs(self) -> list[str]:
        return [item.ref for item in self.items]


def _item(image: ImageUsage, kind: OldVersionKind) -> OldVersionItem:
    return OldVersionItem(
        kind=kind,
        ref=image.reference,
        version=image.tag.lstrip("vV") if kind == "studio_image" else "",
        size_bytes=image.size_bytes,
        created=image.created,
    )


def find_old_versions(usage: DockerDiskUsage, current_version: str, image_base: str) -> OldVersions:
    if not usage.available:
        return OldVersions(current_version=current_version)
    current = parse_version(current_version)

    studio = [
        image
        for image in usage.images
        if not image.dangling
        and image.repository == image_base
        and _SEMVER_TAG_RE.match(image.tag)
        and parse_version(image.tag) < current
    ]
    studio.sort(key=lambda image: parse_version(image.tag), reverse=True)
    rollback = _item(studio[0], "studio_image") if studio else None
    items = [_item(image, "studio_image") for image in studio[1:] if not image.protected]

    # Устаревший тег вспомогательного образа: в его репозитории есть другой, активный или занятый тег.
    live_repos = {
        image.repository
        for image in usage.images
        if image.protected and not image.dangling and image.category not in _NON_SERVICE
    }
    items.extend(
        _item(image, "service_image")
        for image in usage.images
        if not image.dangling
        and not image.protected
        and image.category not in _NON_SERVICE
        and image.repository in live_repos
    )

    items.extend(
        OldVersionItem(
            kind="container",
            ref=container.name,
            version="",
            size_bytes=container.size_bytes,
            created=container.status,
        )
        for container in usage.containers
        if container.managed and container.state != "running" and container.image.rsplit(":", 1)[0] == image_base
    )
    return OldVersions(current_version=current_version, rollback=rollback, items=items)
