from __future__ import annotations

import gzip
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import AsyncClient

from tests.factories import project_api_payload

# A doc from the real hse-cs-se/vkr pack, whose source lands at «thesis/thesis.tex»
# for a solo project (see GET /documents in a freshly created project).
_DOC_ID = "thesis"
_SOURCE_FILE = "thesis/thesis.tex"

# Minimal but well-formed SyncTeX v1 body — one page, a vbox high on the page
# (line 10) and an hbox near the top (line 12). Adapted from
# tests/unit/infra/synctex/test_parser.py's SAMPLE.
_SAMPLE_SYNCTEX = """SyncTeX Version:1
Input:1:./main.tex
Output:pdf
Magnification:1000
Unit:1
X Offset:0
Y Offset:0
Content:
{1
[1,10:4736286,42152922:30785863,41497600,0
(1,12:4736286,4263256:30785863,500000,100000
h1,12:4736286,4263256:30785863,500000,100000
)
]
}1
Postamble:
"""


async def _create_project(client: AsyncClient, folder: Path) -> dict:
    folder.mkdir(exist_ok=True)
    resp = await client.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _synctex_path(proj_folder: Path, doc_id: str = _DOC_ID, source_file: str = _SOURCE_FILE) -> Path:
    # Mirrors the compile executor's convention (see docker_compile_executor.py
    # and query_synctex.py's SyncTexUC docstring): «<src_parent>/.build/<doc_id>/<stem>.synctex.gz».
    src_parent, _, filename = source_file.rpartition("/")
    stem = filename.rsplit(".", 1)[0]
    return proj_folder / src_parent / ".build" / doc_id / f"{stem}.synctex.gz"


def _write_synctex(proj_folder: Path) -> None:
    path = _synctex_path(proj_folder)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(gzip.compress(_SAMPLE_SYNCTEX.encode()))


@pytest_asyncio.fixture
async def project(test_app: AsyncClient, tmp_path: Path) -> dict:
    return await _create_project(test_app, tmp_path / "proj")


async def test__synctex_forward__existing_data_and_known_line__returns_boxes_with_page_and_position(
    test_app: AsyncClient, project: dict
) -> None:
    _write_synctex(Path(project["folder"]))

    resp = await test_app.get(
        f"/api/v1/projects/{project['id']}/documents/{_DOC_ID}/synctex/forward",
        params={"file": "main.tex", "line": 12},
    )

    assert resp.status_code == 200, resp.text
    boxes = resp.json()["boxes"]
    assert boxes
    assert boxes[0]["page"] == 1


async def test__synctex_inverse__existing_data_and_known_position__returns_source_location(
    test_app: AsyncClient, project: dict
) -> None:
    _write_synctex(Path(project["folder"]))

    resp = await test_app.get(
        f"/api/v1/projects/{project['id']}/documents/{_DOC_ID}/synctex/inverse",
        params={"page": 1, "x": 72.0, "y": 64.0},
    )

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["file"] == "main.tex"
    assert data["line"] == 12


async def test__synctex_forward__file_not_matching_any_input__returns_empty_boxes(
    test_app: AsyncClient, project: dict
) -> None:
    _write_synctex(Path(project["folder"]))

    resp = await test_app.get(
        f"/api/v1/projects/{project['id']}/documents/{_DOC_ID}/synctex/forward",
        params={"file": "no-such-file.tex", "line": 1},
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["boxes"] == []


async def test__synctex_inverse__page_with_no_recorded_boxes__returns_404(test_app: AsyncClient, project: dict) -> None:
    _write_synctex(Path(project["folder"]))

    resp = await test_app.get(
        f"/api/v1/projects/{project['id']}/documents/{_DOC_ID}/synctex/inverse",
        params={"page": 2, "x": 0.0, "y": 0.0},
    )

    assert resp.status_code == 404


@pytest.mark.parametrize(
    ("endpoint", "params"),
    [
        pytest.param("forward", {"file": "main.tex", "line": 1}, id="forward"),
        pytest.param("inverse", {"page": 1, "x": 0.0, "y": 0.0}, id="inverse"),
    ],
)
async def test__synctex__no_synctex_file_on_disk__returns_404(
    test_app: AsyncClient, project: dict, endpoint: str, params: dict[str, object]
) -> None:
    # Deliberately do NOT write a .synctex.gz file for the doc.
    resp = await test_app.get(
        f"/api/v1/projects/{project['id']}/documents/{_DOC_ID}/synctex/{endpoint}",
        params=params,
    )

    assert resp.status_code == 404


@pytest.mark.parametrize(
    ("endpoint", "params"),
    [
        pytest.param("forward", {"file": "main.tex", "line": 1}, id="forward"),
        pytest.param("inverse", {"page": 1, "x": 0.0, "y": 0.0}, id="inverse"),
    ],
)
async def test__synctex__nonexistent_doc__returns_404(
    test_app: AsyncClient, project: dict, endpoint: str, params: dict[str, object]
) -> None:
    resp = await test_app.get(
        f"/api/v1/projects/{project['id']}/documents/no-such-doc/synctex/{endpoint}",
        params=params,
    )

    assert resp.status_code == 404


@pytest.mark.parametrize(
    ("endpoint", "params"),
    [
        pytest.param("forward", {"file": "main.tex", "line": 1}, id="forward"),
        pytest.param("inverse", {"page": 1, "x": 0.0, "y": 0.0}, id="inverse"),
    ],
)
async def test__synctex__nonexistent_project__returns_404(
    test_app: AsyncClient, endpoint: str, params: dict[str, object]
) -> None:
    fake_id = "00000000-0000-0000-0000-000000000000"

    resp = await test_app.get(
        f"/api/v1/projects/{fake_id}/documents/{_DOC_ID}/synctex/{endpoint}",
        params=params,
    )

    assert resp.status_code == 404
