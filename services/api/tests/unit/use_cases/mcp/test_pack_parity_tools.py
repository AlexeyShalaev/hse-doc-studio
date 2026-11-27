"""Тулы Студии шаблонов «вровень с интерфейсом» (git по шагам, пространства, сценарии, правки, `pack_help`) без HTTP.

Службы подменены: проверяется, что гард раздела (область `packs` и право) останавливает вызов до службы, что
деструктивные действия без `confirm` ничего не делают, что секреты не принимаются, как разбирается JSON Pointer и что
каталог и справка согласованы.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.enums import EditFormat, ToolKind
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.mcp.entities import MCP_PACKS_SCOPE
from hse_doc_studio.core.pack_studio.entities import WorkspaceKind
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.git_flow import ChangeStatus, FileChange
from hse_doc_studio.use_cases.mcp.catalog import MCP_TOOL_CLASSES, RULES_BY_NAME
from hse_doc_studio.use_cases.mcp.tools import (
    pack_changes,
    pack_edit,
    pack_forms,
    pack_git,
    pack_help,
    pack_scenarios,
    pack_signatures,
    pack_workspaces,
)
from hse_doc_studio.use_cases.mcp.tools import packs as packs_tools
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError
from hse_doc_studio.use_cases.mcp.tools.packs import default_hint
from hse_doc_studio.use_cases.pack_studio.access import PackStudioAccess
from hse_doc_studio.use_cases.pack_studio.files import PackFilesService
from hse_doc_studio.use_cases.pack_studio.git import PackGitService
from hse_doc_studio.use_cases.pack_studio.model import PackModelService
from hse_doc_studio.use_cases.pack_studio.workspaces import PackWorkspaceService

WS = str(uuid4())
ACTOR = Actor.user("u1", source=ActorSource.pat, scopes=frozenset({"mcp", "packs"}))
VERSION = "demo/report/2026.1.1"

NEW_TOOLS = (
    pack_help.PackHelpTool,
    pack_edit.PackTreeTool,
    pack_edit.PackModelTool,
    pack_edit.PackHintsTool,
    pack_edit.PackDocLibraryTool,
    pack_edit.PackSubmissionTool,
    pack_edit.PackSubmissionEditTool,
    pack_edit.PackPatchYamlTool,
    pack_edit.PackMoveFileTool,
    pack_edit.PackDeleteFileTool,
    pack_edit.PackModelActionTool,
    pack_git.PackGitBranchesTool,
    pack_git.PackGitBranchTool,
    pack_git.PackGitCommitTool,
    pack_git.PackGitDiffTool,
    pack_git.PackGitChecksTool,
    pack_git.PackGitMergeBaseTool,
    pack_git.PackGitStartOverTool,
    pack_workspaces.PackListCredentialsTool,
    pack_workspaces.PackWorkspaceCreateTool,
    pack_workspaces.PackWorkspaceRefreshTool,
    pack_workspaces.PackWorkspaceDeleteTool,
    pack_workspaces.PackOfficialTool,
    pack_workspaces.PackOfficialOpenTool,
    pack_workspaces.PackCatalogTool,
    pack_scenarios.PackScenarioListTool,
    pack_scenarios.PackScenarioWriteTool,
    pack_scenarios.PackScenarioDeleteTool,
    pack_scenarios.PackScenarioRunTool,
    pack_scenarios.PackOutcomeAtlasTool,
    pack_scenarios.PackOutcomeExplainTool,
    pack_scenarios.PackOutcomeMatrixTool,
    # Студия шаблонов целиком (pack-studio-mcp.md).
    pack_changes.PackChangesTool,
    pack_forms.PackChecksTool,
    pack_forms.PackVersionNumberTool,
    pack_signatures.PackSignatureRenderTool,
    pack_signatures.PackSignatureCheckTool,
)


@pytest.fixture(autouse=True)
def _actor() -> Iterator[None]:
    set_current_actor(ACTOR)
    set_interface_language("ru")
    yield
    set_current_actor(None)
    set_interface_language(None)


class _Access:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.required: list[Actor] = []

    async def require(self, actor: Actor) -> None:
        self.required.append(actor)
        if self.error is not None:
            raise self.error


class _Deps:
    def __init__(self, access: _Access, services: dict[object, object] | None = None) -> None:
        self._by_type: dict[object, object] = {PackStudioAccess: access, **(services or {})}

    async def get(self, dependency_type: Any, component: str | None = None) -> Any:
        return self._by_type[dependency_type]


def _ctx() -> AgentToolContext:
    return AgentToolContext(project_id=UUID(int=0), model="mcp-client", edit_format=EditFormat.search_replace)


class _Recorder:
    """Любой вызов записывается; ответ не нужен: тесты проверяют, что вызова не было."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __getattr__(self, name: str) -> Any:
        async def call(*_: Any, **__: Any) -> Any:
            self.calls.append(name)
            raise AssertionError(f"unexpected call {name}")

        return call


# ── каталог ──────────────────────────────────────────────────────────────────


def test__catalog__new_tools_have_pack_scope_matching_kind_and_are_not_dangerous() -> None:
    for cls in NEW_TOOLS:
        rule = RULES_BY_NAME[cls.spec.name]
        assert cls in MCP_TOOL_CLASSES, cls.spec.name
        assert rule.scope == MCP_PACKS_SCOPE, cls.spec.name
        assert rule.meta.kind is cls.kind, cls.spec.name
        assert rule.meta.group.value == "packs"
        assert not rule.needs_project
        # Опасным остаётся только pack_propose; деструктивные закрыты confirm, а не выключены.
        assert not rule.meta.dangerous, cls.spec.name


def test__catalog__rate_rules_match_the_endpoints() -> None:
    names = {n: (r.rate.name if (r := RULES_BY_NAME[n]).rate else None) for n in RULES_BY_NAME}
    assert names["pack_scenario_run"] == "pack_outcome"
    assert names["pack_outcome_explain"] == "pack_outcome"
    assert names["pack_outcome_atlas"] == "pack_atlas"
    assert names["pack_outcome_matrix"] == "pack_impact"
    assert names["pack_git_merge_base"] == "git_sync"
    assert names["pack_workspace_create"] == "git_sync"
    assert names["pack_patch_yaml"] == "upload"


def test__catalog__every_write_tool_and_read_tool_declares_its_kind() -> None:
    reads = {c.spec.name for c in NEW_TOOLS if c.kind is ToolKind.read}
    assert {"pack_tree", "pack_git_diff", "pack_scenario_run", "pack_outcome_atlas", "pack_help"} <= reads
    writes = {c.spec.name for c in NEW_TOOLS if c.kind is ToolKind.write}
    assert {"pack_patch_yaml", "pack_git_commit", "pack_workspace_delete", "pack_scenario_write"} <= writes


@pytest.mark.parametrize("cls", NEW_TOOLS, ids=lambda c: c.spec.name)
def test__specs__schema_has_no_project_id_and_describes_required(cls: Any) -> None:
    schema = cls.spec.parameters
    assert "project_id" not in schema["properties"]
    assert set(schema["required"]) <= set(schema["properties"])
    assert cls.spec.description.startswith("Студия шаблонов:")
    assert not cls.requires_project


def test__help__lists_every_pack_tool_in_a_group() -> None:
    named = {n for _, (_, names) in pack_help.GROUPS.items() for n in names}
    every = {c.spec.name for c in MCP_TOOL_CLASSES if c.spec.name.startswith("pack_")} - {"pack_help"}
    assert every <= named, sorted(every - named)
    assert named <= every | {"pack_help"}, sorted(named - every)


# ── гард раздела ─────────────────────────────────────────────────────────────

_ARGS: dict[str, Any] = {
    "workspace_id": WS,
    "version": VERSION,
    "template": "demo/report",
    "id": "s1",
    "path": "demo/pack.yaml",
    "src": "demo/a",
    "dst": "demo/b",
    "ops": [{"op": "set", "pointer": "/a", "value": 1}],
    "element": {"section": "documents", "id": "x"},
    "action": "rename_field",
    "credential_id": str(uuid4()),
    "name": "x",
}


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (PackStudioError(PackStudioErrorCode.pack_scope_required), "pack_scope_required"),
        (PackStudioError(PackStudioErrorCode.pack_studio_forbidden), "pack_studio_forbidden"),
        (PackStudioError(PackStudioErrorCode.pack_studio_disabled), "pack_studio_disabled"),
    ],
)
@pytest.mark.parametrize("cls", NEW_TOOLS, ids=lambda c: c.spec.name)
async def test__tools__scope_and_right_are_checked_before_any_service(
    cls: Any, error: PackStudioError, code: str
) -> None:
    access = _Access(error)

    result = await cls(_Deps(access)).handle(_ctx(), dict(_ARGS))

    assert result.is_error is True
    body = json.loads(result.text)
    assert body["code"] == code
    assert access.required == [ACTOR]
    if code in {"pack_scope_required", "pack_studio_forbidden"}:
        assert "hint" in body


# ── деструктивные действия и секреты ─────────────────────────────────────────


class _Git(_Recorder):
    async def view(self, *_: Any, **__: Any) -> Any:
        ws = SimpleNamespace(pr_url=None)
        status = SimpleNamespace(uncommitted=[SimpleNamespace(path="a")], branch="b")
        return SimpleNamespace(workspace=ws, status=status)


class _Files(_Recorder):
    async def read(self, *_: Any, **__: Any) -> Any:
        return SimpleNamespace(content=b"x", read_only=None, etag="e")


class _Workspaces(_Recorder):
    async def get(self, *_: Any, **__: Any) -> Any:
        ws = SimpleNamespace(id=uuid4(), label="Репозиторий", kind=WorkspaceKind.git)
        return SimpleNamespace(workspace=ws, busy=False)


@pytest.mark.parametrize(
    ("cls", "args", "service", "fake"),
    [
        (pack_git.PackGitStartOverTool, {"workspace_id": WS}, PackGitService, _Git),
        (pack_edit.PackDeleteFileTool, {"workspace_id": WS, "path": "demo/x.tex"}, PackFilesService, _Files),
        (pack_workspaces.PackWorkspaceDeleteTool, {"workspace_id": WS}, PackWorkspaceService, _Workspaces),
        (
            pack_edit.PackModelActionTool,
            {"workspace_id": WS, "version": VERSION, "action": "remove_document", "document": "report"},
            PackModelService,
            _Recorder,
        ),
    ],
)
async def test__destructive_without_confirm__describes_and_changes_nothing(
    cls: Any, args: dict[str, Any], service: Any, fake: Any
) -> None:
    backend = fake()

    result = await cls(_Deps(_Access(), {service: backend})).handle(_ctx(), args)

    assert result.is_error is False, result.text
    assert "confirm: true" in result.text
    assert not [c for c in backend.calls if c not in {"view", "read", "get"}]


@pytest.mark.parametrize("secret", ["token", "password", "access_token", "private_key", "secret"])
@pytest.mark.parametrize("cls", [pack_workspaces.PackWorkspaceCreateTool, pack_workspaces.PackOfficialOpenTool])
async def test__secrets_in_arguments__refused_with_a_hint_to_use_the_interface(cls: Any, secret: str) -> None:
    tool = cls(_Deps(_Access()))

    with pytest.raises(ArgumentError) as caught:
        await tool.handle(_ctx(), {"url": "https://example.org/x.git", "credential_id": str(uuid4()), secret: "x"})

    assert "интерфейсе" in str(caught.value)
    assert secret in str(caught.value)


# ── JSON Pointer ─────────────────────────────────────────────────────────────


def test__pointer__tokens_escape_and_index() -> None:
    assert pack_edit._tokens("/meta_fields/0/label/ru") == ("meta_fields", 0, "label", "ru")  # noqa: SLF001
    assert pack_edit._tokens("/a~1b/c~0d") == ("a/b", "c~d")  # noqa: SLF001
    assert pack_edit._tokens("") == ()  # noqa: SLF001
    with pytest.raises(ArgumentError):
        pack_edit._tokens("meta")  # noqa: SLF001


def test__yaml_ops__set_remove_insert_move() -> None:
    text = "items:\n  - a\n  - b\n"
    ops = pack_edit._yaml_ops(  # noqa: SLF001
        [
            {"op": "set", "pointer": "/x/y", "value": 1},
            {"op": "remove", "pointer": "/items/0"},
            {"op": "insert", "pointer": "/items", "index": 1, "value": "z"},
            {"op": "insert", "pointer": "/items/-", "value": "end"},
            {"op": "insert", "pointer": "/items/0", "value": "first"},
            {"op": "move", "pointer": "/items/0", "to": 1},
            {"op": "set", "path": ["2026", "k"], "value": 2},
        ],
        text,
    )

    assert [(o.op, o.path, o.index, o.to) for o in ops] == [
        ("set", ("x", "y"), None, None),
        ("delete", ("items", 0), None, None),
        ("insert", ("items",), 1, None),
        ("insert", ("items",), 2, None),
        ("insert", ("items",), 0, None),
        ("move", ("items",), 0, 1),
        ("set", ("2026", "k"), None, None),
    ]


@pytest.mark.parametrize(
    "ops",
    [
        [],
        "x",
        [{"op": "nope", "pointer": "/a"}],
        [{"op": "set", "pointer": "/a"}],
        [{"op": "remove"}],
        [{"op": "move", "pointer": "/a", "to": 1}],
        [{"op": "insert", "pointer": "/nolist/-", "value": 1}],
    ],
)
def test__yaml_ops__invalid__argument_error(ops: Any) -> None:
    with pytest.raises(ArgumentError):
        pack_edit._yaml_ops(ops, "a: 1\n")  # noqa: SLF001


# ── подсказки по кодам ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("code", "needle"),
    [
        (PackStudioErrorCode.version_released, "pack_new_version"),
        (PackStudioErrorCode.stale_file, "pack_read_file"),
        (PackStudioErrorCode.workspace_dirty, "pack_git_commit"),
        (PackStudioErrorCode.merge_conflict, "pack_write_file"),
        (PackStudioErrorCode.lint_failed, "pack_lint"),
        (PackStudioErrorCode.scenario_taken, "if_match"),
        (PackStudioErrorCode.pack_scope_required, "packs"),
    ],
)
def test__default_hint__says_the_next_step(code: PackStudioErrorCode, needle: str) -> None:
    hint = default_hint(PackStudioError(code))

    assert hint is not None
    assert needle in hint


def test__default_hint__unknown_codes_have_none() -> None:
    assert default_hint(PackStudioError(PackStudioErrorCode.version_not_found)) is None


def test__default_hint__english_interface() -> None:
    set_interface_language("en")

    hint = default_hint(PackStudioError(PackStudioErrorCode.version_released))

    assert hint is not None
    assert "immutable" in hint


# ── длинные списки файлов: обрезка названа ───────────────────────────────────


def _git_view(count: int) -> Any:
    changed = [FileChange(f"demo/files/f{i:03}.tex", ChangeStatus.added) for i in range(count)]
    status = SimpleNamespace(
        branch="feature/x", head_sha="a" * 40, ahead=1, behind=0, uncommitted=tuple(changed), changed=tuple(changed)
    )
    workspace = SimpleNamespace(
        base_branch="main",
        work_branch="feature/x",
        pr_url=None,
        ci_status=None,
        fork_url=None,
        license_accepted_at=None,
        remote_url="file:///repo.git",
    )
    return SimpleNamespace(status=status, workspace=workspace, compare_url=None)


class _GitViews:
    def __init__(self, count: int) -> None:
        self._view = _git_view(count)

    async def view(self, *_: Any) -> Any:
        return self._view

    async def diff(self, *_: Any) -> tuple[str, bool]:
        return "+x\n" * 2000, False


async def _call(cls: Any, services: dict[object, object], args: dict[str, Any]) -> Any:
    return await cls(_Deps(_Access(), services)).handle(_ctx(), {"workspace_id": WS, **args})


@pytest.mark.parametrize(("count", "cut"), [(250, True), (3, False)])
async def test__propose_summary__says_when_the_file_list_is_cut(count: int, cut: bool) -> None:
    official = SimpleNamespace(is_official=lambda _: False)
    services = {PackGitService: _GitViews(count), packs_tools.OfficialPacks: official}

    result = await _call(packs_tools.PackProposeTool, services, {})
    body = json.loads(result.text)

    assert (body["changed_total"], len(body["changed"])) == (count, min(count, 200))
    assert body["files_truncated"] is cut
    assert result.truncated is cut
    if cut:
        assert "Показаны первые 200 из 250" in body["files_note"]
        assert "pack_git_diff" in body["files_note"]
    else:
        assert "files_note" not in body


@pytest.mark.parametrize("files_only", [True, False])
async def test__git_diff__says_what_is_cut(files_only: bool) -> None:
    services = {PackGitService: _GitViews(250)}
    args = {"files_only": files_only, "max_chars": 1000}

    text = await _call(pack_git.PackGitDiffTool, services, args)
    both = json.loads((await _call(pack_git.PackGitDiffTool, services, {**args, "format": "json"})).text)

    assert "Показаны первые 100 из 250" in text.text
    assert text.truncated is True
    assert ("Diff обрезан" in text.text) is not files_only
    # В JSON список полный, обрезается только текст diff.
    assert len(both["files"]) == both["changed_total"] == 250
    assert both["truncated"] is not files_only
