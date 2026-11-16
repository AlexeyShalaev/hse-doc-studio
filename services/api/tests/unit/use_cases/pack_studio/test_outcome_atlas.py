"""Сервис атласа: состояния, пины, ETag и 304, кэш по `revision`, общий расчёт одинаковых запросов, срок и пределы."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.preview import PreviewInputs, RawExample, VersionDescription, auto_examples
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.pack_studio import outcome_atlas as atlas_service
from hse_doc_studio.use_cases.pack_studio.outcome_atlas import (
    AtlasBusy,
    AtlasLimits,
    PackAtlasService,
    parse_pins,
    work_tree_revision,
)
from hse_doc_studio.use_cases.pack_studio.preview import VersionSource

_ROOT = Path(__file__).resolve().parents[6]
TODAY = date(2026, 11, 16)
_ACTOR: Any = object()  # актора сервис атласа только передаёт дальше


def _source(files: dict[str, str] | None = None) -> VersionSource:
    version = YamlTemplateRepository(_ROOT / "packs").get_version("hse-cs-sse", "coursework", "2026.1.6")
    assert version is not None
    inputs = PreviewInputs(
        files=files or {"version.yaml": "v1", "files/report/doc.yaml": "d1", "files/report/main.tex": "t1"},
        extra=("pack.yaml:p1",),
        tree="tree-1",
    )
    desc = VersionDescription("hse-cs-sse", "coursework", version, (RawExample("ex", {"name": "x"}),))
    examples = auto_examples(version)
    return VersionSource(desc, inputs, examples, examples[0].id)


class _Previews:
    """Подмена `PackPreviewService`: сервис атласа от него берёт только `source`."""

    def __init__(self, source: VersionSource) -> None:
        self.current = source
        self.calls = 0

    async def source(self, *_args: object) -> VersionSource:
        self.calls += 1
        return self.current


def _edited(source: VersionSource, **files: str) -> VersionSource:
    """Источник с изменёнными дайджестами файлов версии."""
    return replace(source, inputs=replace(source.inputs, files={**source.inputs.files, **files}))


def _service(previews: _Previews, **limits: Any) -> PackAtlasService:
    return PackAtlasService(previews, limits=AtlasLimits(**limits), today=lambda: TODAY)  # type: ignore[arg-type]


async def _atlas(service: PackAtlasService, **kwargs: Any) -> Any:
    return await service.atlas(_ACTOR, uuid4(), "hse-cs-sse", "coursework", "2026.1.6", **kwargs)


# ── Вход ─────────────────────────────────────────────────────────────────────


def test__parse_pins__splits_on_the_first_colon_and_rejects_repeats_and_junk() -> None:
    assert parse_pins(["supervisor:company", "meta.report_margins:ВШЭ: 25/10"]) == {
        "supervisor": "company",
        "meta.report_margins": "ВШЭ: 25/10",
    }
    assert parse_pins([]) == {}
    for bad in (["supervisor"], [":x"], ["a:1", "a:2"], [f"i{n}:v" for n in range(65)]):
        with pytest.raises(PackStudioError) as caught:
            parse_pins(bad)
        assert caught.value.code is PackStudioErrorCode.inputs_invalid


async def test__atlas__a_state_other_than_the_work_tree_waits_for_the_git_reading_of_o2() -> None:
    service = _service(_Previews(_source()))

    for state in ("head", "base"):
        with pytest.raises(PackStudioError) as caught:
            await _atlas(service, state=state)
        assert caught.value.code is PackStudioErrorCode.diff_base_unavailable


@pytest.mark.parametrize(
    ("kwargs", "field"),
    [
        ({"pins": {"nope": "x"}}, "nope"),
        ({"pins": {"supervisor": "boss"}}, "supervisor"),
        ({"example": "missing"}, "example"),
    ],
)
async def test__atlas__bad_pins_and_examples_are_inputs_invalid(kwargs: dict[str, Any], field: str) -> None:
    service = _service(_Previews(_source()))

    with pytest.raises(PackStudioError) as caught:
        await _atlas(service, **kwargs)

    assert caught.value.code is PackStudioErrorCode.inputs_invalid
    assert caught.value.ctx["field"] == field


# ── ETag, кэш и общий расчёт ─────────────────────────────────────────────────


async def test__atlas__etag_is_stable_and_a_matching_if_none_match_answers_without_calculating() -> None:
    service = _service(_Previews(_source()))
    first = await _atlas(service)
    builds = 0
    original = atlas_service.build_atlas

    def counting(*args: Any, **kwargs: Any) -> Any:
        nonlocal builds
        builds += 1
        return original(*args, **kwargs)

    atlas_service.build_atlas = counting  # type: ignore[assignment]
    try:
        again = await _atlas(service, if_none_match=first.etag)
        other = await _atlas(service, if_none_match='W/"something-else"')
    finally:
        atlas_service.build_atlas = original  # type: ignore[assignment]

    assert first.atlas is not None
    assert (again.etag, again.atlas) == (first.etag, None)
    assert other.atlas is first.atlas  # из кэша, расчёта нет
    assert builds == 0


async def test__atlas__the_second_request_comes_from_the_cache_and_a_pin_changes_the_etag_only() -> None:
    service = _service(_Previews(_source()))

    first = await _atlas(service)
    second = await _atlas(service)
    pinned = await _atlas(service, pins={"supervisor": "company"})

    assert second.atlas is first.atlas
    assert pinned.etag != first.etag
    assert pinned.atlas is not None
    assert pinned.atlas.rows_total == 4
    assert first.atlas is not None
    assert first.atlas.elapsed_ms >= 0
    assert first.atlas.revision.startswith("sha256-")


async def test__atlas__the_analysis_is_shared_between_pins() -> None:
    service = _service(_Previews(_source()))
    built: list[object] = []
    original = atlas_service.analyze_impact

    def counting(*args: Any, **kwargs: Any) -> Any:
        built.append(1)
        return original(*args, **kwargs)

    atlas_service.analyze_impact = counting  # type: ignore[assignment]
    try:
        await _atlas(service)
        await _atlas(service, pins={"supervisor": "none"})
        await _atlas(service, pins={"co_supervisor": "yes"})
    finally:
        atlas_service.analyze_impact = original  # type: ignore[assignment]

    assert len(built) == 1


async def test__atlas__a_manifest_edit_changes_the_revision_and_a_tex_edit_does_not() -> None:
    previews = _Previews(_source())
    service = _service(previews)
    first = await _atlas(service)

    base = previews.current
    previews.current = _edited(base, **{"files/report/main.tex": "t2"})
    tex = await _atlas(service)
    previews.current = _edited(base, **{"version.yaml": "v2"})
    manifest = await _atlas(service)
    previews.current = _edited(base, **{"files/report/doc.yaml": "d2"})
    doc = await _atlas(service)

    assert tex.etag == first.etag
    assert len({first.etag, manifest.etag, doc.etag}) == 3


async def test__atlas__equal_simultaneous_requests_share_one_calculation() -> None:
    service = _service(_Previews(_source()))
    builds = 0
    original = atlas_service.build_atlas

    def counting(*args: Any, **kwargs: Any) -> Any:
        nonlocal builds
        builds += 1
        return original(*args, **kwargs)

    atlas_service.build_atlas = counting  # type: ignore[assignment]
    try:
        results = await asyncio.gather(*(_atlas(service) for _ in range(4)))
    finally:
        atlas_service.build_atlas = original  # type: ignore[assignment]

    assert builds == 1
    assert len({id(r.atlas) for r in results}) == 1


# ── Пределы и срок ───────────────────────────────────────────────────────────


async def test__atlas__too_many_rows_is_atlas_too_large_with_limit_and_rows() -> None:
    service = _service(_Previews(_source()), max_rows=11)

    with pytest.raises(PackStudioError) as caught:
        await _atlas(service)

    assert caught.value.code is PackStudioErrorCode.atlas_too_large
    assert (caught.value.ctx["limit"], caught.value.ctx["rows"]) == (11, 12)
    # Закрепление режет таблицу под предел.
    ok = await _atlas(service, pins={"supervisor": "company"})
    assert ok.atlas is not None
    assert ok.atlas.rows_total == 4


async def test__atlas__an_expired_deadline_is_busy_with_a_retry_after() -> None:
    service = _service(_Previews(_source()), timeout_s=0.0, retry_after_s=7)

    with pytest.raises(AtlasBusy) as caught:
        await _atlas(service)

    assert caught.value.retry_after_s == 7


async def test__atlas__a_full_queue_is_busy_after_the_deadline() -> None:
    service = _service(_Previews(_source()), concurrency=1, timeout_s=0.05)
    await service._slots.acquire()  # noqa: SLF001 — единственное место занято

    with pytest.raises(AtlasBusy):
        await _atlas(service)

    service._slots.release()  # noqa: SLF001


async def test__atlas__the_cache_keeps_at_most_the_configured_number_of_atlases() -> None:
    service = _service(_Previews(_source()), cache_entries=2)

    for pin in ("university", "company", "none"):
        await _atlas(service, pins={"supervisor": pin})

    assert len(service._atlases) == 2  # noqa: SLF001


def test__revision__ignores_tex_and_depends_on_manifests_and_example() -> None:
    source = _source()
    example = source.examples[0]
    base = work_tree_revision(source, example)

    tex = _edited(source, **{"files/report/main.tex": "other"})
    manifest = _edited(source, **{"version.yaml": "other"})
    pack = replace(source, inputs=replace(source.inputs, extra=("pack.yaml:p2",)))

    assert work_tree_revision(tex, example) == base
    assert len({base, work_tree_revision(manifest, example), work_tree_revision(pack, example)}) == 3
    assert work_tree_revision(source, source.examples[1]) != base
