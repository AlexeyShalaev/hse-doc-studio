"""Места подписей и метки даты на PDF предпросмотра (template-studio.md, 5.6, срез T9) в локальной Студии.

Настоящие роутер, DI и запись файлов; для рамок по сборке подменён только бинарник docker (как в `test_preview.py`).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager, DockerStatus, ImageInfo
from pytest_mock import MockerFixture

from tests.fixtures.fake_docker import FakeDocker, install_fake_docker

from .conftest import API, DRAFT, DRAFT_DIR, PACK_FILES, RELEASED, RELEASED_DIR, Stand, write_pack
from .test_preview import _settled, _start

_VERSION = """\
id: "{version}"
status: {status}
summary: {{ ru: "Версия", en: "Version" }}
langs: [ru]
documents:
  - id: report
    name: {{ ru: "Отчёт", en: "Report" }}
    source_file: report/report.tex
    output_file: report/report.pdf
  - id: memo
    name: {{ ru: "Записка", en: "Memo" }}
    source_file: memo/memo.tex
    output_file: memo/memo.pdf

signatures:
  slots:
    # Руководитель подписывает отчёт.
    - id: supervisor
      label:             {{ ru: Руководитель, en: Supervisor }}
      applies_to:        [report]
      default_placement: {{ page: 1, x_mm: 110, y_mm: 130, width_mm: 40 }}
    - id: author
      label:             {{ ru: Автор, en: Author }}
      applies_to:        [report, memo]
      default_placement: {{ page: 1, x_mm: 30, y_mm: 230, width_mm: 30 }}
"""

FILES: Mapping[str, str] = {
    **{k: v for k, v in PACK_FILES.items() if not k.endswith("version.yaml") and "/files/" not in k},
    f"{RELEASED_DIR}/version.yaml": _VERSION.format(version=RELEASED, status="stable"),
    f"{RELEASED_DIR}/files/report/report.tex": "\\documentclass{article}\n",
    f"{RELEASED_DIR}/files/memo/memo.tex": "\\documentclass{article}\n",
    f"{DRAFT_DIR}/version.yaml": _VERSION.format(version=DRAFT, status="beta"),
    f"{DRAFT_DIR}/files/report/report.tex": "\\documentclass{article}\n% draft\n",
    f"{DRAFT_DIR}/files/memo/memo.tex": "\\documentclass{article}\n",
}


@pytest.fixture
def fake_docker(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, mocker: MockerFixture) -> FakeDocker:
    mocker.patch.object(
        DockerImageManager, "docker_status", return_value=DockerStatus(available=True, version="fake", detail=None)
    )
    mocker.patch.object(
        DockerImageManager,
        "inspect",
        return_value=ImageInfo(image="texlive/texlive:latest", id="sha256:fake", size_bytes=1, created="2026-01-01"),
    )
    return install_fake_docker(monkeypatch, tmp_path)


async def _workspace(stand: Stand) -> tuple[str, Path]:
    await stand.enable()
    root = write_pack(stand.root / "packs", FILES)
    ws = await stand.folder_workspace(root.parent, packs_path=root.name)
    return str(ws["id"]), root


def _url(ws: str, version: str = DRAFT) -> str:
    return f"{API}/workspaces/{ws}/versions/demo/report/{version}/signatures"


def _supervisor(body: dict[str, Any]) -> dict[str, Any]:
    return next(slot for slot in body["slots"] if slot["id"] == "supervisor")


def _op(**fields: Any) -> dict[str, Any]:
    return {"ops": [fields]}


async def test__get__catalog_of_the_version_with_etag(stand: Stand) -> None:
    ws, _ = await _workspace(stand)

    resp = await stand.client.get(_url(ws))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["path"] == f"{DRAFT_DIR}/version.yaml"
    assert body["etag"] == resp.headers["ETag"]
    assert body["read_only"] is None
    assert body["documents"] == ["report", "memo"]
    assert body["build"] is None
    supervisor = _supervisor(body)
    assert supervisor["default_place"] == {"source": "mm", "page": 1, "x_mm": 110.0, "y_mm": 130.0, "width_mm": 40.0}
    assert supervisor["places"] == {}
    assert supervisor["document"] is None


async def test__patch__place_written_with_if_match_and_comments_kept(stand: Stand) -> None:
    ws, root = await _workspace(stand)
    etag = (await stand.client.get(_url(ws))).json()["etag"]
    body = _op(
        op="set_place", slot="supervisor", doc="report", box={"page": 1, "x_mm": 80.4, "y_mm": 139, "width_mm": 40}
    )

    resp = await stand.client.patch(_url(ws), json=body, headers={"If-Match": etag})

    assert resp.status_code == 200, resp.text
    assert resp.json()["etag"] != etag
    assert _supervisor(resp.json())["places"] == {
        "report": {"source": "mm", "page": 1, "x_mm": 80.0, "y_mm": 139.0, "width_mm": 40.0}
    }
    text = (root / DRAFT_DIR / "version.yaml").read_text(encoding="utf-8")
    assert "    # Руководитель подписывает отчёт.\n" in text
    assert "      placements:\n        report: { page: 1, x_mm: 80, y_mm: 139, width_mm: 40 }\n" in text

    stale = await stand.client.patch(_url(ws), json=body, headers={"If-Match": etag})

    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_file"


async def test__patch__dates_and_default_place(stand: Stand) -> None:
    ws, root = await _workspace(stand)
    mark = {"page": 1, "x_mm": 100, "y_mm": 150, "width_mm": 28, "height_mm": 6, "format": "date_numeric"}

    resp = await stand.client.patch(
        _url(ws),
        json={
            "ops": [
                {"op": "add_date", "slot": "supervisor", "doc": "report", "mark": mark},
                {"op": "set_place", "slot": "supervisor", "box": {"page": 1, "x_mm": 100, "y_mm": 120, "width_mm": 45}},
            ]
        },
    )

    assert resp.status_code == 200, resp.text
    supervisor = _supervisor(resp.json())
    assert supervisor["dates"]["report"][0]["index"] == 0
    assert supervisor["dates"]["report"][0]["entry"]["format"] == "date_numeric"
    assert supervisor["default_place"]["x_mm"] == 100.0
    raw = yaml.safe_load((root / DRAFT_DIR / "version.yaml").read_text(encoding="utf-8"))
    assert raw["signatures"]["slots"][0]["default_placement"] == {"page": 1, "x_mm": 100, "y_mm": 120, "width_mm": 45}


async def test__patch__released_version_is_read_only(stand: Stand) -> None:
    ws, root = await _workspace(stand)
    before = (root / RELEASED_DIR / "version.yaml").read_text(encoding="utf-8")

    got = await stand.client.get(_url(ws, RELEASED))
    resp = await stand.client.patch(
        _url(ws, RELEASED),
        json=_op(
            op="set_place", slot="supervisor", doc="report", box={"page": 1, "x_mm": 10, "y_mm": 10, "width_mm": 40}
        ),
    )

    assert got.json()["read_only"] == "version_released"
    assert resp.status_code == 409
    assert resp.json()["code"] == "version_released"
    assert (root / RELEASED_DIR / "version.yaml").read_text(encoding="utf-8") == before


async def test__patch__slot_not_for_the_document_is_place_invalid(stand: Stand) -> None:
    ws, root = await _workspace(stand)
    before = (root / DRAFT_DIR / "version.yaml").read_text(encoding="utf-8")

    resp = await stand.client.patch(
        _url(ws),
        json=_op(
            op="set_place", slot="supervisor", doc="memo", box={"page": 1, "x_mm": 10, "y_mm": 10, "width_mm": 40}
        ),
    )

    assert resp.status_code == 400
    assert resp.json()["code"] == "place_invalid"
    assert "does not apply" in resp.json()["reason"]
    assert (root / DRAFT_DIR / "version.yaml").read_text(encoding="utf-8") == before


async def test__patch__op_without_its_fields_is_rejected(stand: Stand) -> None:
    ws, _ = await _workspace(stand)

    resp = await stand.client.patch(_url(ws), json=_op(op="set_place", slot="supervisor", doc="report"))

    assert resp.status_code == 422


async def test__get__frames_of_the_build_document(stand: Stand, fake_docker: FakeDocker) -> None:
    ws, _ = await _workspace(stand)
    _, builds = await _start(stand, ws, {"documents": ["report"], "example": "auto:normal"})
    build = await _settled(stand, ws, builds[0]["id"])
    assert build["status"] == "succeeded", build

    resp = await stand.client.get(_url(ws), params={"build_id": build["id"]})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["build"] == {
        "id": build["id"],
        "document": "report",
        "anchors_known": False,
        "sign_anchors": [],
        "date_anchors": [],
    }
    frame = _supervisor(body)["document"]
    assert frame["kind"] == "default"
    assert frame["box"] == {"page": 1, "x_mm": 110.0, "y_mm": 130.0, "width_mm": 40.0}

    other = await stand.client.get(_url(ws, RELEASED), params={"build_id": build["id"]})

    assert other.status_code == 400
    assert other.json()["code"] == "preview_invalid"


async def test__get__unknown_build_is_not_found(stand: Stand) -> None:
    ws, _ = await _workspace(stand)

    resp = await stand.client.get(_url(ws), params={"build_id": "6f1c1c8e-1b7a-4d51-9a43-0a5b2f3c4d10"})

    assert resp.status_code == 404
    assert resp.json()["code"] == "preview_not_found"
