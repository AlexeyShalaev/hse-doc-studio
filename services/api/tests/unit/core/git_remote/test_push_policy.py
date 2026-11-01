import json
from uuid import UUID

import pytest
from hse_doc_studio.core.access.entities import Grant, ProjectAcl, Role
from hse_doc_studio.core.git_remote.entities import ZERO_SHA, PushChange, PushPolicy, PushViolationCode
from hse_doc_studio.core.git_remote.push_policy import (
    PROJECT_JSON_PATH,
    check_push,
    check_ref_update,
    clone_url,
    policy_from_json,
    policy_to_json,
    push_policy_for,
)

_SHA_A = "a" * 40
_SHA_B = "b" * 40
_MB = 1024 * 1024


def _acl(*, team: bool = True, shared_enabled: bool = True) -> ProjectAcl:
    return ProjectAcl(project_id="p", team=team, shared_enabled=shared_enabled)


def _policy(grant: Grant, *, team: bool = True, shared_enabled: bool = True) -> PushPolicy:
    return push_policy_for(
        _acl(team=team, shared_enabled=shared_enabled), grant, branch="master", max_blob_bytes=95 * _MB, compat=(1, 1)
    )


def _add(path: str, mode: str = "100644", size: int = 10) -> PushChange:
    return PushChange("A", path, mode, size)


def test__push_policy_for__solo_owner_and_edit_all__scope_all() -> None:
    assert _policy(Grant(Role.editor), team=False).scope == "all"
    assert _policy(Grant(Role.owner)).scope == "all"
    assert _policy(Grant(Role.editor, can_edit_all=True)).owner_or_all


def test__push_policy_for__team_author__own_folder_and_shared() -> None:
    assert _policy(Grant(Role.editor, persona_slug="ivanov")).scope == ("ivanov", "shared")
    assert _policy(Grant(Role.editor, persona_slug="ivanov"), shared_enabled=False).scope == ("ivanov",)
    assert _policy(Grant(Role.editor)).scope == ("shared",)
    # Зарезервированный слаг персоной не считается.
    assert _policy(Grant(Role.editor, persona_slug="common")).scope == ("shared",)


def test__check_ref_update__only_existing_head_branch() -> None:
    policy = _policy(Grant(Role.owner))

    assert check_ref_update(policy, _SHA_A, _SHA_B, "refs/heads/master") is None
    for old, new, ref in (
        (_SHA_A, _SHA_B, "refs/heads/feature"),
        (_SHA_A, _SHA_B, "refs/tags/v1"),
        (ZERO_SHA, _SHA_B, "refs/heads/master"),
        (_SHA_A, ZERO_SHA, "refs/heads/master"),
    ):
        violation = check_ref_update(policy, old, new, ref)
        assert violation is not None
        assert violation.code is PushViolationCode.ref_forbidden


def test__check_push__team_author__own_and_shared_ok_other_outside_scope() -> None:
    policy = _policy(Grant(Role.editor, persona_slug="ivanov"))
    changes = [
        _add("ivanov/main.tex"),
        _add("shared/intro.tex"),
        _add("petrov/main.tex"),
        PushChange("D", "petrov/old.tex", None, None),
        PushChange("M", PROJECT_JSON_PATH, "100644", 100),
    ]

    found = check_push(policy, changes, None)

    assert [(v.code, v.path) for v in found] == [
        (PushViolationCode.path_outside_scope, "petrov/main.tex"),
        (PushViolationCode.path_outside_scope, "petrov/old.tex"),
        (PushViolationCode.path_outside_scope, PROJECT_JSON_PATH),
    ]


def test__check_push__shared_disabled__shared_outside_scope() -> None:
    policy = _policy(Grant(Role.editor, persona_slug="ivanov"), shared_enabled=False)

    assert [v.code for v in check_push(policy, [_add("shared/a.tex")], None)] == [PushViolationCode.path_outside_scope]


def test__check_push__rename_is_delete_and_add__both_checked() -> None:
    policy = _policy(Grant(Role.editor, persona_slug="ivanov"))
    changes = [PushChange("D", "petrov/a.tex", None, None), _add("ivanov/a.tex")]

    assert [v.path for v in check_push(policy, changes, None)] == ["petrov/a.tex"]


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (_add("a/../b.tex"), PushViolationCode.unsafe_path),
        (_add(".git/config"), PushViolationCode.unsafe_path),
        (_add("sub/.GIT/hooks/x"), PushViolationCode.unsafe_path),
        (_add(".hse-studio/git/config"), PushViolationCode.service_dir),
        (_add(".hse-studio/update/journal.json"), PushViolationCode.service_dir),
        (_add("link.tex", mode="120000"), PushViolationCode.symlink),
        (_add("vendor", mode="160000", size=None), PushViolationCode.submodule),
        (_add("big.bin", size=96 * _MB), PushViolationCode.large_file),
    ],
)
def test__check_push__owner__unsafe_entries_rejected(change: PushChange, code: PushViolationCode) -> None:
    assert [v.code for v in check_push(_policy(Grant(Role.owner)), [change], None)] == [code]


def test__check_push__owner__project_state_and_any_folder_accepted() -> None:
    changes = [_add(PROJECT_JSON_PATH), _add("petrov/a.tex"), PushChange("D", "old/x.tex", None, None)]

    assert check_push(_policy(Grant(Role.owner)), changes, b'{"schema": {"version": 1}}') == []


@pytest.mark.parametrize(
    "raw",
    [
        b'{"schema": {"version": 3, "read_compat": 2, "write_compat": 1}}',
        b'{"schema": {"version": 3, "read_compat": 1, "write_compat": 3}}',
        b"not json",
        b"[]",
        b'{"schema": "x"}',
        b'{"schema": {"read_compat": "1"}}',
    ],
)
def test__check_push__newer_or_broken_project_json__schema_newer(raw: bytes) -> None:
    found = check_push(_policy(Grant(Role.owner)), [_add(PROJECT_JSON_PATH)], raw)

    assert [(v.code, v.path) for v in found] == [(PushViolationCode.schema_newer, PROJECT_JSON_PATH)]


def test__check_push__legacy_project_json_without_schema__accepted() -> None:
    assert check_push(_policy(Grant(Role.owner)), [_add(PROJECT_JSON_PATH)], json.dumps({"name": "x"}).encode()) == []


def test__policy_json__round_trip() -> None:
    for grant in (Grant(Role.owner), Grant(Role.editor, persona_slug="ivanov")):
        policy = _policy(grant)

        assert policy_from_json(policy_to_json(policy)) == policy
    assert json.loads(policy_to_json(_policy(Grant(Role.owner))))["owner_or_all"] is True


def test__clone_url__strips_trailing_slash() -> None:
    project = UUID("5b0c1d2e-3f40-4152-8364-758697a8b9c0")

    assert clone_url("https://studio.example.org/", project) == (
        "https://studio.example.org/git/5b0c1d2e-3f40-4152-8364-758697a8b9c0.git"
    )
