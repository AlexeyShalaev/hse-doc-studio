"""Версии релизов: размер шага и выбор цели под политику. Чистые функции."""

from __future__ import annotations

from collections.abc import Iterable
from enum import IntEnum

from hse_doc_studio.core.server_update.entities import MaxBump, ReleaseInfo
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
