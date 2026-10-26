from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.git_sync.entities import (
    CredentialStatus,
    GitCredential,
    GitCredentialKind,
    LastError,
    SyncHealth,
    SyncState,
)
from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.git_sync.fetch_schedule import (
    JITTER_SHARE,
    MAX_BACKOFF_S,
    FetchBook,
    credential_replaced,
    fetch_jitter,
    halts_auto_fetch,
    health_for,
    next_attempt_at,
    retry_delay_s,
)

_NOW = datetime(2026, 10, 27, 12, 0, tzinfo=UTC)


def _state(**changes: object) -> SyncState:
    return SyncState(local_branch="master", remote_branch="main", **changes)  # type: ignore[arg-type]


def _credential(status: CredentialStatus) -> GitCredential:
    return GitCredential(
        id=uuid4(),
        kind=GitCredentialKind.pat,
        label="token",
        host="github.com",
        username=None,
        status=status,
        created_at=_NOW,
    )


def test__fetch_jitter__stays_within_ten_percent_and_is_stable_per_key() -> None:
    values = {fetch_jitter(f"/projects/{n}") for n in range(200)}

    assert all(1 - JITTER_SHARE <= value <= 1 + JITTER_SHARE for value in values)
    assert len(values) > 100
    assert fetch_jitter("/projects/a") == fetch_jitter("/projects/a")


def test__retry_delay__without_failures__is_the_interval_with_jitter() -> None:
    delay = retry_delay_s(300, 0, "p")

    assert delay == pytest.approx(300 * fetch_jitter("p"))


def test__retry_delay__doubles_per_failure() -> None:
    jitter = fetch_jitter("p")

    assert [retry_delay_s(300, n, "p") / jitter for n in range(4)] == pytest.approx([300, 600, 1200, 2400])


def test__retry_delay__is_capped_at_one_hour() -> None:
    jitter = fetch_jitter("p")

    assert retry_delay_s(300, 6, "p") == pytest.approx(MAX_BACKOFF_S * jitter)
    assert retry_delay_s(300, 10_000, "p") == pytest.approx(MAX_BACKOFF_S * jitter)


def test__retry_delay__long_interval__is_never_shortened_by_the_cap() -> None:
    day = 24 * 3600

    assert retry_delay_s(day, 5, "p") == pytest.approx(day * fetch_jitter("p"))


def test__next_attempt_at__never_fetched__is_due_at_once() -> None:
    assert next_attempt_at(None, 300, 0, "p") is None


def test__next_attempt_at__adds_the_delay_to_the_last_attempt() -> None:
    due = next_attempt_at(_NOW, 300, 2, "p")

    assert due == _NOW + timedelta(seconds=retry_delay_s(300, 2, "p"))


@pytest.mark.parametrize(
    ("code", "health"),
    [
        (GitErrorCode.auth_failed, SyncHealth.unauthenticated),
        (GitErrorCode.sso_required, SyncHealth.unauthenticated),
        (GitErrorCode.credentials_missing, SyncHealth.unauthenticated),
        (GitErrorCode.forbidden_write, SyncHealth.unauthenticated),
        (GitErrorCode.host_key_changed, SyncHealth.host_key_changed),
        (GitErrorCode.offline, SyncHealth.offline),
        (GitErrorCode.timeout, SyncHealth.offline),
        (GitErrorCode.not_found_or_no_access, SyncHealth.remote_missing),
        (GitErrorCode.branch_missing, SyncHealth.branch_missing),
        (GitErrorCode.tls_error, SyncHealth.error),
        (GitErrorCode.git_error, SyncHealth.error),
    ],
)
def test__health_for__maps_codes_to_health(code: GitErrorCode, health: SyncHealth) -> None:
    assert health_for(code) is health


@pytest.mark.parametrize("health", [SyncHealth.unauthenticated, SyncHealth.host_key_changed])
def test__halts_auto_fetch__access_problems__stop_it(health: SyncHealth) -> None:
    assert halts_auto_fetch(_state(health=health))


def test__halts_auto_fetch__unknown_host_key__stops_it_although_health_is_a_plain_error() -> None:
    error = LastError(GitErrorCode.host_key_unknown, "", _NOW)

    assert halts_auto_fetch(_state(health=SyncHealth.error, last_error=error))


@pytest.mark.parametrize("health", [SyncHealth.ok, SyncHealth.offline, SyncHealth.error, SyncHealth.remote_missing])
def test__halts_auto_fetch__network_problems__keep_retrying(health: SyncHealth) -> None:
    error = LastError(GitErrorCode.offline, "", _NOW) if health is not SyncHealth.ok else None

    assert not halts_auto_fetch(_state(health=health, last_error=error))


def test__credential_replaced__after_a_token_change__allows_one_more_try() -> None:
    state = _state(health=SyncHealth.unauthenticated, last_error=LastError(GitErrorCode.auth_failed, "", _NOW))

    assert credential_replaced(state, _credential(CredentialStatus.unverified))
    assert credential_replaced(state, _credential(CredentialStatus.ok))


def test__credential_replaced__same_failing_token_or_no_credential__keeps_it_stopped() -> None:
    state = _state(health=SyncHealth.unauthenticated, last_error=LastError(GitErrorCode.auth_failed, "", _NOW))

    assert not credential_replaced(state, _credential(CredentialStatus.auth_failed))
    assert not credential_replaced(state, _credential(CredentialStatus.unreadable))
    assert not credential_replaced(state, None)


def test__credential_replaced__host_key_problem__is_not_cured_by_a_token() -> None:
    state = _state(health=SyncHealth.host_key_changed, last_error=LastError(GitErrorCode.host_key_changed, "", _NOW))

    assert not credential_replaced(state, _credential(CredentialStatus.unverified))


def test__fetch_book__counts_failures_in_a_row_and_resets_on_success(tmp_path: Path) -> None:
    book = FetchBook()

    book.failed(tmp_path)
    book.failed(tmp_path)
    assert book.failures(tmp_path) == 2
    book.succeeded(tmp_path)
    assert book.failures(tmp_path) == 0


def test__fetch_book__one_lock_per_folder(tmp_path: Path) -> None:
    book = FetchBook()

    assert book.lock(tmp_path) is book.lock(tmp_path)
    assert book.lock(tmp_path) is not book.lock(tmp_path / "other")


async def test__fetch_book__forget__drops_failures_and_the_lock(tmp_path: Path) -> None:
    book = FetchBook()
    first = book.lock(tmp_path)
    book.failed(tmp_path)

    book.forget(tmp_path)

    assert book.failures(tmp_path) == 0
    assert book.lock(tmp_path) is not first
    assert isinstance(first, asyncio.Lock)
