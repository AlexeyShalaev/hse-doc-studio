from __future__ import annotations

import json
from uuid import UUID

import pytest
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.remote_project import require_mergeable_project

pytestmark = pytest.mark.unit

_ID = UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")


def _project(**changes: object) -> bytes:
    data: dict[str, object] = {"id": str(_ID), "lock": {"pack_id": "p", "template_id": "t", "version": "1"}}
    return json.dumps({**data, **changes}).encode()


def test__require_mergeable_project__same_project__returns_it() -> None:
    assert require_mergeable_project(_project(), _ID).id == _ID


def test__require_mergeable_project__missing_file__not_a_studio_project() -> None:
    with pytest.raises(GitSyncError) as info:
        require_mergeable_project(None, _ID)

    assert info.value.code is GitErrorCode.not_a_studio_project


def test__require_mergeable_project__other_project__unrelated_and_not_adoptable() -> None:
    with pytest.raises(GitSyncError) as info:
        require_mergeable_project(_project(id="00000000-0000-4000-8000-000000000000"), _ID)

    assert info.value.code is GitErrorCode.unrelated_histories
    assert info.value.ctx == {"can_adopt": False}


def test__require_mergeable_project__newer_schema__remote_schema_newer_with_required_studio() -> None:
    newer = {"version": 9, "read_compat": 9, "write_compat": 9, "written_by": "9.0.0"}

    with pytest.raises(GitSyncError) as info:
        require_mergeable_project(_project(schema=newer), _ID)

    assert info.value.code is GitErrorCode.remote_schema_newer
    assert info.value.ctx == {"required_studio": "9.0.0"}
