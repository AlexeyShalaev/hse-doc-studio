from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from hse_doc_studio.infra.office import jwt as office_jwt
from hse_doc_studio.use_cases.office_editor.get_editor_config import callback_signature
from httpx import AsyncClient
from pytest_mock import MockerFixture

from tests.factories import project_api_payload

# Shared HMAC/JWT secret this test pre-seeds at the manager's persisted secret
# path (see `_write_office_editor_secret`) so it can build a genuinely valid
# `sig` and DS-token pair, the same way `callback_signature`/`office_jwt.sign`
# are used in production.
_SECRET = "test-office-editor-secret"  # noqa: S105 — test-only shared secret

# "presentation" ships a `pptx` variant (office format, chosen by default —
# see packs/hse-cs-se .../version.yaml + create_project's `_resolve_variant`);
# "thesis" is LaTeX-only (PDF artifact) — no office format to open.
_OFFICE_DOC_ID = "presentation"
_NON_OFFICE_DOC_ID = "thesis"


async def _create_project(client: AsyncClient, folder: Path) -> dict[str, Any]:
    folder.mkdir(exist_ok=True)
    resp = await client.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    return resp.json()


def _write_office_editor_secret(tmp_path: Path, secret: str = _SECRET) -> None:
    """Pre-seed the manager's persisted JWT secret (data_dir/office-editor-jwt.secret).

    `test_app` points `data_dir` at `tmp_path/data` (see tests/fixtures/app.py);
    the manager lazily reads-or-creates this exact file on first access to
    `.jwt_secret`. Writing it up front lets the test compute a real, valid
    signature/token instead of needing to reach the "ready" state first.
    """
    secret_path = tmp_path / "data" / "office-editor-jwt.secret"
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.write_text(secret, encoding="utf-8")


class _FakeDockerProc:
    """Minimal stand-in for `asyncio.subprocess.Process` (returncode + communicate())."""

    def __init__(self, returncode: int, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self, input: bytes | None = None) -> tuple[bytes, bytes]:  # noqa: A002 — mirrors stdlib API
        return self._stdout, self._stderr


def _patch_docker_unavailable(mocker: MockerFixture) -> None:
    """Docker CLI itself can't be invoked -> `OfficeEditorManager` sees Docker as down.

    Faked at the exact seam `_run_docker_raw` calls (see backend-testing.md's
    guidance on faking Docker at the narrowest boundary): this dev host actually
    has `onlyoffice/documentserver:latest` pulled (and a stopped `hse-office-editor`
    container from prior manual use), so hitting the endpoint unmocked would try
    to really start it — slow and out of scope. This keeps the test fast and
    host-independent.
    """
    mocker.patch(
        "asyncio.create_subprocess_exec",
        side_effect=OSError("docker: executable file not found in $PATH"),
    )


def _patch_docker_image_missing(mocker: MockerFixture) -> None:
    """Docker is up but the DS image isn't installed (opt-in not done)."""

    async def _fake_exec(program: str, *args: str, **_kwargs: Any) -> _FakeDockerProc:
        assert program == "docker"
        if args and args[0] == "version":
            return _FakeDockerProc(0, stdout=b"27.0.0")
        if args and args[0] == "image":
            return _FakeDockerProc(1, stderr=b"Error: No such image")
        return _FakeDockerProc(1)

    mocker.patch("asyncio.create_subprocess_exec", side_effect=_fake_exec)


# ── GET /projects/{project_id}/documents/{doc_id}/office-editor ─────────────


async def test__get_config__non_office_document__returns_400(test_app: AsyncClient, tmp_path: Path) -> None:
    # thesis's artifact is a PDF (LaTeX build), not an office format the DS
    # editor can open -> NotOfficeDocumentError, never touches Docker.
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/documents/{_NON_OFFICE_DOC_ID}/office-editor")

    assert resp.status_code == 400, resp.text


async def test__get_config__unknown_project__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.get(f"/api/v1/projects/{uuid4()}/documents/{_OFFICE_DOC_ID}/office-editor")

    assert resp.status_code == 404, resp.text


async def test__get_config__unknown_doc__returns_404(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/documents/no-such-doc/office-editor")

    assert resp.status_code == 404, resp.text


async def test__get_config__docker_unavailable__degrades_to_unavailable(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    _patch_docker_unavailable(mocker)

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/documents/{_OFFICE_DOC_ID}/office-editor")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["state"] == "unavailable"
    assert data["config"] is None
    assert data["detail"]


async def test__get_config__image_not_installed__degrades_to_image_missing(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    _patch_docker_image_missing(mocker)

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/documents/{_OFFICE_DOC_ID}/office-editor")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["state"] == "image_missing"
    assert data["image"] == "onlyoffice/documentserver:latest"
    assert data["settings_section"] == "presentations"
    assert data["config"] is None


# ── POST /office-editor/callback ─────────────────────────────────────────────


async def test__callback__invalid_json_body__returns_400(test_app: AsyncClient) -> None:
    resp = await test_app.post(
        "/api/v1/office-editor/callback",
        params={"project_id": str(uuid4()), "doc_id": _OFFICE_DOC_ID, "sig": "whatever"},
        content=b"not-json{",
        headers={"Content-Type": "application/json"},
    )

    assert resp.status_code == 400, resp.text


async def test__callback__non_dict_body__returns_400(test_app: AsyncClient) -> None:
    resp = await test_app.post(
        "/api/v1/office-editor/callback",
        params={"project_id": str(uuid4()), "doc_id": _OFFICE_DOC_ID, "sig": "whatever"},
        json=[1, 2, 3],
    )

    assert resp.status_code == 400, resp.text


async def test__callback__wrong_signature__returns_403(test_app: AsyncClient, tmp_path: Path) -> None:
    _write_office_editor_secret(tmp_path)

    resp = await test_app.post(
        "/api/v1/office-editor/callback",
        params={"project_id": str(uuid4()), "doc_id": _OFFICE_DOC_ID, "sig": "not-the-real-signature"},
        json={"status": 1},
    )

    assert resp.status_code == 403, resp.text


@pytest.mark.parametrize(
    "body",
    [
        pytest.param({"status": 1}, id="missing_token"),
        pytest.param({"status": 1, "token": "garbage.not.jwt"}, id="invalid_token"),
    ],
)
async def test__callback__bad_token__returns_403(test_app: AsyncClient, tmp_path: Path, body: dict[str, Any]) -> None:
    _write_office_editor_secret(tmp_path)
    project_id = uuid4()
    sig = callback_signature(_SECRET, project_id, _OFFICE_DOC_ID)

    resp = await test_app.post(
        "/api/v1/office-editor/callback",
        params={"project_id": str(project_id), "doc_id": _OFFICE_DOC_ID, "sig": sig},
        json=body,
    )

    assert resp.status_code == 403, resp.text


async def test__callback__valid_auth_editing_status__acknowledged_without_project_lookup(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    # status=1 (EDITING) never looks up the project at all -- proves auth is
    # verified unconditionally while existence is only checked on the save path
    # (status 2/6), i.e. auth precedes (and is independent of) the 404 checks.
    _write_office_editor_secret(tmp_path)
    project_id = uuid4()  # deliberately never created
    sig = callback_signature(_SECRET, project_id, _OFFICE_DOC_ID)
    body: dict[str, Any] = {"status": 1, "key": "some-key"}
    body["token"] = office_jwt.sign(body, _SECRET)

    resp = await test_app.post(
        "/api/v1/office-editor/callback",
        params={"project_id": str(project_id), "doc_id": _OFFICE_DOC_ID, "sig": sig},
        json=body,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"error": 0}


async def test__callback__valid_auth_save_status_unknown_project__returns_404(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    _write_office_editor_secret(tmp_path)
    project_id = uuid4()  # never created -> save path's project lookup 404s
    sig = callback_signature(_SECRET, project_id, _OFFICE_DOC_ID)
    body: dict[str, Any] = {"status": 2, "key": "some-key", "url": "http://ds.invalid/doc.pptx"}
    body["token"] = office_jwt.sign(body, _SECRET)

    resp = await test_app.post(
        "/api/v1/office-editor/callback",
        params={"project_id": str(project_id), "doc_id": _OFFICE_DOC_ID, "sig": sig},
        json=body,
    )

    assert resp.status_code == 404, resp.text


async def test__callback__valid_auth_save_status_unknown_doc__returns_404(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    _write_office_editor_secret(tmp_path)
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]
    doc_id = "no-such-doc"
    sig = callback_signature(_SECRET, project_id, doc_id)
    body: dict[str, Any] = {"status": 2, "key": "some-key", "url": "http://ds.invalid/doc.pptx"}
    body["token"] = office_jwt.sign(body, _SECRET)

    resp = await test_app.post(
        "/api/v1/office-editor/callback",
        params={"project_id": str(project_id), "doc_id": doc_id, "sig": sig},
        json=body,
    )

    assert resp.status_code == 404, resp.text


# ── POST /projects/{project_id}/documents/{doc_id}/office-editor/touch ──────


async def test__touch__valid_project_and_doc__returns_204(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.post(f"/api/v1/projects/{project['id']}/documents/{_OFFICE_DOC_ID}/office-editor/touch")

    assert resp.status_code == 204, resp.text
    assert resp.content == b""


async def test__touch__unknown_project_and_doc__still_returns_204(test_app: AsyncClient) -> None:
    # Router's own comment: one shared container for all projects, path exists
    # only for API symmetry -- project/doc validity is never checked.
    resp = await test_app.post(f"/api/v1/projects/{uuid4()}/documents/no-such-doc/office-editor/touch")

    assert resp.status_code == 204, resp.text
