from __future__ import annotations

import json
from pathlib import Path

import pytest
from hse_doc_studio.core.git_sync.entities import SyncBlockReason, SyncHealth, SyncRelation, SyncUiState
from hse_doc_studio.core.git_sync.status import StatusInputs, derive_relation, derive_ui_state

_STATUS_FIXTURES = Path(__file__).resolve().parents[6] / "contracts" / "git-sync" / "fixtures" / "GitStatus"


def _inputs(**changes: object) -> StatusInputs:
    base: dict[str, object] = {"connected": True, "relation": SyncRelation.in_sync}
    return StatusInputs(**{**base, **changes})  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("relation", "expected"),
    [
        (SyncRelation.none, SyncUiState.unfetched),
        (SyncRelation.unfetched, SyncUiState.unfetched),
        (SyncRelation.remote_empty, SyncUiState.ahead),
        (SyncRelation.ahead, SyncUiState.ahead),
        (SyncRelation.behind, SyncUiState.behind),
        (SyncRelation.diverged, SyncUiState.diverged),
        (SyncRelation.in_sync, SyncUiState.up_to_date),
    ],
)
def test__derive_ui_state__healthy_remote__follows_the_branch_relation(
    relation: SyncRelation, expected: SyncUiState
) -> None:
    assert derive_ui_state(_inputs(relation=relation)) is expected


def test__derive_ui_state__no_remote__wins_over_everything() -> None:
    inputs = _inputs(
        connected=False,
        has_operation=True,
        has_pending=True,
        blocked=SyncBlockReason.read_only,
        health=SyncHealth.offline,
    )

    assert derive_ui_state(inputs) is SyncUiState.no_remote


def test__derive_ui_state__operation__wins_over_pending_block_and_health() -> None:
    inputs = _inputs(has_operation=True, has_pending=True, blocked=SyncBlockReason.off_branch, health=SyncHealth.error)

    assert derive_ui_state(inputs) is SyncUiState.syncing


def test__derive_ui_state__pending__wins_over_block_and_health() -> None:
    inputs = _inputs(has_pending=True, blocked=SyncBlockReason.off_branch, health=SyncHealth.error)

    assert derive_ui_state(inputs) is SyncUiState.conflicts


@pytest.mark.parametrize("reason", list(SyncBlockReason))
def test__derive_ui_state__block__wins_over_health_and_relation(reason: SyncBlockReason) -> None:
    inputs = _inputs(blocked=reason, health=SyncHealth.unauthenticated, relation=SyncRelation.diverged)

    assert derive_ui_state(inputs) is SyncUiState.blocked


@pytest.mark.parametrize(
    ("health", "expected"),
    [
        (SyncHealth.unauthenticated, SyncUiState.auth_failed),
        (SyncHealth.offline, SyncUiState.offline),
        (SyncHealth.error, SyncUiState.error),
        (SyncHealth.host_key_changed, SyncUiState.error),
        (SyncHealth.remote_missing, SyncUiState.error),
        (SyncHealth.branch_missing, SyncUiState.error),
    ],
)
def test__derive_ui_state__unhealthy_remote__wins_over_branch_relation(
    health: SyncHealth, expected: SyncUiState
) -> None:
    assert derive_ui_state(_inputs(health=health, relation=SyncRelation.behind)) is expected


def test__derive_ui_state__every_ui_state_is_reachable() -> None:
    reached = {
        derive_ui_state(_inputs(connected=False)),
        derive_ui_state(_inputs(has_operation=True)),
        derive_ui_state(_inputs(has_pending=True)),
        derive_ui_state(_inputs(blocked=SyncBlockReason.read_only)),
        derive_ui_state(_inputs(health=SyncHealth.unauthenticated)),
        derive_ui_state(_inputs(health=SyncHealth.offline)),
        derive_ui_state(_inputs(health=SyncHealth.error)),
        *(derive_ui_state(_inputs(relation=relation)) for relation in SyncRelation),
    }

    assert reached == set(SyncUiState)


@pytest.mark.parametrize("path", sorted(_STATUS_FIXTURES.glob("*.json")), ids=lambda p: p.stem)
def test__derive_ui_state__contract_fixture__reproduces_its_ui_state(path: Path) -> None:
    status = json.loads(path.read_text(encoding="utf-8"))
    blocked = status["blocked"]

    result = derive_ui_state(
        StatusInputs(
            connected=status["connected"],
            relation=SyncRelation(status["relation"]),
            health=SyncHealth(status["health"]),
            has_operation=status["operation"] is not None,
            has_pending=status["pending"] is not None,
            blocked=SyncBlockReason(blocked["reason"]) if blocked else None,
        )
    )

    assert result.value == status["ui_state"]


@pytest.mark.parametrize(
    ("ahead", "behind", "expected"),
    [
        (0, 0, SyncRelation.in_sync),
        (3, 0, SyncRelation.ahead),
        (0, 2, SyncRelation.behind),
        (3, 2, SyncRelation.diverged),
    ],
)
def test__derive_relation__fetched_remote__counts_decide(ahead: int, behind: int, expected: SyncRelation) -> None:
    assert derive_relation(ahead=ahead, behind=behind, tracking_exists=True) is expected


def test__derive_relation__never_fetched__is_unfetched_whatever_the_counts() -> None:
    assert derive_relation(ahead=5, behind=0, tracking_exists=False) is SyncRelation.unfetched


def test__derive_relation__empty_remote__is_remote_empty() -> None:
    assert derive_relation(ahead=4, behind=0, tracking_exists=False, remote_empty=True) is SyncRelation.remote_empty
