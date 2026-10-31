"""Локальная Студия выгружает PDF на настоящий сервер: вход кодом устройства, загрузка, повтор, отказы."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from hse_doc_studio.core.git_sync.entities import StoreRemoteConfig, SyncState
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.use_cases.git_sync.publish_pdf import PdfPublishStatus, PublishPdfUC
from hse_doc_studio.use_cases.git_sync.studio_servers import LoginState

from tests.factories import make_project
from tests.integration.api.git_remote.conftest import Live, Person
from tests.integration.api.git_remote.test_studio_login import _service

pytestmark = [pytest.mark.pg, pytest.mark.timeout(240)]

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


class _Fixed:
    """Порты локальной Студии, которым настоящий сервер не нужен: проект, документ, remote, состояние."""

    def __init__(self, folder: Path, server_project: str, doc_id: str, credential_id: Any) -> None:
        self.project = make_project(folder)
        self.doc_id = doc_id
        self.config = StoreRemoteConfig(url=f"http://127.0.0.1/git/{server_project}.git", credential_id=credential_id)
        self.state: SyncState | None = SyncState(local_branch="master", remote_branch="master")

    async def execute(self, _inp: Any) -> Any:  # GetProjectUC и GetDocumentUC
        return SimpleNamespace(project=self.project, output_file="coursework/main.pdf")

    def read(self, _project: Any) -> StoreRemoteConfig:
        return self.config

    def get(self, _folder: Path) -> SyncState | None:
        return self.state

    def save(self, _folder: Path, state: SyncState) -> None:
        self.state = state

    def rev_parse(self, _folder: Path, _ref: str) -> str:
        return "b" * 40

    def for_folder(self, _folder: Path) -> Any:
        class _Lock:
            async def __aenter__(self) -> None:
                return None

            async def __aexit__(self, *_exc: object) -> None:
                return None

        return _Lock()


async def _signed_in(live: Live, person: Person, service: Any, scopes: list[str]) -> Any:
    login = await service.start_login(live.base, "Студия на MacBook")
    with live.client() as client:
        response = client.post(
            f"/api/v1/account/device/{login.user_code}",
            json={"decision": "approve", "scopes": scopes},
            headers=person.session,
            cookies=person.cookies,
        )
    assert response.status_code == 200, response.text
    for _ in range(60):
        current = service.get_login(login.login_id)
        if current.state != LoginState.pending:
            return current
        await asyncio.sleep(0.5)
    raise AssertionError("вход не завершился")


def _build(live: Live, service: Any, credentials: Any, fixed: _Fixed) -> PublishPdfUC:
    return PublishPdfUC(
        project_repo_uc=fixed,  # type: ignore[arg-type]
        document_uc=fixed,  # type: ignore[arg-type]
        store_remotes=fixed,  # type: ignore[arg-type]
        state_repo=fixed,  # type: ignore[arg-type]
        credentials=credentials,
        servers=service,
        reader=fixed,  # type: ignore[arg-type]
        locks=fixed,  # type: ignore[arg-type]
        policy=GitSyncPolicy(),
    )


def test__publish_pdf__real_server__uploaded_once_then_unchanged_and_visible_on_site(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    doc = str(live.call("GET", f"/api/v1/projects/{project}/documents", anna).json()[0]["id"])
    service, credentials = _service(live.tmp)
    folder = live.tmp / "local-project"
    (folder / "coursework").mkdir(parents=True)
    (folder / "coursework" / "main.pdf").write_bytes(PDF)

    async def scenario() -> None:
        current = await _signed_in(live, anna, service, ["git:read", "git:write"])
        fixed = _Fixed(folder, project, doc, current.credential_id)
        uc = _build(live, service, credentials, fixed)

        first = await uc.execute(fixed.project.id, doc, pages=3)
        second = await uc.execute(fixed.project.id, doc)

        assert (first.status, second.status) == (PdfPublishStatus.uploaded, PdfPublishStatus.unchanged)
        assert fixed.state is not None
        assert fixed.state.last_pdf_upload is not None
        assert fixed.state.last_pdf_upload.ok is True

    asyncio.run(scenario())
    (item,) = live.call("GET", f"/api/v1/projects/{project}/artifacts", anna).json()["items"]
    assert item["doc_id"] == doc
    assert item["pages"] == 3
    assert item["source_commit"] == "b" * 40
    assert item["client_name"] == "Студия на MacBook"
    assert live.call("GET", item["file_url"], anna).content == PDF


def test__publish_pdf__token_without_write_scope__failed_with_scope_hint(live: Live) -> None:
    anna = live.person("anna")
    project = live.create_project(anna)
    doc = str(live.call("GET", f"/api/v1/projects/{project}/documents", anna).json()[0]["id"])
    service, credentials = _service(live.tmp)
    folder = live.tmp / "local-project"
    (folder / "coursework").mkdir(parents=True)
    (folder / "coursework" / "main.pdf").write_bytes(PDF)

    async def scenario() -> None:
        current = await _signed_in(live, anna, service, ["git:read"])
        fixed = _Fixed(folder, project, doc, current.credential_id)

        result = await _build(live, service, credentials, fixed).execute(fixed.project.id, doc)

        assert (result.status, result.code) == (PdfPublishStatus.failed, "pdf_scope_missing")
        assert fixed.state is not None
        assert fixed.state.last_pdf_upload is not None
        assert fixed.state.last_pdf_upload.ok is False

    asyncio.run(scenario())
    assert live.call("GET", f"/api/v1/projects/{project}/artifacts", anna).json()["items"] == []


def test__publish_pdf__reader_role__failed_forbidden(live: Live) -> None:
    anna, vera = live.person("anna"), live.person("vera")
    project = live.create_project(anna)
    live.add_member(project, vera, "reader")
    doc = str(live.call("GET", f"/api/v1/projects/{project}/documents", anna).json()[0]["id"])
    service, credentials = _service(live.tmp)
    folder = live.tmp / "local-project"
    (folder / "coursework").mkdir(parents=True)
    (folder / "coursework" / "main.pdf").write_bytes(PDF)

    async def scenario() -> None:
        current = await _signed_in(live, vera, service, ["git:read", "git:write"])
        fixed = _Fixed(folder, project, doc, current.credential_id)

        result = await _build(live, service, credentials, fixed).execute(fixed.project.id, doc)

        assert (result.status, result.code) == (PdfPublishStatus.failed, "pdf_forbidden")

    asyncio.run(scenario())
