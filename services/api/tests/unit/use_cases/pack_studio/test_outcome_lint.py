"""Служба линтера результата: ключ и ETag, 304, кэш, общий расчёт, срок и пределы, Jinja по кнопке, универсум покрытия.

Версию службе отдаёт служба результата (`PackOutcomeService.prepare`); здесь вместо неё подмена с готовой версией
курсового проекта `hse-cs-sse`, а ключ строит настоящий `PackOutcomeService.key_of`."""

from __future__ import annotations

import asyncio
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from hse_doc_studio.api.schemas.pack_studio_outcome import PackOutcomeLintResponse
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.outcome.lint import finding
from hse_doc_studio.core.pack_studio.preview import PreviewRenderError
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.pack_studio import outcome_lint
from hse_doc_studio.use_cases.pack_studio.outcome_lint import LintLimits, PackOutcomeLintService
from hse_doc_studio.use_cases.pack_studio.outcome_service import PackOutcomeService

_ROOT = Path(__file__).resolve().parents[6]
TODAY = date(2026, 11, 16)
_ACTOR: Any = object()
_SCENARIO = """\
format: 1
name: { ru: Один, en: One }
inputs: { supervisor: company }
assertions:
  - { kind: participant_present, persona: supervisor, present: true }
"""


def _folder() -> Path:
    return _ROOT / "packs" / "hse-cs-sse" / "templates" / "coursework" / "versions" / "2026.1.6"


def _prepared(scenarios: dict[str, bytes] | None = None, token: str = "tree:1", workspace: Any = None) -> Any:
    from hse_doc_studio.core.pack_studio.preview import auto_examples  # noqa: PLC0415

    version = YamlTemplateRepository(_ROOT / "packs").get_version("hse-cs-sse", "coursework", "2026.1.6")
    assert version is not None
    ref = SimpleNamespace(pack="hse-cs-sse", template="coursework", version="2026.1.6", dir="x/y/z")
    texts = {"version.yaml": (_folder() / "version.yaml").read_bytes()}
    return SimpleNamespace(
        ws=SimpleNamespace(id=workspace or uuid4()),
        ref=ref,
        source=SimpleNamespace(
            token=token,
            desc=SimpleNamespace(version=version, examples=()),
            texts=texts,
            scenarios=scenarios or {},
        ),
        example=auto_examples(version)[0],
        revision="sha256-one",
        today=TODAY,
        scenario=None,
    )


class _Outcomes:
    def __init__(self, prepared: Any) -> None:
        self.current = prepared
        self.states: list[str] = []

    async def prepare(
        self, _a: object, _w: object, _p: str, _t: str, _v: str, state: str, _e: Any, _s: Any = None
    ) -> Any:
        self.states.append(state)
        return self.current

    key_of = staticmethod(PackOutcomeService.key_of)


class _Workspaces:
    async def ready(self, _actor: object, _ws: object) -> tuple[Any, Path]:
        return SimpleNamespace(), Path("/work")


class _Probe:
    def __init__(self, fail: bool = False) -> None:
        self.calls = 0
        self.fail = fail

    async def probe(self, _root: Path, _ref: Any, _today: date) -> tuple[Any, ...]:
        self.calls += 1
        if self.fail:
            raise PreviewRenderError("timeout 5s")
        return (finding("jinja-fail-open", "error", "broken template", "fix it", "files/a.tex", None),)


def _service(outcomes: _Outcomes, probe: Any = None, **limits: Any) -> PackOutcomeLintService:
    return PackOutcomeLintService(outcomes, _Workspaces(), probe, limits=LintLimits(**limits))  # type: ignore[arg-type]


async def _lint(service: PackOutcomeLintService, **kwargs: Any) -> Any:
    state = kwargs.pop("state", "work_tree")
    return await service.lint(_ACTOR, uuid4(), "hse-cs-sse", "coursework", "2026.1.6", state, **kwargs)


class _Count:
    def __init__(self, monkeypatch: pytest.MonkeyPatch, name: str) -> None:
        self.calls = 0
        original = getattr(outcome_lint, name)

        def counting(*args: Any, **kwargs: Any) -> Any:
            self.calls += 1
            return original(*args, **kwargs)

        monkeypatch.setattr(outcome_lint, name, counting)


async def test__lint__body_is_accepted_by_the_strict_contract_model_and_counts_agree() -> None:
    service = _service(_Outcomes(_prepared({"one.yaml": _SCENARIO.encode()})))

    reply = await _lint(service)

    body = reply.body
    parsed = PackOutcomeLintResponse.model_validate(body)
    assert (parsed.pack, parsed.template, parsed.version, parsed.state) == (
        "hse-cs-sse",
        "coursework",
        "2026.1.6",
        "work_tree",
    )
    assert parsed.errors == sum(f.severity == "error" for f in parsed.findings)
    assert parsed.warnings == sum(f.severity == "warning" for f in parsed.findings)
    assert parsed.infos == sum(f.severity == "info" for f in parsed.findings)
    assert parsed.jinja == "not_run"
    assert not parsed.atlas_skipped
    assert parsed.coverage.scenarios == 1
    assert parsed.coverage.rows_total == 12
    assert parsed.coverage.rows_touched == 1
    assert {f.rule_id for f in parsed.findings} == {"route-step-without-person", "dimension-no-effect"}
    assert all(f.hint for f in parsed.findings)


async def test__lint__etag_is_stable_if_none_match_answers_304_and_a_scenario_edit_changes_it() -> None:
    outcomes = _Outcomes(_prepared())
    service = _service(outcomes)
    first = await _lint(service)

    same = await _lint(service, if_none_match=first.etag)
    outcomes.current = _prepared({"one.yaml": _SCENARIO.encode()}, workspace=outcomes.current.ws.id)
    edited = await _lint(service, if_none_match=first.etag)

    assert same.body is None
    assert same.etag == first.etag
    assert edited.body is not None
    assert edited.etag != first.etag


async def test__lint__an_unsaved_change_of_the_source_changes_the_etag() -> None:
    outcomes = _Outcomes(_prepared(token="tree:1"))
    service = _service(outcomes)
    one = await _lint(service)
    outcomes.current = _prepared(token="tree:2", workspace=outcomes.current.ws.id)

    two = await _lint(service)

    assert one.etag != two.etag


async def test__lint__is_cached_and_equal_requests_in_flight_share_one_calculation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _Count(monkeypatch, "lint_outcome")
    service = _service(_Outcomes(_prepared()))

    await asyncio.gather(_lint(service), _lint(service), _lint(service))
    await _lint(service)

    assert calls.calls == 1


async def test__lint__jinja_runs_only_on_the_work_tree_and_only_on_request() -> None:
    probe = _Probe()
    service = _service(_Outcomes(_prepared()), probe)

    plain = await _lint(service)
    asked = await _lint(service, jinja=True)
    head = await _lint(service, jinja=True, state="head")

    assert (plain.body["jinja"], asked.body["jinja"], head.body["jinja"]) == ("not_run", "ran", "unavailable")
    assert probe.calls == 1
    assert [f["rule_id"] for f in asked.body["findings"]][0] == "jinja-fail-open"
    assert asked.body["errors"] == 1
    assert plain.body["errors"] == 0
    assert plain.etag != asked.etag


async def test__lint__a_probe_that_dies_becomes_a_finding_and_not_a_refusal() -> None:
    service = _service(_Outcomes(_prepared()), _Probe(fail=True))

    reply = await _lint(service, jinja=True)

    (item,) = [f for f in reply.body["findings"] if f["rule_id"] == "jinja-fail-open"]
    assert item["severity"] == "warning"
    assert "timeout" in item["message"]
    assert reply.body["jinja"] == "ran"


async def test__lint__without_a_probe_a_jinja_request_is_unavailable_and_not_an_error() -> None:
    reply = await _lint(_service(_Outcomes(_prepared())), jinja=True)

    assert reply.body["jinja"] == "unavailable"


async def test__lint__a_table_over_the_limit_keeps_the_static_rules_and_says_so() -> None:
    reply = await _lint(_service(_Outcomes(_prepared()), max_rows=2))

    assert reply.body["atlas_skipped"] is True
    assert [f["rule_id"] for f in reply.body["findings"]] == ["atlas-skipped"]
    assert reply.body["coverage"]["approximate"] is True


async def test__lint__over_the_time_limit_is_outcome_busy_and_nothing_is_cached(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = outcome_lint.lint_outcome

    def slow(*args: Any, **kwargs: Any) -> Any:
        time.sleep(0.2)
        kwargs["check"]()
        return original(*args, **kwargs)

    monkeypatch.setattr(outcome_lint, "lint_outcome", slow)
    service = _service(_Outcomes(_prepared()), timeout_s=0.05)

    with pytest.raises(PackStudioError) as caught:
        await _lint(service)

    assert caught.value.code is PackStudioErrorCode.outcome_busy
    assert caught.value.ctx["reason"] == "timeout"
    assert caught.value.ctx["retry_after_s"] == 5
    monkeypatch.setattr(outcome_lint, "lint_outcome", original)
    service._limits = LintLimits()  # noqa: SLF001
    assert (await _lint(service)).body is not None


async def test__lint__a_busy_queue_refuses_at_once_with_overloaded() -> None:
    service = _service(_Outcomes(_prepared()), concurrency=1, timeout_s=0.05)
    await service._slots.acquire()  # noqa: SLF001

    with pytest.raises(PackStudioError) as caught:
        await _lint(service)

    assert caught.value.ctx["reason"] == "overloaded"


async def test__lint__a_failure_of_the_calculation_is_version_unreadable(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any, **_k: Any) -> Any:
        raise ValueError("bad manifest")

    monkeypatch.setattr(outcome_lint, "lint_outcome", boom)

    with pytest.raises(PackStudioError) as caught:
        await _lint(_service(_Outcomes(_prepared())))

    assert caught.value.code is PackStudioErrorCode.version_unreadable
    assert "bad manifest" in caught.value.ctx["reason"]


async def test__static__gives_only_the_static_rules_for_the_work_tree() -> None:
    outcomes = _Outcomes(_prepared())

    found = await _service(outcomes).static(_ACTOR, uuid4(), "hse-cs-sse", "coursework", "2026.1.6")

    assert outcomes.states == ["work_tree"]
    assert all(f.rule_id not in {"route-step-without-person", "dimension-no-effect"} for f in found)


async def test__universe__is_cached_and_shared_with_the_lint_calculation(monkeypatch: pytest.MonkeyPatch) -> None:
    prepared = _prepared()
    service = _service(_Outcomes(prepared))
    await _lint(service)
    calls = _Count(monkeypatch, "scan_atlas")
    from hse_doc_studio.core.pack_studio.preview import auto_examples  # noqa: PLC0415

    ctx = SimpleNamespace(
        ws=prepared.ws,
        ref=prepared.ref,
        state="work_tree",
        source=prepared.source,
        today=TODAY,
        examples=auto_examples(prepared.source.desc.version),
    )

    universe = await service.universe(ctx)  # type: ignore[arg-type]
    again = await service.universe(ctx)  # type: ignore[arg-type]

    assert universe is again
    assert len(universe.rows) == 12
    assert calls.calls == 0
