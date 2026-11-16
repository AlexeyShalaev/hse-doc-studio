"""Служба атласа: ключ и ETag, 304, кэш, общий анализ, общий расчёт одинаковых запросов, срок и пределы.

Версию службе отдаёт служба результата (`PackOutcomeService.prepare`, срез O2); здесь вместо неё подмена, которая
возвращает готовую версию курсового проекта `hse-cs-sse`, а ключ строит настоящий `PackOutcomeService.key_of`."""

from __future__ import annotations

import asyncio
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.preview import auto_examples
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.pack_studio import outcome_atlas
from hse_doc_studio.use_cases.pack_studio.outcome_atlas import AtlasLimits, PackAtlasService, parse_pins
from hse_doc_studio.use_cases.pack_studio.outcome_service import PackOutcomeService

_ROOT = Path(__file__).resolve().parents[6]
TODAY = date(2026, 11, 16)
_ACTOR: Any = object()  # актора служба атласа только передаёт дальше


def _prepared(revision: str = "sha256-one", token: str = "tree:1", example: int = 0) -> Any:
    version = YamlTemplateRepository(_ROOT / "packs").get_version("hse-cs-sse", "coursework", "2026.1.6")
    assert version is not None
    ref = SimpleNamespace(pack="hse-cs-sse", template="coursework", version="2026.1.6", dir="x/y/z")
    return SimpleNamespace(
        ws=SimpleNamespace(id=uuid4()),
        ref=ref,
        source=SimpleNamespace(token=token, desc=SimpleNamespace(version=version)),
        example=auto_examples(version)[example],
        revision=revision,
        today=TODAY,
        scenario=None,
    )


class _Outcomes:
    """Подмена `PackOutcomeService`: версия готова, ключ настоящий."""

    def __init__(self, prepared: Any) -> None:
        self.current = prepared
        self.states: list[str] = []

    async def prepare(self, _actor: object, _ws: object, _pack: str, _tpl: str, _ver: str, state: str, _ex: Any) -> Any:
        self.states.append(state)
        return self.current

    key_of = staticmethod(PackOutcomeService.key_of)


def _service(outcomes: _Outcomes, **limits: Any) -> PackAtlasService:
    return PackAtlasService(outcomes, limits=AtlasLimits(**limits))  # type: ignore[arg-type]


async def _atlas(service: PackAtlasService, **kwargs: Any) -> Any:
    state = kwargs.pop("state", "work_tree")
    return await service.atlas(_ACTOR, uuid4(), "hse-cs-sse", "coursework", "2026.1.6", state, **kwargs)


class _Count:
    """Считает вызовы функции модуля службы и отпускает их дальше."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
        self.calls = 0
        original = getattr(outcome_atlas, name)

        def counting(*args: Any, **kwargs: Any) -> Any:
            self.calls += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(outcome_atlas, name, counting)


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


@pytest.mark.parametrize("pins", [{"nope": "x"}, {"supervisor": "boss"}])
async def test__atlas__bad_pins_are_inputs_invalid_before_the_queue(pins: dict[str, str]) -> None:
    service = _service(_Outcomes(_prepared()))
    await service._slots.acquire()  # noqa: SLF001 — очередь занята: проверка должна случиться раньше неё

    with pytest.raises(PackStudioError) as caught:
        await _atlas(service, pins=pins)

    assert caught.value.code is PackStudioErrorCode.inputs_invalid
    assert caught.value.ctx["field"] in pins


async def test__atlas__the_state_goes_to_the_outcome_service_and_into_the_body() -> None:
    outcomes = _Outcomes(_prepared())
    service = _service(outcomes)

    head = await _atlas(service, state="head")
    base = await _atlas(service, state="base")

    assert outcomes.states == ["head", "base"]
    assert (head.body["state"], base.body["state"]) == ("head", "base")
    assert head.etag != base.etag


# ── ETag, кэш и общий расчёт ─────────────────────────────────────────────────


async def test__atlas__a_matching_if_none_match_answers_without_calculating(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service(_Outcomes(_prepared()))
    first = await _atlas(service)
    builds = _Count(monkeypatch, "build_atlas")

    again = await _atlas(service, if_none_match=first.etag)
    weak = await _atlas(service, if_none_match=f'W/{first.etag}, "other"')
    other = await _atlas(service, if_none_match='"something-else"')

    assert first.body is not None
    assert (again.etag, again.body) == (first.etag, None)
    assert weak.body is None
    assert other.body is not None
    assert builds.calls == 0  # третий запрос из кэша


async def test__atlas__the_second_request_comes_from_the_cache_and_a_pin_changes_the_etag_only() -> None:
    service = _service(_Outcomes(_prepared()))

    first = await _atlas(service)
    second = await _atlas(service)
    pinned = await _atlas(service, pins={"supervisor": "company"})

    assert second.etag == first.etag
    assert {k: v for k, v in second.body.items() if k != "elapsed_ms"} == {
        k: v for k, v in first.body.items() if k != "elapsed_ms"
    }
    assert pinned.etag != first.etag
    assert pinned.body["rows_total"] == 4
    assert first.body["revision"] == "sha256-one"
    assert first.body["elapsed_ms"] >= 0


async def test__atlas__the_analysis_is_shared_between_pins(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service(_Outcomes(_prepared()))
    analyses = _Count(monkeypatch, "analyze_impact")

    await _atlas(service)
    await _atlas(service, pins={"supervisor": "none"})
    await _atlas(service, pins={"co_supervisor": "yes"})

    assert analyses.calls == 1


async def test__atlas__a_new_revision_or_source_is_a_new_key() -> None:
    outcomes = _Outcomes(_prepared())
    service = _service(outcomes)
    first = await _atlas(service)

    outcomes.current = _prepared(revision="sha256-two")
    revision = await _atlas(service)
    outcomes.current = _prepared(token="git:abc")
    source = await _atlas(service)
    outcomes.current = _prepared(example=1)
    example = await _atlas(service)

    assert len({first.etag, revision.etag, source.etag, example.etag}) == 4
    assert revision.body["revision"] == "sha256-two"


async def test__atlas__equal_simultaneous_requests_share_one_calculation(monkeypatch: pytest.MonkeyPatch) -> None:
    service = _service(_Outcomes(_prepared()))
    builds = _Count(monkeypatch, "build_atlas")

    results = await asyncio.gather(*(_atlas(service) for _ in range(4)))

    assert builds.calls == 1
    assert len({r.etag for r in results}) == 1


# ── Пределы и срок ───────────────────────────────────────────────────────────


async def test__atlas__too_many_rows_is_atlas_too_large_with_limit_and_rows() -> None:
    service = _service(_Outcomes(_prepared()), max_rows=11)

    with pytest.raises(PackStudioError) as caught:
        await _atlas(service)

    assert caught.value.code is PackStudioErrorCode.atlas_too_large
    assert (caught.value.ctx["limit"], caught.value.ctx["rows"]) == (11, 12)
    # Закрепление режет таблицу под предел; анализ из первой попытки уже в кэше.
    ok = await _atlas(service, pins={"supervisor": "company"})
    assert ok.body["rows_total"] == 4


async def test__atlas__an_expired_deadline_is_outcome_busy_with_a_retry_after() -> None:
    service = _service(_Outcomes(_prepared()), timeout_s=0.0, retry_after_s=7)

    with pytest.raises(PackStudioError) as caught:
        await _atlas(service)

    assert caught.value.code is PackStudioErrorCode.outcome_busy
    assert (caught.value.ctx["reason"], caught.value.ctx["retry_after_s"]) == ("timeout", 7)


async def test__atlas__a_full_queue_is_outcome_busy_after_the_deadline() -> None:
    service = _service(_Outcomes(_prepared()), concurrency=1, timeout_s=0.05)
    await service._slots.acquire()  # noqa: SLF001 — единственное место занято

    with pytest.raises(PackStudioError) as caught:
        await _atlas(service)

    assert caught.value.code is PackStudioErrorCode.outcome_busy
    assert caught.value.ctx["reason"] == "overloaded"
    service._slots.release()  # noqa: SLF001


async def test__atlas__the_cache_keeps_at_most_the_configured_number_of_atlases() -> None:
    service = _service(_Outcomes(_prepared()), cache_entries=2)

    for pin in ("university", "company", "none"):
        await _atlas(service, pins={"supervisor": pin})

    assert len(service._atlases) == 2  # noqa: SLF001
