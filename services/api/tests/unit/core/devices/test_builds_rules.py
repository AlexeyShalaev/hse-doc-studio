"""Правила сравнения сборок облака и Студии и решение «качать ли облачный PDF»."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from hse_doc_studio.core.devices.builds import BuildRelation, FetchStatus, Side, decide_fetch, relate

T0 = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
MB = 1024 * 1024


def side(minutes: int = 0, *, commit: str | None = "c1", sha: str | None = "s1", size: int | None = MB) -> Side:
    return Side(at=T0 + timedelta(minutes=minutes), commit=commit, sha256=sha, size=size)


def test__relate__covers_every_combination() -> None:
    assert relate(None, None) is BuildRelation.none
    assert relate(None, side()) is BuildRelation.cloud_only
    assert relate(side(), None) is BuildRelation.local_only
    assert relate(side(), side(5)) is BuildRelation.same
    assert relate(side(0, sha="a"), side(5, sha="b")) is BuildRelation.cloud_newer
    assert relate(side(5, sha="a"), side(0, sha="b")) is BuildRelation.local_newer


def test__relate__same_commit_without_fingerprint_counts_as_same() -> None:
    assert relate(side(sha=None), side(sha="x")) is BuildRelation.same


def decide(
    relation: BuildRelation,
    cloud: Side | None,
    *,
    force: bool = False,
    auto: bool = False,
    current: bool | None = True,
    limit: int = 100 * MB,
) -> FetchStatus | None:
    return decide_fetch(relation, cloud, force=force, auto=auto, cloud_current=current, max_bytes=limit)


def test__decide_fetch__nothing_to_fetch_cases() -> None:
    assert decide(BuildRelation.none, None) is FetchStatus.no_cloud_build
    assert decide(BuildRelation.same, side()) is FetchStatus.unchanged


def test__decide_fetch__never_overwrites_a_newer_local_build_unless_forced() -> None:
    assert decide(BuildRelation.local_newer, side()) is FetchStatus.kept_local
    assert decide(BuildRelation.local_newer, side(), force=True) is None


def test__decide_fetch__respects_size_limit() -> None:
    assert decide(BuildRelation.cloud_only, side(size=101 * MB)) is FetchStatus.too_large
    assert decide(BuildRelation.cloud_only, side(size=100 * MB)) is None


def test__decide_fetch__auto_takes_only_the_build_of_the_inputs_the_person_has() -> None:
    assert decide(BuildRelation.cloud_only, side(commit="c1"), auto=True, current=True) is None
    assert decide(BuildRelation.cloud_only, side(commit="c0"), auto=True, current=False) is FetchStatus.skipped_stale
    assert decide(BuildRelation.cloud_only, side(commit=None), auto=True, current=None) is FetchStatus.skipped_stale


def test__decide_fetch__manual_takes_any_cloud_build_even_of_another_version() -> None:
    assert decide(BuildRelation.cloud_newer, side(commit="c0"), current=False) is None
