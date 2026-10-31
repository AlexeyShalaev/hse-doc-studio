"""Правила приёма push: одна ветка, только вперёд, пути в области автора, без служебных и опасных файлов.

Общая чистая логика для хука `pre-receive` (он импортирует только `core`) и для API, который строит политику.
Область автора считается той же функцией, что и запись файла через API (`core.access.paths`).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Literal
from uuid import UUID

from hse_doc_studio.core.access.entities import Grant, ProjectAcl, Role
from hse_doc_studio.core.access.paths import path_in_author_scope
from hse_doc_studio.core.git_remote.entities import (
    ZERO_SHA,
    PushChange,
    PushPolicy,
    PushViolation,
    PushViolationCode,
)
from hse_doc_studio.core.git_sync.merge.paths import comparison_key, is_safe_path
from hse_doc_studio.core.team import RESERVED_SLUGS, SHARED_DIR

PROJECT_JSON_PATH = ".hse-studio/project.json"
_STUDIO_DIR = ".hse-studio"
_STUDIO_PRIVATE_DIRS = frozenset({"git", "update", "compiles", "chats", "backup", "submissions"})
_SYMLINK_MODE = "120000"
_SUBMODULE_MODE = "160000"


def push_policy_for(
    acl: ProjectAcl, grant: Grant, *, branch: str, max_blob_bytes: int, compat: tuple[int, int]
) -> PushPolicy:
    scope: Literal["all"] | tuple[str, ...] = "all"
    if acl.team and grant.role is not Role.owner and not grant.can_edit_all:
        allowed: list[str] = []
        if grant.persona_slug and grant.persona_slug not in RESERVED_SLUGS:
            allowed.append(grant.persona_slug)
        if acl.shared_enabled:
            allowed.append(SHARED_DIR)
        scope = tuple(allowed)
    return PushPolicy(
        branch=branch,
        team=acl.team,
        shared_enabled=acl.shared_enabled,
        scope=scope,
        max_blob_bytes=max_blob_bytes,
        studio_read_compat=compat[0],
        studio_write_compat=compat[1],
    )


def check_ref_update(policy: PushPolicy, old: str, new: str, ref: str) -> PushViolation | None:
    """Только текущая ветка стора, без создания и удаления веток (S17). Перемотку вперёд проверяет хук по git."""
    if ref != f"refs/heads/{policy.branch}" or ZERO_SHA in (old, new):
        return PushViolation(PushViolationCode.ref_forbidden, ref)
    return None


def check_push(policy: PushPolicy, changes: Sequence[PushChange], project_json: bytes | None) -> list[PushViolation]:
    """Нарушения по итоговой разнице (S18).

    `project_json`: новое содержимое `.hse-studio/project.json`, если он менялся.
    """
    violations: list[PushViolation] = []
    for change in changes:
        found = _path_violation(change.path)
        if found is None and not _in_scope(policy, change.path):
            found = PushViolationCode.path_outside_scope
        if found is None and change.status != "D":
            found = _entry_violation(policy, change)
        if found is not None:
            violations.append(PushViolation(found, change.path))
    if project_json is not None and _schema_newer(policy, project_json):
        violations.append(PushViolation(PushViolationCode.schema_newer, PROJECT_JSON_PATH))
    return violations


def _path_violation(path: str) -> PushViolationCode | None:
    segments = path.split("/")
    if (
        len(segments) > 1
        and comparison_key(segments[0]).rstrip(" .") == _STUDIO_DIR
        and comparison_key(segments[1]).rstrip(" .") in _STUDIO_PRIVATE_DIRS
    ):
        return PushViolationCode.service_dir
    if not is_safe_path(path):
        return PushViolationCode.unsafe_path
    return None


def _in_scope(policy: PushPolicy, path: str) -> bool:
    if policy.scope == "all":
        return True
    acl = ProjectAcl(project_id="", team=True, shared_enabled=policy.shared_enabled)
    for slug in policy.scope:
        persona = None if slug == SHARED_DIR else slug
        if path_in_author_scope(acl, Grant(role=Role.editor, persona_slug=persona), path):
            return True
    return False


def _entry_violation(policy: PushPolicy, change: PushChange) -> PushViolationCode | None:
    if change.mode == _SYMLINK_MODE:
        return PushViolationCode.symlink
    if change.mode == _SUBMODULE_MODE:
        return PushViolationCode.submodule
    if change.size is not None and change.size > policy.max_blob_bytes:
        return PushViolationCode.large_file
    return None


def _schema_newer(policy: PushPolicy, raw: bytes) -> bool:
    """Неразборчивый `project.json` считается новее: сервер не должен принять то, что не прочтёт."""
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return True
    if not isinstance(data, dict):
        return True
    schema = data.get("schema")
    if schema is None:
        return False
    if not isinstance(schema, dict):
        return True
    read_compat, write_compat = schema.get("read_compat", 1), schema.get("write_compat", 1)
    if not isinstance(read_compat, int) or not isinstance(write_compat, int):
        return True
    return read_compat > policy.studio_read_compat or write_compat > policy.studio_write_compat


def clone_url(public_url: str, project_id: UUID) -> str:
    return f"{public_url.rstrip('/')}/git/{project_id}.git"


def policy_to_json(policy: PushPolicy) -> str:
    return json.dumps(
        {
            "branch": policy.branch,
            "team": policy.team,
            "shared_enabled": policy.shared_enabled,
            "scope": policy.scope if policy.scope == "all" else list(policy.scope),
            "owner_or_all": policy.owner_or_all,
            "max_blob_bytes": policy.max_blob_bytes,
            "studio_compat": [policy.studio_read_compat, policy.studio_write_compat],
        }
    )


def policy_from_json(raw: str) -> PushPolicy:
    data: Mapping[str, Any] = json.loads(raw)
    scope = data["scope"]
    read_compat, write_compat = data["studio_compat"]
    return PushPolicy(
        branch=str(data["branch"]),
        team=bool(data["team"]),
        shared_enabled=bool(data["shared_enabled"]),
        scope="all" if scope == "all" else tuple(str(s) for s in scope),
        max_blob_bytes=int(data["max_blob_bytes"]),
        studio_read_compat=int(read_compat),
        studio_write_compat=int(write_compat),
    )
