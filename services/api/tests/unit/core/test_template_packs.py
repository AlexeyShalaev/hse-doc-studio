"""Подключённый каталог шаблонов отстаёт от Студии: как это видно и что говорит проект."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import ProjectAccessMode, ProjectAccessReason
from hse_doc_studio.core.project_access import StalePacks, access_message, evaluate_project_access
from hse_doc_studio.core.template_packs import PacksKind, PacksSource, TemplateKey, classify_packs

from tests.factories import make_project

_OLD = TemplateKey("hse-cs-sse", "coursework", "2026.1.1")
_NEW = TemplateKey("hse-cs-sse", "coursework", "2026.1.2")
_FUTURE = TemplateKey("hse-cs-sse", "coursework", "2027.0")


def _external(available: frozenset[TemplateKey] = frozenset({_OLD})) -> PacksSource:
    return PacksSource(
        path="/app/packs",
        kind=PacksKind.external,
        mounted=True,
        builtin=frozenset({_OLD, _NEW}),
        builtin_studio="0.16.0",
        available=available,
    )


@pytest.mark.unit
def test__classify__no_manifest__is_source_run() -> None:
    assert classify_packs(packs_dir="/repo/packs", builtin_dir=None, mounted=True) is PacksKind.source


@pytest.mark.unit
def test__classify__mounted_over_builtin_dir__is_external() -> None:
    assert classify_packs(packs_dir="/app/packs", builtin_dir="/app/packs", mounted=True) is PacksKind.external


@pytest.mark.unit
def test__classify__other_path__is_external() -> None:
    assert classify_packs(packs_dir="/data/packs", builtin_dir="/app/packs", mounted=False) is PacksKind.external


@pytest.mark.unit
def test__classify__builtin_dir_untouched__is_builtin() -> None:
    assert classify_packs(packs_dir="/app/packs/", builtin_dir="/app/packs", mounted=False) is PacksKind.builtin


@pytest.mark.unit
def test__lags_for__version_built_in_but_missing_from_external_dir() -> None:
    assert _external().lags_for(_NEW)


@pytest.mark.unit
def test__lags_for__version_not_built_in__does_not_lag() -> None:
    # Такой версии нет и в самой Студии: она действительно вышла позже.
    assert not _external().lags_for(_FUTURE)


@pytest.mark.unit
def test__lags_for__builtin_dir__never_lags() -> None:
    source = replace(_external(), kind=PacksKind.builtin, mounted=False)

    assert not source.lags_for(_NEW)
    assert source.missing_builtin == ()


@pytest.mark.unit
def test__missing_builtin__lists_what_the_external_dir_lacks() -> None:
    assert _external().missing_builtin == (_NEW,)


def _locked_on(version: str, min_studio: str | None = None) -> Project:
    project = make_project()
    lock = replace(project.lock, pack_id="hse-cs-sse", template_id="coursework", version=version, min_studio=min_studio)
    return replace(project, lock=lock)


@pytest.mark.unit
def test__access__stale_packs__read_only_without_newer_studio_advice() -> None:
    project = _locked_on(_NEW.version, min_studio="0.16.0")
    stale = StalePacks(path="/app/packs", studio_version="0.16.0")

    access = evaluate_project_access(
        project,
        template_available=False,
        update_in_progress=False,
        stale_packs=stale,
    )

    assert access.mode is ProjectAccessMode.read_only
    assert access.reasons == (ProjectAccessReason.template_missing,)
    assert access.required_studio is None
    assert access.stale_packs == stale


@pytest.mark.unit
def test__access_message__stale_packs__names_the_folder_and_studio_version() -> None:
    project = _locked_on(_NEW.version)
    access = evaluate_project_access(
        project,
        template_available=False,
        update_in_progress=False,
        stale_packs=StalePacks(path="/app/packs", studio_version="0.16.0"),
    )

    message = access_message(access, _NEW.version)

    assert message == (
        "Версии шаблона 2026.1.2 нет в каталоге шаблонов /app/packs: он подключён извне и отстаёт "
        "от Студии v0.16.0. Обновите каталог или уберите подключение."
    )
    assert "—" not in message


@pytest.mark.unit
def test__access_message__version_missing_everywhere__still_asks_for_a_newer_studio() -> None:
    project = _locked_on(_FUTURE.version, min_studio="0.20.0")
    access = evaluate_project_access(
        project,
        template_available=False,
        update_in_progress=False,
    )

    assert access.stale_packs is None
    assert access.required_studio == "0.20.0"
    assert "более новой версией Студии (нужна 0.20.0)" in access_message(access, _FUTURE.version)


@pytest.mark.unit
def test__access__template_available__ignores_stale_packs() -> None:
    access = evaluate_project_access(
        make_project(),
        template_available=True,
        update_in_progress=False,
        stale_packs=StalePacks(path="/app/packs", studio_version="0.16.0"),
    )

    assert access.mode is ProjectAccessMode.full
    assert access.stale_packs is None
