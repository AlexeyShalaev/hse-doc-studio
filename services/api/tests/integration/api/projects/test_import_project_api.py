"""POST /projects/import: загрузка zip, тело ответа, отказы с кодом и статусом, предел загрузки, локальный режим."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import pytest
import pytest_asyncio
from dishka import Provider, Scope, make_async_container, provide
from dishka.integrations.fastapi import FastapiProvider, setup_dishka
from fastapi import FastAPI
from hse_doc_studio.api.config import settings
from hse_doc_studio.api.guards import install_exception_handlers
from hse_doc_studio.api.routers.v1 import project_import
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.core.projects.importer import (
    ImportLimits,
    ImportReport,
    ImportWarning,
    ImportWarningCode,
    ProjectImportCode,
    ProjectImportError,
)
from hse_doc_studio.use_cases.projects.import_project import ImportProjectInput, ImportProjectUC
from httpx import ASGITransport, AsyncClient

LIMITS = ImportLimits(max_unpacked_bytes=1024, max_files=10)


@dataclass
class Spy:
    seen: list[bytes] = field(default_factory=list)
    outcome: ImportReport | ProjectImportError | None = None


class _FakeImport:
    def __init__(self, spy: Spy) -> None:
        self._spy = spy

    async def execute(self, inp: ImportProjectInput) -> ImportReport:
        self._spy.seen.append(Path(inp.archive).read_bytes())
        outcome = self._spy.outcome
        if isinstance(outcome, ProjectImportError):
            raise outcome
        assert outcome is not None
        return outcome


class _Providers(Provider):
    scope = Scope.APP

    def __init__(self, spy: Spy) -> None:
        super().__init__()
        self._spy = spy

    @provide
    def uc(self) -> ImportProjectUC:
        return _FakeImport(self._spy)  # type: ignore[return-value]

    @provide
    def limits(self) -> ImportLimits:
        return LIMITS


@pytest_asyncio.fixture
async def client(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[tuple[AsyncClient, Spy]]:
    monkeypatch.setattr(settings, "mode", StudioMode.server)
    spy = Spy()
    app = FastAPI()
    app.include_router(project_import.router, prefix="/api/v1")
    install_exception_handlers(app)
    container = make_async_container(_Providers(spy), FastapiProvider())
    setup_dishka(container, app)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
        yield http, spy
    await container.close()


def report(**changes: object) -> ImportReport:
    base = ImportReport(project_id=uuid4(), name="Курсовая", id_regenerated=False, files=3, bytes=120, chats=1)
    for key, value in changes.items():
        setattr(base, key, value)
    return base


async def upload(http: AsyncClient, data: bytes = b"PK-bytes") -> object:
    return await http.post("/api/v1/projects/import", files={"file": ("p.zip", data, "application/zip")})


async def test__import__returns_report_and_passes_file_to_use_case(client: tuple[AsyncClient, Spy]) -> None:
    http, spy = client
    ready = report(
        id_regenerated=True,
        warnings=[
            ImportWarning(ImportWarningCode.remote_needs_access),
            ImportWarning(ImportWarningCode.junk_skipped, "2"),
        ],
    )
    spy.outcome = ready

    response = await upload(http)

    assert response.status_code == 201  # type: ignore[attr-defined]
    assert response.json() == {  # type: ignore[attr-defined]
        "project_id": str(ready.project_id),
        "name": "Курсовая",
        "id_regenerated": True,
        "files": 3,
        "bytes": 120,
        "chats": 1,
        "warnings": [
            {"code": "remote_needs_access", "detail": ""},
            {"code": "junk_skipped", "detail": "2"},
        ],
    }
    assert spy.seen == [b"PK-bytes"]


@pytest.mark.parametrize(
    ("code", "status"),
    [
        (ProjectImportCode.archive_unsafe, 422),
        (ProjectImportCode.archive_invalid, 422),
        (ProjectImportCode.no_project, 422),
        (ProjectImportCode.project_newer, 422),
        (ProjectImportCode.too_large, 413),
        (ProjectImportCode.unavailable, 503),
    ],
)
async def test__import__refusal__status_and_code(
    client: tuple[AsyncClient, Spy], code: ProjectImportCode, status: int
) -> None:
    http, spy = client
    spy.outcome = ProjectImportError(code, "причина")

    response = await upload(http)

    assert response.status_code == status  # type: ignore[attr-defined]
    assert response.json() == {"detail": "причина", "code": f"import_{code.value}"}  # type: ignore[attr-defined]


async def test__import__upload_over_limit__413_and_use_case_not_called(client: tuple[AsyncClient, Spy]) -> None:
    http, spy = client

    response = await upload(http, b"0" * (LIMITS.max_unpacked_bytes + 1))

    assert response.status_code == 413  # type: ignore[attr-defined]
    assert response.json()["code"] == "import_too_large"  # type: ignore[attr-defined]
    assert spy.seen == []


async def test__import__missing_file__422(client: tuple[AsyncClient, Spy]) -> None:
    http, _ = client

    response = await http.post("/api/v1/projects/import")

    assert response.status_code == 422


async def test__import__local_mode__404(client: tuple[AsyncClient, Spy], monkeypatch: pytest.MonkeyPatch) -> None:
    http, spy = client
    monkeypatch.setattr(settings, "mode", StudioMode.local)

    response = await upload(http)

    assert response.status_code == 404  # type: ignore[attr-defined]
    assert spy.seen == []
