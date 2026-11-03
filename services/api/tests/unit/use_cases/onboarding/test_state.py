from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from hse_doc_studio.core.onboarding.entities import OnboardingPatch, OnboardingState, OnboardingStatus
from hse_doc_studio.infra.persistence.onboarding import JsonOnboardingRepository, LocalExistingUserProbe
from hse_doc_studio.use_cases.onboarding.state import GetOnboardingUC, ResetOnboardingUC, UpdateOnboardingUC

_NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


class _Index:
    def __init__(self, folders: list[Path]) -> None:
        self._folders = folders

    def list_known(self) -> list[Path]:
        return list(self._folders)

    def register(self, folder: Path) -> None:
        self._folders.append(folder)

    def unregister(self, folder: Path) -> None:
        self._folders.remove(folder)


class _Probe:
    def __init__(self, existing: bool) -> None:
        self.existing = existing

    async def is_existing_user(self) -> bool:
        return self.existing


@pytest.mark.parametrize(("existing", "expected"), [(False, "pending"), (True, "suggested")])
async def test__get__no_record__status_depends_on_existing_user(tmp_path: Path, existing: bool, expected: str) -> None:
    uc = GetOnboardingUC(JsonOnboardingRepository(tmp_path), _Probe(existing))

    state = await uc.execute()

    assert state.status.value == expected
    assert not (tmp_path / "onboarding.json").exists()


async def test__update__persists_to_json_file(tmp_path: Path) -> None:
    repo = JsonOnboardingRepository(tmp_path)
    update = UpdateOnboardingUC(repo, _Probe(False), clock=lambda: _NOW)

    await update.execute(
        OnboardingPatch(status=OnboardingStatus.in_progress, step="demo.edit", answers={"role": "student"})
    )

    stored = await JsonOnboardingRepository(tmp_path).get()
    assert stored == OnboardingState(
        status=OnboardingStatus.in_progress,
        step="demo.edit",
        answers={"role": "student"},
        started_at=_NOW,
        updated_at=_NOW,
    )


async def test__reset__after_completion__pending_again(tmp_path: Path) -> None:
    repo = JsonOnboardingRepository(tmp_path)
    await UpdateOnboardingUC(repo, _Probe(True), clock=lambda: _NOW).execute(
        OnboardingPatch(status=OnboardingStatus.completed)
    )

    state = await ResetOnboardingUC(repo, _Probe(True), clock=lambda: _NOW).execute()

    assert state.status is OnboardingStatus.pending
    assert (await GetOnboardingUC(repo, _Probe(True)).execute()).status is OnboardingStatus.pending


async def test__json_repo__corrupt_file__treated_as_missing(tmp_path: Path) -> None:
    (tmp_path / "onboarding.json").write_text("{not json", encoding="utf-8")

    assert await JsonOnboardingRepository(tmp_path).get() is None


@pytest.mark.parametrize(("folders", "expected"), [([], False), ([Path("/p")], True)])
async def test__local_probe__existing_projects_mean_existing_user(folders: list[Path], expected: bool) -> None:
    assert await LocalExistingUserProbe(_Index(folders)).is_existing_user() is expected
