from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from hse_doc_studio.core.git_sync.entities import (
    LastError,
    LastSync,
    PendingSession,
    SyncHealth,
    SyncOutcome,
    SyncState,
)
from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.git_sync.merge.choices import (
    FieldChoice,
    FieldDecision,
    FieldsResolution,
    FileChoice,
    FileChoiceResolution,
    HunkChoice,
    HunkDecision,
    HunksResolution,
    TextResolution,
)
from hse_doc_studio.infra.git_sync.sync_state import SYNC_STATE_FILE, JsonGitSyncStateRepository

pytestmark = pytest.mark.unit

_AT = datetime(2026, 10, 26, 12, 30, 5, tzinfo=UTC)
_CRED = UUID("11111111-2222-3333-4444-555555555555")


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    (tmp_path / ".hse-studio" / "git").mkdir(parents=True)
    return tmp_path


def _file(folder: Path) -> Path:
    return folder / ".hse-studio" / "git" / SYNC_STATE_FILE


def _full_state() -> SyncState:
    return SyncState(
        local_branch="master",
        remote_branch="main",
        credential_id=_CRED,
        insecure_http=True,
        health=SyncHealth.offline,
        last_fetch_at=_AT,
        last_fetch_ok_at=_AT,
        last_error=LastError(code=GitErrorCode.offline, detail="no route", at=_AT),
        last_sync=LastSync(id="s1", at=_AT, outcome=SyncOutcome.merged, pulled_commits=3, pushed_commits=2),
        pending=PendingSession(
            session_id="p1",
            files_total=4,
            files_open=3,
            ours="a" * 40,
            theirs="b" * 40,
            base="c" * 40,
            fingerprint="f1",
            drafts={
                "main.tex": HunksResolution({"h:3f2a9c01": HunkDecision(HunkChoice.custom, "text\nof the hunk")}),
                ".hse-studio/project.json": FieldsResolution({"/meta/title": FieldDecision(FieldChoice.theirs)}),
                "figures/a.png": FileChoiceResolution(FileChoice.newest),
                "notes.tex": TextResolution("whole file\n"),
            },
            drafts_saved_at=_AT,
        ),
        auto_fetch=False,
        fetch_interval_s=600,
        shared_folder_ack=True,
        remote_empty=True,
        adopted_unrelated=True,
        remote_schema_newer=True,
        remote_required_studio="9.9.0",
    )


def test__get__no_file__returns_none(folder: Path) -> None:
    assert JsonGitSyncStateRepository().get(folder) is None


def test__save_get__round_trips_every_field(folder: Path) -> None:
    repo = JsonGitSyncStateRepository()
    repo.save(folder, _full_state())
    assert repo.get(folder) == _full_state()


def test__save_get__minimal_state_round_trips(folder: Path) -> None:
    repo = JsonGitSyncStateRepository()
    state = SyncState(local_branch="master", remote_branch="main")
    repo.save(folder, state)
    assert repo.get(folder) == state


def test__get__file_without_the_new_flags__reads_them_as_off(folder: Path) -> None:
    repo = JsonGitSyncStateRepository()
    repo.save(folder, SyncState(local_branch="master", remote_branch="main"))
    data = json.loads(_file(folder).read_text(encoding="utf-8"))
    del data["remote_empty"], data["adopted_unrelated"], data["remote_schema_newer"], data["remote_required_studio"]
    _file(folder).write_text(json.dumps(data), encoding="utf-8")

    state = repo.get(folder)

    assert state is not None
    assert (state.remote_empty, state.adopted_unrelated) == (False, False)
    assert (state.remote_schema_newer, state.remote_required_studio) == (False, None)


def test__save__writes_a_versioned_file_with_utc_timestamps(folder: Path) -> None:
    JsonGitSyncStateRepository().save(folder, _full_state())
    raw = json.loads(_file(folder).read_text(encoding="utf-8"))
    assert raw["version"] == 1
    assert raw["last_fetch_at"] == "2026-10-26T12:30:05Z"
    assert raw["credential_id"] == str(_CRED)
    assert raw["pending"] == {
        "session_id": "p1",
        "files_total": 4,
        "files_open": 3,
        "ours": "a" * 40,
        "theirs": "b" * 40,
        "base": "c" * 40,
        "fingerprint": "f1",
        "drafts": {
            ".hse-studio/project.json": {"kind": "fields", "fields": {"/meta/title": {"choice": "theirs"}}},
            "figures/a.png": {"kind": "file", "choice": "newest"},
            "main.tex": {"kind": "hunks", "hunks": {"h:3f2a9c01": {"choice": "custom", "text": "text\nof the hunk"}}},
            "notes.tex": {"kind": "text", "content": "whole file\n"},
        },
        "drafts_saved_at": "2026-10-26T12:30:05Z",
    }
    assert not list(_file(folder).parent.glob("*.tmp"))


def test__save__keeps_unknown_keys_at_top_level_and_nested(folder: Path) -> None:
    repo = JsonGitSyncStateRepository()
    repo.save(folder, _full_state())
    raw = json.loads(_file(folder).read_text(encoding="utf-8"))
    raw["future_flag"] = {"a": 1}
    raw["pending"]["future_note"] = {"vkr.tex": "mine"}
    raw["last_sync"]["note"] = "x"
    _file(folder).write_text(json.dumps(raw), encoding="utf-8")

    repo.save(folder, _full_state())

    after = json.loads(_file(folder).read_text(encoding="utf-8"))
    assert after["future_flag"] == {"a": 1}
    assert after["pending"]["future_note"] == {"vkr.tex": "mine"}
    assert after["last_sync"]["note"] == "x"


def test__save__new_pending_session__drops_the_drafts_of_the_old_one(folder: Path) -> None:
    repo = JsonGitSyncStateRepository()
    repo.save(folder, _full_state())
    raw = json.loads(_file(folder).read_text(encoding="utf-8"))
    raw["pending"]["future_note"] = {"a": 1}
    _file(folder).write_text(json.dumps(raw), encoding="utf-8")

    repo.save(folder, replace(_full_state(), pending=PendingSession("p2", 1, 1)))

    assert "future_note" not in json.loads(_file(folder).read_text(encoding="utf-8"))["pending"]


def test__save__pending_cleared__removes_the_key_content(folder: Path) -> None:
    repo = JsonGitSyncStateRepository()
    repo.save(folder, _full_state())
    repo.save(folder, replace(_full_state(), pending=None))
    assert json.loads(_file(folder).read_text(encoding="utf-8"))["pending"] is None
    assert repo.get(folder).pending is None  # type: ignore[union-attr]


def test__save__newer_version_is_not_downgraded(folder: Path) -> None:
    repo = JsonGitSyncStateRepository()
    repo.save(folder, _full_state())
    raw = json.loads(_file(folder).read_text(encoding="utf-8"))
    raw["version"] = 7
    _file(folder).write_text(json.dumps(raw), encoding="utf-8")
    repo.save(folder, _full_state())
    assert json.loads(_file(folder).read_text(encoding="utf-8"))["version"] == 7


@pytest.mark.parametrize(
    "content", ["", "not json", "[1, 2]", "{}", '{"local_branch": "m"}', '{"local_branch": "", "remote_branch": "m"}']
)
def test__get__unusable_file__returns_none(folder: Path, content: str) -> None:
    _file(folder).write_text(content, encoding="utf-8")
    assert JsonGitSyncStateRepository().get(folder) is None


def test__get__unknown_values_from_a_newer_studio__fall_back_instead_of_failing(folder: Path) -> None:
    raw = {
        "local_branch": "master",
        "remote_branch": "main",
        "health": "quantum_entangled",
        "credential_id": "not-a-uuid",
        "last_error": {"code": "brand_new_code", "detail": "d", "at": "2026-10-26T12:30:05"},
        "last_sync": {"id": "s", "at": "2026-10-26T12:30:05Z", "outcome": "teleported"},
        "last_fetch_at": "garbage",
    }
    _file(folder).write_text(json.dumps(raw), encoding="utf-8")

    state = JsonGitSyncStateRepository().get(folder)

    assert state is not None
    assert state.health is SyncHealth.ok
    assert state.credential_id is None
    assert state.last_fetch_at is None
    assert state.last_error is not None
    assert state.last_error.code is GitErrorCode.git_error
    assert state.last_error.at == datetime(2026, 10, 26, 12, 30, 5, tzinfo=UTC)
    assert state.last_sync is not None
    assert state.last_sync.outcome is SyncOutcome.up_to_date


def test__save__over_a_corrupt_file__replaces_it(folder: Path) -> None:
    _file(folder).write_text("{{{", encoding="utf-8")
    repo = JsonGitSyncStateRepository()
    repo.save(folder, _full_state())
    assert repo.get(folder) == _full_state()


def test__clear__removes_the_file_and_tolerates_absence(folder: Path) -> None:
    repo = JsonGitSyncStateRepository()
    repo.save(folder, _full_state())
    repo.clear(folder)
    assert not _file(folder).exists()
    repo.clear(folder)
    assert repo.get(folder) is None


def test__save__without_store_folder__creates_it(tmp_path: Path) -> None:
    JsonGitSyncStateRepository().save(tmp_path, _full_state())
    assert JsonGitSyncStateRepository().get(tmp_path) == _full_state()


def test__save__leaves_no_temp_files(folder: Path) -> None:
    repo = JsonGitSyncStateRepository()
    repo.save(folder, _full_state())
    repo.save(folder, _full_state())
    assert [p.name for p in _file(folder).parent.iterdir()] == [SYNC_STATE_FILE]


def test__get__pending_written_by_older_studio_without_commits__reads_with_empty_commits(folder: Path) -> None:
    repo = JsonGitSyncStateRepository()
    repo.save(folder, _full_state())
    raw = json.loads(_file(folder).read_text(encoding="utf-8"))
    raw["pending"] = {"session_id": "old", "files_total": 2, "files_open": 1}
    _file(folder).write_text(json.dumps(raw), encoding="utf-8")

    pending = repo.get(folder).pending  # type: ignore[union-attr]

    assert pending == PendingSession("old", 2, 1)


def test__get__damaged_draft__is_dropped_and_the_rest_is_kept(folder: Path) -> None:
    repo = JsonGitSyncStateRepository()
    repo.save(folder, _full_state())
    raw = json.loads(_file(folder).read_text(encoding="utf-8"))
    raw["pending"]["drafts"]["figures/a.png"] = {"kind": "file", "choice": "sideways"}
    raw["pending"]["drafts"]["strange"] = "mine"
    _file(folder).write_text(json.dumps(raw), encoding="utf-8")

    pending = repo.get(folder).pending  # type: ignore[union-attr]

    assert pending is not None
    assert set(pending.drafts) == {"main.tex", ".hse-studio/project.json", "notes.tex"}
