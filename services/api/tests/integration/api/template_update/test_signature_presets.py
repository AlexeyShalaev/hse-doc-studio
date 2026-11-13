"""Обновление шаблона и места подписей из шаблона (docs/design/signing-route.md, 15.9 и 15.10): сквозь HTTP, с git.

Пак: 2026.1 знает только общее место научрука, patch 2026.1.1 с теми же файлами ставит место научрука на отчёте и
метки даты. Файловый план такого обновления пуст, а пункт `signature_presets` нет.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from hse_doc_studio.core.value_objects import FromPack, SignaturePlacement, SignaturesState
from hse_doc_studio.infra.persistence.signature import JsonSignatureRepository
from httpx import ASGITransport, AsyncClient

from tests.fixtures.app import create_test_app, create_test_container
from tests.fixtures.template_pack import AUTHOR_PLACE, SUPERVISOR_V1, SUPERVISOR_V2, V1, V2, build_presets_pack
from tests.integration.api.template_update.conftest import create_project

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git binary not available")

_REPO = JsonSignatureRepository()


@pytest_asyncio.fixture
async def presets_app(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    packs_dir = tmp_path / "packs"
    build_presets_pack(packs_dir)
    container = create_test_container(data_dir, packs_dir=packs_dir)
    app = create_test_app(container)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    await container.close()


@pytest_asyncio.fixture
async def project(presets_app: AsyncClient, tmp_path: Path) -> dict[str, Any]:
    return await create_project(presets_app, tmp_path / "proj")


def _base(project: dict[str, Any]) -> str:
    return f"/api/v1/projects/{project['id']}"


def _folder(project: dict[str, Any]) -> Path:
    return Path(project["folder"])


def _place(place: dict[str, Any], *, enabled: bool = False, **kwargs: Any) -> SignaturePlacement:
    return SignaturePlacement(enabled=enabled, **{**place, **kwargs})


def _seed_state(project: dict[str, Any], **placements: SignaturePlacement) -> None:
    _REPO.save_state(_folder(project), SignaturesState(slots={}, placements={"report": dict(placements)}))


def _placements(project: dict[str, Any]) -> dict[str, Any]:
    data = json.loads((_folder(project) / ".hse-studio" / "signatures.json").read_text(encoding="utf-8"))
    return dict(data["placements"]["report"])


async def _plan(client: AsyncClient, project: dict[str, Any]) -> dict[str, Any]:
    resp = await client.post(f"{_base(project)}/template-update/plan", json={"to_version": V2})
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _apply(client: AsyncClient, project: dict[str, Any], plan: dict[str, Any]) -> dict[str, Any]:
    resp = await client.post(
        f"{_base(project)}/template-update/apply",
        json={"to_version": plan["to_version"], "fingerprint": plan["fingerprint"], "resolutions": {}},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test__plan__only_signature_places_change(presets_app: AsyncClient, project: dict[str, Any]) -> None:
    # Затравка научрука (выключенное место из пака 2026.1) и ручное место автора, которое пак не менял.
    _seed_state(project, supervisor=_place(SUPERVISOR_V1), author=_place(AUTHOR_PLACE, enabled=True, x_mm=150.0))

    plan = await _plan(presets_app, project)

    assert plan["update_class"] == "patch"
    assert plan["files"] == []
    assert plan["counts"] == {}
    assert plan["signature_presets"] == {"updated": [{"doc_id": "report", "slot_id": "supervisor"}], "kept": []}


async def test__apply__moves_the_seed_to_the_new_preset_and_revert_returns_it(
    presets_app: AsyncClient, project: dict[str, Any]
) -> None:
    author = _place(AUTHOR_PLACE, enabled=True, x_mm=150.0)
    _seed_state(project, supervisor=_place(SUPERVISOR_V1), author=author)
    before = _placements(project)

    await _apply(presets_app, project, await _plan(presets_app, project))

    after = _placements(project)
    supervisor = after["supervisor"]
    assert {k: supervisor[k] for k in SUPERVISOR_V2} == SUPERVISOR_V2
    assert supervisor["enabled"] is False
    assert [(d["id"], d["format"], d["x_mm"]) for d in supervisor["dates"]] == [
        ("d1", "day", 81.0),
        ("d2", "month_word", 90.0),
    ]
    assert supervisor["from_pack"]["version"] == V2
    assert after["author"] == before["author"]
    detail = (await presets_app.get(_base(project))).json()
    assert detail["lock"]["version"] == V2
    # Место из шаблона: ответ состояния подписей видит его как `pack`.
    signatures = (await presets_app.get(f"{_base(project)}/signatures")).json()
    assert signatures["placements"]["report"]["supervisor"]["origin"] == "pack"
    assert signatures["placements"]["report"]["author"]["origin"] == "manual"

    resp = await presets_app.post(f"{_base(project)}/template-update/revert", json={})

    assert resp.status_code == 200, resp.text
    assert _placements(project) == before
    assert (await presets_app.get(_base(project))).json()["lock"]["version"] == V1


async def test__manual_place__kept_and_untouched(presets_app: AsyncClient, project: dict[str, Any]) -> None:
    manual = _place(SUPERVISOR_V1, enabled=True, x_mm=95.0)
    _seed_state(project, supervisor=manual)
    before = _placements(project)

    plan = await _plan(presets_app, project)
    assert plan["signature_presets"] == {
        "updated": [],
        "kept": [{"doc_id": "report", "slot_id": "supervisor", "reason": "manual"}],
    }
    await _apply(presets_app, project, plan)

    assert _placements(project) == before


async def test__pair_the_pack_did_not_move__not_in_the_plan(presets_app: AsyncClient, project: dict[str, Any]) -> None:
    # Затравка автора: место автора пак между версиями не менял, переводить нечего.
    _seed_state(project, author=_place(AUTHOR_PLACE))

    plan = await _plan(presets_app, project)

    assert plan["signature_presets"] == {"updated": [], "kept": []}


async def test__apply__refuses_when_places_changed_after_the_preview(
    presets_app: AsyncClient, project: dict[str, Any]
) -> None:
    _seed_state(project, supervisor=_place(SUPERVISOR_V1))
    plan = await _plan(presets_app, project)
    # Автор передвинул затравку после предпросмотра: место стало ручным, план уже не тот.
    _seed_state(project, supervisor=_place(SUPERVISOR_V1, x_mm=100.0))

    resp = await presets_app.post(
        f"{_base(project)}/template-update/apply",
        json={"to_version": V2, "fingerprint": plan["fingerprint"], "resolutions": {}},
    )

    assert resp.status_code == 409, resp.text
    assert _placements(project)["supervisor"]["x_mm"] == 100.0


async def test__revert__keeps_a_place_moved_after_the_update(presets_app: AsyncClient, project: dict[str, Any]) -> None:
    _seed_state(project, supervisor=_place(SUPERVISOR_V1))
    await _apply(presets_app, project, await _plan(presets_app, project))
    moved = _place(SUPERVISOR_V2, enabled=True, x_mm=70.0)
    _REPO.save_state(_folder(project), SignaturesState(slots={}, placements={"report": {"supervisor": moved}}))

    resp = await presets_app.post(f"{_base(project)}/template-update/revert", json={})

    assert resp.status_code == 200, resp.text
    supervisor = _placements(project)["supervisor"]
    assert supervisor["x_mm"] == 70.0
    assert supervisor["enabled"] is True


async def test__revert__restores_the_place_but_keeps_enabled(presets_app: AsyncClient, project: dict[str, Any]) -> None:
    _seed_state(project, supervisor=_place(SUPERVISOR_V1))
    await _apply(presets_app, project, await _plan(presets_app, project))
    state = _REPO.get_state(_folder(project))
    placement = state.placements["report"]["supervisor"]
    assert isinstance(placement.from_pack, FromPack)
    # Включение места не меняет отпечаток: место остаётся из шаблона, отмена возвращает его, не выключая.
    on = replace(placement, enabled=True)
    _REPO.save_state(_folder(project), SignaturesState(slots={}, placements={"report": {"supervisor": on}}))

    resp = await presets_app.post(f"{_base(project)}/template-update/revert", json={})

    assert resp.status_code == 200, resp.text
    supervisor = _placements(project)["supervisor"]
    assert {k: supervisor[k] for k in SUPERVISOR_V1} == SUPERVISOR_V1
    assert supervisor["dates"] == []
    assert supervisor["from_pack"] is None
    assert supervisor["enabled"] is True
