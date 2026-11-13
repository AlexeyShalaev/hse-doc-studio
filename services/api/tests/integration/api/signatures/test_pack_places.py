"""Места подписей из пака по документам и их происхождение в API (docs/design/signing-route.md, 15.3, 15.4, 15.11).

Синтетический пак с двумя версиями шаблона: в `2026.1` у научрука одно общее место, в patch `2026.1.1` своё место и
метки даты на «Описании проекта» и другое общее место. Проект на `2026.1.1`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest_asyncio
from hse_doc_studio.core.enums import TemplateUpdateClass
from hse_doc_studio.core.signatures.pack_places import stamp_from_pack
from hse_doc_studio.core.value_objects import SignaturePlacement
from hse_doc_studio.infra.persistence.signature import JsonSignatureRepository
from hse_doc_studio.infra.template.releases import freeze
from httpx import ASGITransport, AsyncClient

from tests.fixtures.app import create_test_app, create_test_container

_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

_VERSION_YAML = """\
id: "{version}"
released_at: 2026-09-01
status: stable
summary: {{ru: Версия {version}, en: Version {version}}}
engine: {{default: xelatex, allowed: [xelatex], passes: 1, flags: ""}}
latex_packages: []
supported_kinds: [research, project]
supported_staffing: [solo]
langs: [ru]
documents: [proposal, report]
meta_fields: {{}}
signatures:
  slots:
    - id: supervisor
      label: {{ru: Научный руководитель, en: Supervisor}}
      applies_to: [proposal, report]
      default_placement: {default}
{extra}
pack_submission: {{profiles: []}}
"""

_PATCH_EXTRA = """\
      placements:
        proposal: { page: 1, x_mm: 80, y_mm: 139, width_mm: 40 }
      default_dates:
        proposal:
          - { page: 1, x_mm: 81, y_mm: 156, width_mm: 7, height_mm: 5, format: day }
          - { page: 1, x_mm: 90, y_mm: 156, width_mm: 24, height_mm: 5, format: month_word }
"""

_V1_PLACE = {"page": 1, "x_mm": 60.0, "y_mm": 230.0, "width_mm": 50.0}
_GENERAL = {"page": 1, "x_mm": 110.0, "y_mm": 130.0, "width_mm": 40.0}
_PROPOSAL = {"page": 1, "x_mm": 80.0, "y_mm": 139.0, "width_mm": 40.0}


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def _flow(place: dict[str, float]) -> str:
    return "{ " + ", ".join(f"{key}: {value:g}" for key, value in place.items()) + " }"


def _build_pack(packs_dir: Path) -> None:
    pack_dir = packs_dir / "preset-pack"
    _write(
        pack_dir / "pack.yaml",
        "id: preset-pack\nname: {ru: Пак, en: Pack}\ndescription: {ru: Тест, en: Test}\n"
        'maintainer: {name: Test, email: test@test.local, url: ""}\nlicense: MIT\ncreated_at: 2026-01-01\n',
    )
    template_dir = pack_dir / "templates" / "kp"
    _write(
        template_dir / "template.yaml",
        "id: kp\nname: {ru: КП, en: CP}\nshort_name: {ru: КП, en: CP}\ndescription: {ru: Тест, en: Test}\n"
        'icon: ""\naccent_hue: 200\ndefault_version: "2026.1.1"\n',
    )
    for version, default, extra in (("2026.1", _V1_PLACE, ""), ("2026.1.1", _GENERAL, _PATCH_EXTRA)):
        version_dir = template_dir / "versions" / version
        _write(version_dir / "version.yaml", _VERSION_YAML.format(version=version, default=_flow(default), extra=extra))
        (version_dir / "checks").mkdir(parents=True, exist_ok=True)
        for doc in ("proposal", "report"):
            _write(
                version_dir / "files" / doc / "doc.yaml",
                f"name: {{ru: {doc}, en: {doc}}}\ncode: {{ru: X, en: X}}\nsource_file: {doc}/{doc}.tex\n"
                f"output_file: {doc}/{doc}.pdf\noutput_name: {{ru: {doc}.pdf, en: {doc}.pdf}}\nrequired: true\n",
            )
            _write(version_dir / "files" / doc / f"{doc}.tex", "\\documentclass{article}\n")
    freeze(template_dir, "2026.1", TemplateUpdateClass.major)
    freeze(template_dir, "2026.1.1", TemplateUpdateClass.patch)


@pytest_asyncio.fixture
async def preset_app(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    packs_dir = tmp_path / "packs"
    _build_pack(packs_dir)
    container = create_test_container(data_dir, packs_dir=packs_dir)
    app = create_test_app(container)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    await container.close()


async def _project(client: AsyncClient, folder: Path) -> dict[str, Any]:
    folder.mkdir(parents=True, exist_ok=True)
    resp = await client.post(
        "/api/v1/projects",
        json={
            "name": "КП",
            "folder": str(folder),
            "pack_id": "preset-pack",
            "template_id": "kp",
            "version": "2026.1.1",
            "engine": "xelatex",
            "kind": "research",
            "staffing": "solo",
            "lang": "ru",
            "authors": [{"name": "Иван Иванов", "group": "МСПИН261", "email": None}],
            "supervisor": None,
            "co_supervisor": None,
            "meta": {},
        },
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _place(body: dict[str, Any]) -> dict[str, float]:
    return {key: body[key] for key in ("page", "x_mm", "y_mm", "width_mm")}


def _put_placement(folder: Path, doc_id: str, placement: SignaturePlacement) -> None:
    repository = JsonSignatureRepository()
    state = repository.get_state(folder)
    placements = {**state.placements, doc_id: {**state.placements.get(doc_id, {}), "supervisor": placement}}
    repository.save_state(folder, replace(state, placements=placements))


def _stored_from_pack(folder: Path, doc_id: str) -> Any:
    raw = json.loads((folder / ".hse-studio" / "signatures.json").read_text(encoding="utf-8"))
    return raw["placements"][doc_id]["supervisor"]["from_pack"]


async def test__get_signatures__runtime_slot_carries_the_pack_place_and_marks_of_each_document(
    preset_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _project(preset_app, tmp_path / "proj")

    data = (await preset_app.get(f"/api/v1/projects/{project['id']}/signatures")).json()

    (slot,) = (s for s in data["runtime_slots"] if s["id"] == "supervisor")
    assert slot["default_placement"] == _GENERAL
    assert slot["default_placements"] == {"proposal": _PROPOSAL, "report": _GENERAL}
    assert slot["default_dates"] == {
        "proposal": [
            {"page": 1, "x_mm": 81.0, "y_mm": 156.0, "width_mm": 7.0, "height_mm": 5.0, "format": "day",
             "align": "center"},
            {"page": 1, "x_mm": 90.0, "y_mm": 156.0, "width_mm": 24.0, "height_mm": 5.0, "format": "month_word",
             "align": "center"},
        ]
    }  # fmt: skip


async def test__upload_png__seeds_each_document_at_its_pack_place__origin_seed(
    preset_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _project(preset_app, tmp_path / "proj")

    resp = await preset_app.post(
        f"/api/v1/projects/{project['id']}/signatures/slots/supervisor/png",
        files={"file": ("s.png", _PNG, "image/png")},
    )
    assert resp.status_code == 200, resp.text

    placements = (await preset_app.get(f"/api/v1/projects/{project['id']}/signatures")).json()["placements"]
    assert _place(placements["proposal"]["supervisor"]) == _PROPOSAL
    assert _place(placements["report"]["supervisor"]) == _GENERAL
    for doc_id in ("proposal", "report"):
        assert placements[doc_id]["supervisor"]["enabled"] is False
        assert placements[doc_id]["supervisor"]["dates"] == []
        assert (placements[doc_id]["supervisor"]["origin"], placements[doc_id]["supervisor"]["preset_available"]) == (
            "seed",
            True,
        )
    assert _stored_from_pack(Path(project["folder"]), "proposal") is None


async def test__seed_of_an_earlier_version__still_a_seed_after_a_patch(preset_app: AsyncClient, tmp_path: Path) -> None:
    project = await _project(preset_app, tmp_path / "proj")
    _put_placement(Path(project["folder"]), "report", SignaturePlacement(enabled=False, **_V1_PLACE))  # type: ignore[arg-type]

    placements = (await preset_app.get(f"/api/v1/projects/{project['id']}/signatures")).json()["placements"]

    assert placements["report"]["supervisor"]["origin"] == "seed"


async def test__patch_placement__new_place_starts_at_the_document_pack_place(
    preset_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _project(preset_app, tmp_path / "proj")

    resp = await preset_app.patch(
        f"/api/v1/projects/{project['id']}/signatures/placements/proposal/supervisor", json={"enabled": True}
    )

    assert resp.status_code == 200, resp.text
    assert _place(resp.json()) == _PROPOSAL
    assert resp.json()["origin"] == "manual"


async def test__place_from_the_pack__pack_until_a_person_moves_it_noop_patch_keeps_the_mark(
    preset_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _project(preset_app, tmp_path / "proj")
    folder = Path(project["folder"])
    _put_placement(
        folder,
        "proposal",
        stamp_from_pack(SignaturePlacement(enabled=True, **_PROPOSAL), "2026.1.1"),  # type: ignore[arg-type]
    )
    url = f"/api/v1/projects/{project['id']}/signatures/placements/proposal/supervisor"

    state = (await preset_app.get(f"/api/v1/projects/{project['id']}/signatures")).json()
    assert state["placements"]["proposal"]["supervisor"]["origin"] == "pack"

    same = await preset_app.patch(url, json={"x_mm": 80.0})
    assert same.json()["origin"] == "pack"
    assert _stored_from_pack(folder, "proposal")["version"] == "2026.1.1"

    moved = await preset_app.patch(url, json={"x_mm": 85.0})
    assert moved.status_code == 200, moved.text
    assert moved.json()["origin"] == "manual"
    assert _stored_from_pack(folder, "proposal") is None


async def test__put_dates__on_a_place_from_the_pack__makes_it_manual(preset_app: AsyncClient, tmp_path: Path) -> None:
    project = await _project(preset_app, tmp_path / "proj")
    folder = Path(project["folder"])
    _put_placement(
        folder,
        "proposal",
        stamp_from_pack(SignaturePlacement(enabled=True, **_PROPOSAL), "2026.1.1"),  # type: ignore[arg-type]
    )
    mark = {"id": None, "page": 1, "x_mm": 81, "y_mm": 156, "width_mm": 7, "height_mm": 5, "format": "day"}

    resp = await preset_app.put(
        f"/api/v1/projects/{project['id']}/signatures/placements/proposal/supervisor/dates", json={"dates": [mark]}
    )

    assert resp.status_code == 200, resp.text
    assert (resp.json()["origin"], resp.json()["preset_available"]) == ("manual", True)
    assert _stored_from_pack(folder, "proposal") is None
