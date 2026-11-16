"""Тулы `pack_outcome_inputs` и `pack_outcome` (template-studio-outcome.md, 4.7, срез O3) без HTTP и без диска.

Служба результата подменена: проверяется, что тул передаёт ей (состояние, набор данных, вводные, `include`), как
переводит отказы в понятные сообщения и как гард раздела останавливает вызов до службы. Вид результата собран из
настоящего ядра на настоящих версиях репозитория.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.enums import EditFormat
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.mcp.entities import MCP_PACKS_SCOPE, McpToolGroup
from hse_doc_studio.core.mcp.errors import McpError, McpErrorCode
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.outcome.payload import to_json
from hse_doc_studio.core.pack_studio.preview import auto_examples
from hse_doc_studio.core.rate_limit import PACK_OUTCOME
from hse_doc_studio.infra.ratelimit.memory import InMemoryRateLimiter
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.mcp.call_tool import CallMcpToolUC, lacks_scope
from hse_doc_studio.use_cases.mcp.catalog import RULES_BY_NAME, McpToolEntry
from hse_doc_studio.use_cases.mcp.tools import pack_outcome as tools
from hse_doc_studio.use_cases.mcp.tools import pack_outcome_view as view
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError
from hse_doc_studio.use_cases.pack_studio.access import PackStudioAccess
from hse_doc_studio.use_cases.pack_studio.outcome.resolve import resolve
from hse_doc_studio.use_cases.pack_studio.outcome_service import OutcomeReply, OutcomeRequest, PackOutcomeService

_REPO_PACKS = Path(__file__).resolve().parents[6] / "packs"
VKR = ("hse-cs-se", "vkr", "2026.1.2")
COURSEWORK = ("hse-cs-sse", "coursework", "2026.1.6")
TODAY = date(2026, 11, 16)
WS = uuid4()
ACTOR = Actor.user("u1", source=ActorSource.pat, scopes=frozenset({"mcp", "packs"}))


@pytest.fixture(autouse=True)
def _actor() -> Iterator[None]:
    set_current_actor(ACTOR)
    set_interface_language("ru")
    yield
    set_current_actor(None)
    set_interface_language(None)


@pytest.fixture(scope="module")
def repo() -> YamlTemplateRepository:
    return YamlTemplateRepository(_REPO_PACKS)


def body_of(
    repo: YamlTemplateRepository,
    ref: tuple[str, str, str] = VKR,
    inputs: dict[str, str] | None = None,
    include: frozenset[Any] = frozenset(),
    state: str = "work_tree",
) -> dict[str, Any]:
    """Тело ответа `PackOutcome`: результат ядра и поля границы запроса, как отдаёт служба."""
    version = repo.get_version(*ref)
    assert version is not None
    outcome = resolve(version, inputs or {}, auto_examples(version)[0], TODAY, include=include, revision="sha256-test")
    return {
        "workspace_id": str(WS),
        "pack": ref[0],
        "template": ref[1],
        "version": ref[2],
        "state": state,
        **to_json(outcome),
    }


# ── вид результата ───────────────────────────────────────────────────────────


def test__view__compact_text__lists_the_bundle_with_final_file_names_and_reasons(repo: YamlTemplateRepository) -> None:
    body = body_of(repo)

    text = view.build_view(body, view.ViewOptions()).text

    active = [d for d in body["documents"] if d["state"] == "active"]
    assert f"Документы: {len(active)} в комплекте из {len(body['documents'])}" in text
    for doc in active:
        assert f"  + {doc['id']}: {doc['instances'][0]['file_name']}" in text
    assert "  - nda: inactive (builtin_gate: meta.nda is on (meta.nda=no))" in text
    assert "  - annotation: absent (supported_kinds: kind in [research] (kind=project))" in text
    assert "Предупреждений нет." in text


def test__view__compact_is_much_smaller_than_the_full_structure(repo: YamlTemplateRepository) -> None:
    body = body_of(repo, include=frozenset({"checks", "branches"}))
    everything = view.SECTIONS

    compact = view.build_view(body, view.ViewOptions(sections=everything))
    full = view.build_view(body, view.ViewOptions(sections=everything, detail="full", trace=True))

    assert len(compact.text) < len(full.text) / 2
    assert len(view.dump(compact.data)) < len(view.dump(full.data)) / 3
    assert len(compact.text) < len(json.dumps(body, ensure_ascii=False)) / 8


def test__view__sections_follow_the_request_in_the_result_order(repo: YamlTemplateRepository) -> None:
    body = body_of(repo)

    result = view.build_view(body, view.ViewOptions(sections=view.split_sections(["route", "meta"])))

    assert list(result.data["sections"]) == ["meta", "route"]
    assert result.text.index("Поля проекта:") < result.text.index("Маршруты подписания:")
    assert "Документы:" not in result.text
    # Сводка по всем разделам всегда: агент видит масштаб, даже запросив один раздел.
    assert result.data["summary"]["documents"] == sum(1 for d in body["documents"] if d["state"] == "active")
    assert result.text.splitlines()[2].startswith("Сводка: documents ")


def test__view__without_include_the_expensive_sections_say_they_are_not_calculated(
    repo: YamlTemplateRepository,
) -> None:
    result = view.build_view(body_of(repo), view.ViewOptions(sections=("checks", "branches")))

    assert "Проверки: не посчитаны (include: checks)" in result.text
    assert "Ветки: не посчитаны (include: branches)" in result.text
    assert result.data["sections"] == {"checks": None, "branches": None}


def test__view__checks_and_branches_when_calculated(repo: YamlTemplateRepository) -> None:
    body = body_of(repo, COURSEWORK, include=frozenset({"checks", "branches"}))

    result = view.build_view(body, view.ViewOptions(sections=("checks", "branches")))

    enabled = sum(1 for c in body["checks"] if c["enabled"])
    assert f"Проверки: {enabled} включены из {len(body['checks'])}" in result.text
    assert "Что если сменить вводную:" in result.text
    assert body["branches"]
    for branch in body["branches"]:
        assert f"  {branch['input']} = {branch['chosen']}; " in result.text
    assert {b["input"] for b in result.data["sections"]["branches"]} == {b["input"] for b in body["branches"]}


def test__view__trace__only_decisions_behind_the_shown_elements_and_tags_on_the_elements(
    repo: YamlTemplateRepository,
) -> None:
    body = body_of(repo)

    plain = view.build_view(body, view.ViewOptions(sections=("documents",)))
    traced = view.build_view(body, view.ViewOptions(sections=("documents",), trace=True))

    assert "trace" not in plain.data
    assert "Трасса" not in plain.text
    assert "[t1" not in plain.text
    shown = {w for d in body["documents"] for w in [*d["why"], *(x for v in d["variants"] for x in v["why"])]}
    assert {e["id"] for e in traced.data["trace"]} == shown
    assert len(traced.data["trace"]) < len(body["trace"])
    assert f"Трасса ({len(shown)} решений" in traced.text
    first = body["documents"][0]
    assert f"{first['id']}: {first['instances'][0]['file_name']}" in traced.text
    assert "[" + ",".join(first["why"]) + "]" in traced.text
    line = next(ln for ln in traced.text.splitlines() if ln.startswith("  t1 "))
    assert line == (
        "  t1 held gate supported_kinds: kind in [project] (kind=project)"
        " | files/technical_specification/doc.yaml#/supported_kinds | documents:technical_specification"
    )


def test__view__trace_is_capped(repo: YamlTemplateRepository, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(view, "MAX_TRACE", 5)

    result = view.build_view(body_of(repo), view.ViewOptions(sections=("documents",), trace=True))

    assert len(result.data["trace"]) == 5
    assert result.truncated is True


def test__view__full_structure_has_no_why_without_trace_and_keeps_it_with_trace(repo: YamlTemplateRepository) -> None:
    body = body_of(repo)

    without = view.build_view(body, view.ViewOptions(sections=view.SECTIONS[:6], detail="full"))
    with_trace = view.build_view(body, view.ViewOptions(sections=view.SECTIONS[:6], detail="full", trace=True))

    assert '"why"' not in json.dumps(without.data["sections"])
    assert '"why"' in json.dumps(with_trace.data["sections"])
    assert without.data["out_of_scope"] == body["out_of_scope"]
    assert "Не входит в результат: " in without.text
    # Структура раздела `points` не тащит маршрут, он отдельным разделом `route`.
    assert all("route" not in p for p in without.data["sections"]["points"])
    assert {r["point"] for r in without.data["sections"]["route"]} == {p["id"] for p in body["points"]}


def test__view__warning_step_without_person_comes_from_the_result(repo: YamlTemplateRepository) -> None:
    body = body_of(repo, VKR, {"supervisor": "none"})

    result = view.build_view(body, view.ViewOptions())

    assert [w["code"] for w in result.data["warnings"]] == ["step_without_person"] * len(result.data["warnings"])
    assert result.data["warnings"]
    assert "Предупреждения (" in result.text
    assert "  ! точка " in result.text
    # Предупреждение выведено тем же правилом, что у линтера результата: по шагам и участникам.
    steps_without = [
        (p["id"], n)
        for p in body["points"]
        for n, step in enumerate(p["route"]["steps"], start=1)
        for person in step
        if person["persona"] not in {x["persona"] for x in body["participants"] if x["present"]}
    ]
    assert len(result.data["warnings"]) == len(steps_without)


def test__view__english_interface__english_text(repo: YamlTemplateRepository) -> None:
    result = view.build_view(body_of(repo, VKR, {"supervisor": "none"}), view.ViewOptions(lang="en"))

    for phrase in (
        "Documents: ",
        "Participants: ",
        "Submission points: ",
        "Signing routes:",
        "Warnings (",
        "Inputs: all defaults",
    ):
        assert phrase in result.text, phrase
    assert "waits for" in result.text
    assert "Документы" not in result.text
    assert "example auto:normal" in result.text.splitlines()[0]


def test__view__inputs_line__full_lists_every_input_and_compact_only_the_given(repo: YamlTemplateRepository) -> None:
    body = body_of(repo, VKR, {"kind": "research"})

    compact = view.build_view(body, view.ViewOptions(requested={"kind": "research"}))
    full = view.build_view(body, view.ViewOptions(detail="full", requested={"kind": "research"}))

    assert "Вводные заданы: kind=research; остальные по умолчанию" in compact.text
    assert "Вводные: lang=ru, kind=research, staffing=solo" in full.text


def test__view__loc_and_condition_helpers() -> None:
    assert view.loc({"ru": "а", "en": "a"}, "en") == "a"
    assert view.loc({"ru": "а"}, "en") == "а"
    assert view.loc(None, "ru") == ""
    entry = {
        "join": "any",
        "terms": [
            {"op": "equals", "subject": "x", "expected": ["1"]},
            {"op": "contains_any", "subject": "m", "expected": ["a", "b"]},
            {"op": "present", "subject": "p", "expected": []},
            {"op": "truthy", "subject": "t", "expected": []},
        ],
        "actual": {"x": "2"},
    }
    assert view.condition_of(entry) == "x = 1 or m contains any of [a, b] or p is present or t is on (x=2)"


# ── аргументы ────────────────────────────────────────────────────────────────


def test__args__state_include_and_inputs_are_validated() -> None:
    assert tools._state_arg({}) == "work_tree"
    assert tools._state_arg({"state": "base"}) == "base"
    assert tools._sections_arg({}) == view.DEFAULT_SECTIONS
    assert tools._sections_arg({"include": "route, meta"}) == ("meta", "route")
    assert tools._sections_arg({"include": ["all"]}) == view.SECTIONS
    assert tools._sections_arg({"include": []}) == view.DEFAULT_SECTIONS
    assert tools._inputs_arg({"inputs": {"a": "x", "b": True, "c": False, "d": 3}}) == {
        "a": "x",
        "b": "yes",
        "c": "no",
        "d": "3",
    }
    assert tools._inputs_arg({}) == {}


@pytest.mark.parametrize(
    ("fn", "args", "needle"),
    [
        (tools._state_arg, {"state": "tail"}, "state"),
        (tools._sections_arg, {"include": ["documents", "bogus"]}, "bogus"),
        (tools._sections_arg, {"include": 5}, "include"),
        (tools._inputs_arg, {"inputs": ["kind"]}, "inputs"),
        (tools._inputs_arg, {"inputs": {"k": ["x"]}}, "inputs.k"),
        (tools._inputs_arg, {"inputs": {"k": "x" * 129}}, "inputs.k"),
        (tools._inputs_arg, {"inputs": {f"k{i}": "x" for i in range(65)}}, "64"),
    ],
)
def test__args__bad_values__argument_error_names_the_argument(fn: Any, args: dict[str, object], needle: str) -> None:
    with pytest.raises(ArgumentError, match=needle):
        fn(args)


# ── перевод отказов службы ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("code", "ctx", "needle"),
    [
        (
            PackStudioErrorCode.inputs_invalid,
            {"field": "kind", "value": "zzz", "reason": "not in the list"},
            "pack_outcome_inputs",
        ),
        (PackStudioErrorCode.diff_base_unavailable, {"reason": "no_git"}, "state=work_tree"),
        (PackStudioErrorCode.diff_base_unavailable, {"reason": "no_base"}, "state=head"),
        (PackStudioErrorCode.diff_base_unavailable, {"reason": "new_version"}, "Версия новая"),
        (PackStudioErrorCode.outcome_busy, {"reason": "timeout", "retry_after_s": 2}, "через 2 с"),
        (PackStudioErrorCode.version_unreadable, {"reason": "bad yaml"}, "pack_lint"),
    ],
)
def test__outcome_hint__says_what_to_do_next(code: PackStudioErrorCode, ctx: dict[str, object], needle: str) -> None:
    hint = tools.outcome_hint(PackStudioError(code, **ctx))

    assert hint is not None
    assert needle in hint


def test__outcome_hint__codes_without_advice_have_none() -> None:
    assert tools.outcome_hint(PackStudioError(PackStudioErrorCode.version_not_found)) is None
    assert tools.outcome_hint(PackStudioError(PackStudioErrorCode.diff_base_unavailable, reason="other")) is None


# ── тулы со службой-заменой ──────────────────────────────────────────────────


class _Service:
    def __init__(self, body: dict[str, Any] | None = None, error: Exception | None = None) -> None:
        self.calls: list[tuple[str, tuple[Any, ...]]] = []
        self._body = body
        self._error = error

    async def outcome(
        self, actor: Actor, ws: UUID, pack: str, template: str, version: str, request: OutcomeRequest
    ) -> OutcomeReply:
        self.calls.append(("outcome", (actor, ws, pack, template, version, request)))
        if self._error is not None:
            raise self._error
        return OutcomeReply("etag", self._body)

    async def inputs(self, actor: Actor, ws: UUID, pack: str, template: str, version: str, state: str) -> OutcomeReply:
        self.calls.append(("inputs", (actor, ws, pack, template, version, state)))
        if self._error is not None:
            raise self._error
        return OutcomeReply("etag", self._body)


class _Access:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.required: list[Actor] = []

    async def require(self, actor: Actor) -> None:
        self.required.append(actor)
        if self.error is not None:
            raise self.error


class _Deps:
    def __init__(self, service: _Service, access: _Access) -> None:
        self._by_type: dict[object, object] = {PackOutcomeService: service, PackStudioAccess: access}

    async def get(self, dependency_type: Any, component: str | None = None) -> Any:
        return self._by_type[dependency_type]


def _ctx() -> AgentToolContext:
    return AgentToolContext(project_id=UUID(int=0), model="mcp-client", edit_format=EditFormat.search_replace)


def _tool(cls: Any, service: _Service, access: _Access | None = None) -> Any:
    return cls(_Deps(service, access or _Access()))


_ARGS = {"workspace_id": str(WS), "version": "hse-cs-se/vkr/2026.1.2"}


async def test__outcome_tool__passes_state_example_inputs_and_the_expensive_sections_to_the_service(
    repo: YamlTemplateRepository,
) -> None:
    service = _Service(body_of(repo, state="head"))
    tool = _tool(tools.PackOutcomeTool, service)

    result = await tool.handle(
        _ctx(),
        {
            **_ARGS,
            "state": "head",
            "example": "auto:long",
            "inputs": {"kind": "research", "meta.nda": True},
            "include": ["documents", "checks", "branches"],
        },
    )

    assert result.is_error is False, result.text
    ((name, (actor, ws, pack, template, version, request)),) = service.calls
    assert (name, actor, ws, (pack, template, version)) == ("outcome", ACTOR, WS, VKR)
    assert request == OutcomeRequest(
        state="head",
        example="auto:long",
        inputs={"kind": "research", "meta.nda": "yes"},
        include=frozenset({"checks", "branches"}),
    )
    assert "[head]" in result.text.splitlines()[0]
    assert "Документы:" in result.text
    assert "Участники:" not in result.text


async def test__outcome_tool__default_request_asks_for_no_expensive_part(repo: YamlTemplateRepository) -> None:
    service = _Service(body_of(repo))

    await _tool(tools.PackOutcomeTool, service).handle(_ctx(), _ARGS)

    request = service.calls[0][1][-1]
    assert request == OutcomeRequest(state="work_tree", example=None, inputs={}, include=frozenset())


async def test__outcome_tool__formats(repo: YamlTemplateRepository) -> None:
    body = body_of(repo)
    tool = _tool(tools.PackOutcomeTool, _Service(body))

    text = await tool.handle(_ctx(), _ARGS)
    structured = await tool.handle(_ctx(), {**_ARGS, "format": "json"})
    both = await tool.handle(_ctx(), {**_ARGS, "format": "both"})

    assert text.text.startswith("hse-cs-se/vkr/2026.1.2 [work_tree]")
    assert json.loads(structured.text)["fingerprint"] == body["fingerprint"]
    assert json.loads(both.text)["text"] == text.text
    assert json.loads(both.text)["data"] == json.loads(structured.text)


@pytest.mark.parametrize(
    ("error", "code", "hint"),
    [
        (
            PackStudioError(PackStudioErrorCode.inputs_invalid, field="kind", value="zzz", reason="not in the list"),
            "inputs_invalid",
            "pack_outcome_inputs",
        ),
        (
            PackStudioError(PackStudioErrorCode.diff_base_unavailable, reason="new_version"),
            "diff_base_unavailable",
            "Версия новая",
        ),
        (
            PackStudioError(PackStudioErrorCode.outcome_busy, reason="overloaded", retry_after_s=2),
            "outcome_busy",
            "через 2 с",
        ),
        (PackStudioError(PackStudioErrorCode.version_unreadable, reason="bad"), "version_unreadable", "pack_lint"),
        (PackStudioError(PackStudioErrorCode.version_not_found), "version_not_found", None),
    ],
)
@pytest.mark.parametrize("cls", [tools.PackOutcomeTool, tools.PackOutcomeInputsTool])
async def test__tools__service_refusal__code_fields_and_hint_as_a_tool_error(
    cls: Any, error: PackStudioError, code: str, hint: str | None
) -> None:
    result = await _tool(cls, _Service(error=error)).handle(_ctx(), _ARGS)

    assert result.is_error is True
    body = json.loads(result.text)
    assert body["code"] == code
    assert body["detail"]
    for key, value in error.ctx.items():
        assert body[key] == value
    if hint is None:
        assert "hint" not in body
    else:
        assert hint in body["hint"]


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (PackStudioError(PackStudioErrorCode.pack_scope_required), "pack_scope_required"),
        (PackStudioError(PackStudioErrorCode.pack_studio_forbidden), "pack_studio_forbidden"),
        (PackStudioError(PackStudioErrorCode.pack_studio_disabled), "pack_studio_disabled"),
    ],
)
@pytest.mark.parametrize("cls", [tools.PackOutcomeTool, tools.PackOutcomeInputsTool])
async def test__tools__section_scope_and_right_are_checked_before_the_service(
    cls: Any, error: PackStudioError, code: str
) -> None:
    service, access = _Service(body={}), _Access(error)

    result = await _tool(cls, service, access).handle(_ctx(), _ARGS)

    assert result.is_error is True
    assert json.loads(result.text)["code"] == code
    assert access.required == [ACTOR]
    assert service.calls == []


async def test__inputs_tool__compact_dictionary_with_labels_and_defaults() -> None:
    kind_values = [
        {"value": "project", "label": {"ru": "Проект", "en": "Project"}},
        {"value": "research", "label": None},
    ]
    big_values = [{"value": str(i), "label": None} for i in range(50)]
    body = {
        "workspace_id": str(WS),
        "pack": "p",
        "template": "t",
        "version": "v",
        "state": "work_tree",
        "revision": "sha256-x",
        "default_example": "auto:normal",
        "examples": [{"id": "auto:normal", "error": None}, {"id": "bad.yaml", "error": "broken"}],
        "inputs": [
            {
                "id": "kind",
                "group": "project",
                "type": "select",
                "label": {"ru": "Вид работы", "en": "Kind"},
                "values": kind_values,
                "default": "project",
                "affects": ["documents"],
                "rules": 3,
            },
            {
                "id": "variant.big",
                "group": "variants",
                "type": "select",
                "label": None,
                "values": big_values,
                "default": "0",
                "affects": [],
                "rules": 0,
            },
        ],
        "defaults": {"kind": "project"},
    }

    result = await _tool(tools.PackOutcomeInputsTool, _Service(body)).handle(_ctx(), {**_ARGS, "state": "base"})

    data = json.loads(result.text)
    assert (data["version"], data["state"], data["default_example"]) == ("p/t/v", "work_tree", "auto:normal")
    assert data["examples"] == [{"id": "auto:normal"}, {"id": "bad.yaml", "error": "broken"}]
    kind, big = data["inputs"]
    assert kind == {
        "id": "kind",
        "group": "project",
        "type": "select",
        "default": "project",
        "values": ["project", "research"],
        "affects": ["documents"],
        "rules": 3,
        "label": "Вид работы",
        "value_labels": {"project": "Проект"},
    }
    assert len(big["values"]) == 40
    assert big["values_total"] == 50
    assert "pack_outcome" in data["hint"]


async def test__inputs_tool__passes_the_state() -> None:
    service = _Service(
        {
            "pack": "p",
            "template": "t",
            "version": "v",
            "state": "head",
            "revision": "r",
            "default_example": "e",
            "examples": [],
            "inputs": [],
        }
    )

    await _tool(tools.PackOutcomeInputsTool, service).handle(_ctx(), {**_ARGS, "state": "head"})

    ((name, (_, ws, pack, template, version, state)),) = service.calls
    assert (name, ws, (pack, template, version), state) == ("inputs", WS, VKR, "head")


@pytest.mark.parametrize("cls", [tools.PackOutcomeTool, tools.PackOutcomeInputsTool])
async def test__tools__version_must_be_pack_template_version(cls: Any) -> None:
    service = _Service(body={})

    with pytest.raises(ArgumentError, match="version"):
        await _tool(cls, service).handle(_ctx(), {"workspace_id": str(WS), "version": "vkr"})
    with pytest.raises(ArgumentError, match="workspace_id"):
        await _tool(cls, service).handle(_ctx(), {"workspace_id": "x", "version": "a/b/c"})

    assert service.calls == []


# ── каталог: права, область токена, частота ──────────────────────────────────

_NAMES = ("pack_outcome_inputs", "pack_outcome")


@pytest.mark.parametrize("name", _NAMES)
def test__catalog_rule__read_only_in_the_packs_group_with_scope_and_the_outcome_rate(name: str) -> None:
    rule = RULES_BY_NAME[name]

    assert rule.meta.group is McpToolGroup.packs
    assert rule.meta.read_only
    assert not rule.meta.dangerous
    assert rule.scope == MCP_PACKS_SCOPE
    assert rule.rate is PACK_OUTCOME
    assert not rule.needs_project
    assert not rule.guards_write


@pytest.mark.parametrize("name", _NAMES)
def test__catalog_rule__token_without_the_packs_scope_does_not_get_the_tool(name: str) -> None:
    from hse_doc_studio.core.agent.entities import ToolSpec  # noqa: PLC0415
    from hse_doc_studio.core.agent.tools import ToolDefinition  # noqa: PLC0415
    from hse_doc_studio.core.enums import ToolKind  # noqa: PLC0415

    spec = ToolSpec(name=name, description="", parameters={"type": "object", "properties": {}})
    entry = McpToolEntry(rule=RULES_BY_NAME[name], definition=ToolDefinition(spec, ToolKind.read, object()))  # type: ignore[arg-type]

    assert lacks_scope(Actor.user("u1", source=ActorSource.pat, scopes=frozenset({"mcp"})), entry)
    assert not lacks_scope(ACTOR, entry)
    # Локально и в сессии браузера прав токена нет: гард раздела остаётся единственным.
    assert not lacks_scope(Actor.local(), entry)


@pytest.mark.parametrize("name", _NAMES)
async def test__rate__twenty_a_second_per_person_shared_by_both_tools_and_the_http_routes(name: str) -> None:
    now = [100.0]
    limiter = InMemoryRateLimiter(clock=lambda: now[0])
    entry = McpToolEntry(rule=RULES_BY_NAME[name], definition=None)  # type: ignore[arg-type]
    # Расход от HTTP-маршрутов (`api/rate_limit.py`): тот же ключ `user:<id>` и то же правило.
    for _ in range(PACK_OUTCOME.limit - 1):
        assert (await limiter.hit(PACK_OUTCOME, f"user:{ACTOR.id}")).allowed

    await CallMcpToolUC._rate(ACTOR, entry, limiter)
    with pytest.raises(McpError) as refused:
        await CallMcpToolUC._rate(ACTOR, entry, limiter)

    assert refused.value.code is McpErrorCode.rate_limited
    assert refused.value.retry_after_s == 1
    # Другой человек не затронут, через секунду окно открывается.
    other = Actor.user("u2", source=ActorSource.pat, scopes=frozenset({"mcp", "packs"}))
    await CallMcpToolUC._rate(other, entry, limiter)
    now[0] += 1.01
    await CallMcpToolUC._rate(ACTOR, entry, limiter)
