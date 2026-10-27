from __future__ import annotations

import pytest
from hse_doc_studio.api.git_errors import GIT_ERROR_STATUS, git_error_body
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError


def test__git_error_status__covers_every_code() -> None:
    assert set(GIT_ERROR_STATUS) == set(GitErrorCode)


@pytest.mark.parametrize(
    ("code", "status"),
    [
        (GitErrorCode.url_invalid, 422),
        (GitErrorCode.credential_invalid, 422),
        (GitErrorCode.credential_in_use, 409),
        (GitErrorCode.secrets_unavailable, 409),
        (GitErrorCode.sync_busy, 409),
        (GitErrorCode.no_conflicts, 404),
        (GitErrorCode.auth_failed, 502),
        (GitErrorCode.host_key_unknown, 502),
    ],
)
def test__git_error_status__follows_the_contract(code: GitErrorCode, status: int) -> None:
    assert GIT_ERROR_STATUS[code] == status


def test__git_error_status__never_uses_401_or_403() -> None:
    assert not {401, 403} & set(GIT_ERROR_STATUS.values())


def test__git_error_body__carries_detail_code_and_context() -> None:
    exc = GitSyncError(GitErrorCode.sync_busy, "Идёт синхронизация", operation_id="op1")

    assert git_error_body(exc) == {"detail": "Идёт синхронизация", "code": "sync_busy", "operation_id": "op1"}
