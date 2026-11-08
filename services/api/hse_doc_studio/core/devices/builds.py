"""Сравнение сборок документа у облака и у локальной Студии: чистые правила без ввода-вывода."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class BuildRelation(StrEnum):
    none = "none"
    cloud_only = "cloud_only"
    local_only = "local_only"
    same = "same"
    cloud_newer = "cloud_newer"
    local_newer = "local_newer"


class FetchStatus(StrEnum):
    downloaded = "downloaded"
    unchanged = "unchanged"
    kept_local = "kept_local"
    skipped_stale = "skipped_stale"
    too_large = "too_large"
    no_cloud_build = "no_cloud_build"
    # Документ выпускается не в PDF (pptx и т. п.): облако хранит только PDF, результат приходит с исходниками.
    not_pdf = "not_pdf"
    failed = "failed"


class FetchBlocked(StrEnum):
    """Почему облачную сборку документа нельзя получить, даже если она есть."""

    # Результат документа не PDF: облако архивирует только PDF, а сам файл (pptx) и так приходит с исходниками.
    not_pdf = "not_pdf"
    # Путь результата не известен: определения документа нет в установленном паке.
    output_unknown = "output_unknown"


@dataclass(frozen=True)
class Side:
    """Сборка с одной из сторон: когда, из какого коммита, отпечаток."""

    at: datetime
    commit: str | None
    sha256: str | None
    size: int | None = None


def relate(local: Side | None, cloud: Side | None) -> BuildRelation:
    if local is None and cloud is None:
        return BuildRelation.none
    if local is None:
        return BuildRelation.cloud_only
    if cloud is None:
        return BuildRelation.local_only
    same_file = local.sha256 is not None and local.sha256 == cloud.sha256
    same_version = local.commit is not None and local.commit == cloud.commit and local.sha256 is None
    if same_file or same_version:
        return BuildRelation.same
    return BuildRelation.cloud_newer if cloud.at > local.at else BuildRelation.local_newer


def fetch_blocked(output_file: str | None) -> FetchBlocked | None:
    """Можно ли вообще положить облачный PDF на место результата документа; `None` значит «можно»."""
    if output_file is None:
        return FetchBlocked.output_unknown
    if not output_file.lower().endswith(".pdf"):
        return FetchBlocked.not_pdf
    return None


def decide_fetch(  # noqa: PLR0911 — правила проверяются по порядку, каждое со своим итогом
    relation: BuildRelation,
    cloud: Side | None,
    *,
    force: bool,
    auto: bool,
    local_head: str | None,
    local_dirty: bool,
    max_bytes: int,
) -> FetchStatus | None:
    """Почему сборку качать не надо; `None` значит «можно качать».

    Ручной запуск скачивает любую облачную сборку, если она не затрёт более свежую локальную (`force` разрешает и
    это). Автоматический берёт только сборку из версии, которая сейчас лежит у человека: чужая более новая или
    старая версия подменила бы PDF тем, чего нет в его исходниках.
    """
    if cloud is None:
        return FetchStatus.no_cloud_build
    if relation is BuildRelation.same:
        return FetchStatus.unchanged
    if cloud.size is not None and cloud.size > max_bytes:
        return FetchStatus.too_large
    if relation is BuildRelation.local_newer and not force:
        return FetchStatus.kept_local
    if auto and (cloud.commit is None or cloud.commit != local_head or local_dirty):
        return FetchStatus.skipped_stale
    return None
