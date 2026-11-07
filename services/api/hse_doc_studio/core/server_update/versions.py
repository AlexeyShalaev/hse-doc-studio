"""Версии релизов: размер шага и выбор цели под политику. Чистые функции."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import IntEnum, StrEnum

from hse_doc_studio.core.server_update.entities import MaxBump, ReleaseInfo, RunKind, RunStatus, UpdateRun
from hse_doc_studio.core.update.services import is_newer, parse_version


class Bump(IntEnum):
    none = 0
    patch = 1
    minor = 2
    major = 3


def bump_kind(current: str, candidate: str) -> Bump:
    """Размер шага от текущей версии к кандидату; не новее значит `none`."""
    if not is_newer(candidate, current):
        return Bump.none
    cur, cand = _triple(current), _triple(candidate)
    if cand[0] != cur[0]:
        return Bump.major
    if cand[1] != cur[1]:
        return Bump.minor
    return Bump.patch


def _triple(value: str) -> tuple[int, int, int]:
    parts = (*parse_version(value), 0, 0, 0)
    return parts[0], parts[1], parts[2]


_ALLOWED = {MaxBump.patch: Bump.patch, MaxBump.minor: Bump.minor}


def is_allowed(current: str, candidate: str, limit: MaxBump) -> bool:
    kind = bump_kind(current, candidate)
    return kind is not Bump.none and kind <= _ALLOWED[limit]


def newest_release(current: str, releases: Iterable[ReleaseInfo]) -> ReleaseInfo | None:
    """Самый свежий релиз новее текущей версии (что бы ни разрешала политика)."""
    newer = [r for r in releases if is_newer(r.version, current)]
    return max(newer, key=lambda r: parse_version(r.version), default=None)


def pick_target(current: str, releases: Iterable[ReleaseInfo], limit: MaxBump) -> ReleaseInfo | None:
    """Самый свежий релиз, который политика ставит сама: шаг не крупнее `limit`.

    Перешагивать через крупную версию нельзя, но внутри разрешённого шага берётся самая новая: при текущей 0.3.1,
    релизах 0.3.5, 0.4.0, 1.0.0 и пределе minor цель 0.4.0.
    """
    allowed = [r for r in releases if is_allowed(current, r.version, limit)]
    return max(allowed, key=lambda r: parse_version(r.version), default=None)


class SchemaVerdict(StrEnum):
    compatible = "compatible"  # ревизия версии известна и равна текущей: образ встанет на эту базу
    incompatible = "incompatible"  # известна и отличается: версия не запустится (или потеряет данные), откат запрещён
    unknown = "unknown"  # версии на этом хосте не было: апдейтер проверит схему образа до остановки сервисов


@dataclass(frozen=True)
class DowngradeTarget:
    release: ReleaseInfo
    verdict: SchemaVerdict
    revision: str | None = None  # известная ревизия базы этой версии


def schema_verdict(version: str, db_revision: str | None, known: Mapping[str, str]) -> tuple[SchemaVerdict, str | None]:
    """Политика отката: разрешён на версию, у которой head миграций равен текущей ревизии базы.

    Точное равенство, потому что обратную совместимость схемы мы не декларируем: другая ревизия значит, что миграции
    между версиями что-то меняли, и старый код либо не стартует (защита db-ahead), либо работает на чужой схеме.
    """
    revision = known.get(version)
    if db_revision is None or revision is None:
        return SchemaVerdict.unknown, revision
    return (SchemaVerdict.compatible if revision == db_revision else SchemaVerdict.incompatible), revision


def older_releases(current: str, releases: Iterable[ReleaseInfo]) -> list[ReleaseInfo]:
    """Релизы старше текущей версии, свежие первыми."""
    older = [r for r in releases if is_newer(current, r.version)]
    return sorted(older, key=lambda r: parse_version(r.version), reverse=True)


def known_revisions(runs: Iterable[UpdateRun]) -> dict[str, str]:
    """Версия -> ревизия базы по запускам от старых к новым.

    Перед запуском база стоит на head версии `from_version` (иначе её образ не стартовал бы), после успешного
    обновления или отката на head версии `to_version`. Откатившийся запуск говорит только о `from_version`.
    """
    known: dict[str, str] = {}
    for run in runs:
        if run.kind not in {RunKind.update, RunKind.downgrade}:
            continue
        if run.from_revision:
            known[run.from_version] = run.from_revision
        if run.status is RunStatus.succeeded and run.to_revision:
            known[run.to_version] = run.to_revision
    return known
