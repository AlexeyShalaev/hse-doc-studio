from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.catalog import DocumentDefinition, DocumentVariant
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.jobs.entities import JobSpec
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.office import OfficeConvertPayload, OfficeConvertReason
from hse_doc_studio.core.jobs.protocols import IJobObserver
from hse_doc_studio.core.value_objects import CustomFileOverride
from hse_doc_studio.infra.docker.siblings import SiblingNetwork
from hse_doc_studio.infra.office.editor_manager import OfficeEditorManager
from hse_doc_studio.infra.office.jwt import sign
from hse_doc_studio.use_cases.office_editor.get_editor_config import callback_signature
from hse_doc_studio.use_cases.office_editor.handle_callback import (
    OfficeEditorCallbackInput,
    OfficeEditorCallbackUC,
)
from hse_doc_studio.use_cases.office_editor.preview_observer import PreviewRefreshObserver

from tests.factories import make_document, make_document_definition, make_project, make_template_version


def _pres_definition() -> DocumentDefinition:
    pptx_variant = DocumentVariant(
        id="pptx",
        label={"ru": "PowerPoint"},
        source_file="pres/pptx/presentation.pptx",
        output_file="pres/pptx/presentation.pptx",
        output_name={"ru": "Презентация.pptx"},
        engine=None,
    )
    return make_document_definition("pres", required=False, variants=(pptx_variant,))


def _make_manager(tmp_path: Path) -> OfficeEditorManager:
    # Реальный менеджер без docker-вызовов: нужны jwt_secret (файл в tmp) и
    # набор активных сессий; контейнерные методы в этих тестах не трогаются.
    return OfficeEditorManager(
        image="onlyoffice/documentserver:latest",
        container_name="test-office-editor",
        container_port=80,
        health_path="/healthcheck",
        health_timeout_s=1.0,
        startup_timeout_s=1.0,
        idle_timeout_s=60.0,
        secret_path=tmp_path / "office-editor-jwt.secret",
        fonts_dir=None,
        fonts_host_dir=None,
        client=MagicMock(),
        siblings=SiblingNetwork.disabled(),
    )


class FakeJobDispatcher:
    """Запоминает фоновые задачи; сами они не выполняются."""

    def __init__(self) -> None:
        self.events: list[str] = []
        self.detached: list[tuple[JobSpec, IJobObserver | None]] = []
        self.submit_error: Exception | None = None

    def submit_detached(self, spec: JobSpec, observer: IJobObserver | None = None) -> None:
        if self.submit_error is not None:
            raise self.submit_error
        self.events.append("submit")
        self.detached.append((spec, observer))


def _make_uc(
    project: Project,
    manager: OfficeEditorManager,
    client: MagicMock | None = None,
    dispatcher: FakeJobDispatcher | None = None,
) -> tuple[OfficeEditorCallbackUC, AsyncMock]:
    template_repo = MagicMock()
    template_repo.get_version.return_value = make_template_version(documents=(_pres_definition(),))
    put_file_uc = AsyncMock()
    settings_repo = MagicMock()
    settings_repo.get.return_value = {}
    uc = OfficeEditorCallbackUC(
        project_repo=MagicMock(),
        project_index_repo=MagicMock(),
        template_repo=template_repo,
        manager=manager,
        put_file_uc=put_file_uc,
        dispatcher=dispatcher or FakeJobDispatcher(),
        settings_repo=settings_repo,
        client=client or MagicMock(),
    )
    uc._get_uc = AsyncMock()
    uc._get_uc.execute.return_value = SimpleNamespace(project=project)
    return uc, put_file_uc


def _inp(
    manager: OfficeEditorManager,
    project_id: UUID,
    body: dict,
    *,
    sig: str | None = None,
    authorization: str | None = None,
) -> OfficeEditorCallbackInput:
    return OfficeEditorCallbackInput(
        project_id=project_id,
        doc_id="pres",
        sig=sig if sig is not None else callback_signature(manager.jwt_secret, project_id, "pres"),
        body=body,
        authorization=authorization,
    )


@pytest.mark.unit
async def test__callback__save_status_2__downloads_and_writes_via_put_file(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager._base_url = "http://127.0.0.1:5555"
    manager.mark_active("key-1")
    project_id = uuid4()
    project = make_project(folder=tmp_path, documents=[make_document("pres", chosen_variant="pptx")])
    client = MagicMock()
    client.get.return_value = SimpleNamespace(status_code=200, content=b"PPTX-EDITED")
    uc, put_file_uc = _make_uc(project, manager, client)
    body = {
        "status": 2,
        "key": "key-1",
        # DS отдаёт self-ссылку со своим внутренним хостом — она должна быть
        # переписана на published-адрес контейнера
        "url": "http://ds-internal:80/cache/files/data/output.pptx?md5=x",
        "token": sign({"status": 2, "key": "key-1"}, manager.jwt_secret),
    }

    result = await uc.execute(_inp(manager, project_id, body))

    assert result == {"error": 0}
    client.get.assert_called_once()
    assert client.get.call_args.args[0] == "http://127.0.0.1:5555/cache/files/data/output.pptx?md5=x"
    put_file_uc.execute.assert_awaited_once()
    put_inp = put_file_uc.execute.await_args.args[0]
    assert put_inp.project_id == project_id
    assert put_inp.path == "pres/pptx/presentation.pptx"  # путь резолвится по шаблону, не из колбэка
    assert put_inp.content == b"PPTX-EDITED"
    assert "key-1" not in manager._active_keys  # сохранение закрывает сессию


def _save_body(manager: OfficeEditorManager, ext: str = "pptx") -> dict:
    return {
        "status": 2,
        "key": "key-1",
        "url": f"http://ds-internal:80/cache/files/data/output.{ext}?md5=x",
        "token": sign({"status": 2, "key": "key-1"}, manager.jwt_secret),
    }


def _pptx_client() -> MagicMock:
    client = MagicMock()
    client.get.return_value = SimpleNamespace(status_code=200, content=b"PPTX-EDITED")
    return client


@pytest.mark.unit
async def test__callback_save__convertible__submits_detached_office_job_after_put_file(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager._base_url = "http://127.0.0.1:5555"
    manager.mark_active("key-1")
    project_id = uuid4()
    project = make_project(folder=tmp_path, documents=[make_document("pres", chosen_variant="pptx")])
    dispatcher = FakeJobDispatcher()
    uc, put_file_uc = _make_uc(project, manager, _pptx_client(), dispatcher)
    put_file_uc.execute.side_effect = lambda _inp: dispatcher.events.append("put_file")

    result = await uc.execute(_inp(manager, project_id, _save_body(manager)))

    assert result == {"error": 0}
    # Задача ставится после put_file и закрытия сессии, и ровно одна.
    assert dispatcher.events == ["put_file", "submit"]
    assert "key-1" not in manager._active_keys
    ((spec, observer),) = dispatcher.detached
    assert isinstance(spec, JobSpec)
    assert spec.kind is JobKind.office_convert
    assert spec.project_id == project.id
    assert spec.local_root == tmp_path
    assert spec.tags == frozenset({"office"})
    payload = spec.payload
    assert isinstance(payload, OfficeConvertPayload)
    assert payload.source.path == "pres/pptx/presentation.pptx"
    assert payload.output_path == "pres/pptx/presentation.pdf"
    assert payload.reason is OfficeConvertReason.save_refresh
    # Образ берётся активный (по умолчанию деплоя), а не None, как у загрузки.
    assert payload.image
    assert isinstance(observer, PreviewRefreshObserver)


@pytest.mark.unit
async def test__callback_save__custom_docx__job_targets_stored_path(tmp_path: Path) -> None:
    # У custom-файла нет варианта шаблона: путь берётся из custom_file.stored_path.
    manager = _make_manager(tmp_path)
    manager._base_url = "http://127.0.0.1:5555"
    custom_file = CustomFileOverride(
        original_filename="report.docx",
        stored_path="pres/_custom/report.docx",
        ext=".docx",
        uploaded_at="2026-07-21T00:00:00",
    )
    project = make_project(folder=tmp_path, documents=[make_document("pres", custom_file=custom_file)])
    client = MagicMock()
    client.get.return_value = SimpleNamespace(status_code=200, content=b"DOCX-EDITED")
    dispatcher = FakeJobDispatcher()
    uc, put_file_uc = _make_uc(project, manager, client, dispatcher)

    result = await uc.execute(_inp(manager, uuid4(), _save_body(manager, "docx")))

    assert result == {"error": 0}
    put_inp = put_file_uc.execute.await_args.args[0]
    assert put_inp.path == "pres/_custom/report.docx"
    assert put_inp.content == b"DOCX-EDITED"
    payload = dispatcher.detached[0][0].payload
    assert isinstance(payload, OfficeConvertPayload)
    assert payload.source.path == "pres/_custom/report.docx"
    assert payload.output_path == "pres/_custom/report.pdf"


@pytest.mark.unit
async def test__callback_save__non_convertible__no_job(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager._base_url = "http://127.0.0.1:5555"
    custom_file = CustomFileOverride(
        original_filename="notes.pdf",
        stored_path="pres/_custom/notes.pdf",
        ext=".pdf",
        uploaded_at="2026-07-21T00:00:00",
    )
    project = make_project(folder=tmp_path, documents=[make_document("pres", custom_file=custom_file)])
    dispatcher = FakeJobDispatcher()
    uc, put_file_uc = _make_uc(project, manager, _pptx_client(), dispatcher)

    result = await uc.execute(_inp(manager, uuid4(), _save_body(manager)))

    assert result == {"error": 0}
    put_file_uc.execute.assert_awaited_once()
    assert dispatcher.detached == []


@pytest.mark.unit
async def test__callback_save__submit_raises__still_returns_error_0(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager._base_url = "http://127.0.0.1:5555"
    manager.mark_active("key-1")
    project = make_project(folder=tmp_path, documents=[make_document("pres", chosen_variant="pptx")])
    dispatcher = FakeJobDispatcher()
    dispatcher.submit_error = RuntimeError("no running loop")
    uc, put_file_uc = _make_uc(project, manager, _pptx_client(), dispatcher)

    result = await uc.execute(_inp(manager, uuid4(), _save_body(manager)))

    assert result == {"error": 0}
    put_file_uc.execute.assert_awaited_once()
    assert "key-1" not in manager._active_keys


@pytest.mark.unit
@pytest.mark.parametrize("status", [1, 3, 4, 7])
async def test__callback_status_editing_and_closed__no_job(tmp_path: Path, status: int) -> None:
    manager = _make_manager(tmp_path)
    project = make_project(folder=tmp_path, documents=[make_document("pres", chosen_variant="pptx")])
    dispatcher = FakeJobDispatcher()
    uc, put_file_uc = _make_uc(project, manager, dispatcher=dispatcher)

    result = await uc.execute(
        _inp(manager, uuid4(), {"status": status, "key": "k", "token": sign({"status": status}, manager.jwt_secret)})
    )

    assert result == {"error": 0}
    put_file_uc.execute.assert_not_awaited()
    assert dispatcher.detached == []


@pytest.mark.unit
async def test__callback__returns_before_job_finishes(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager._base_url = "http://127.0.0.1:5555"
    project = make_project(folder=tmp_path, documents=[make_document("pres", chosen_variant="pptx")])
    release = asyncio.Event()
    finished: list[str] = []

    class SlowDispatcher(FakeJobDispatcher):
        def submit_detached(self, spec: JobSpec, observer: IJobObserver | None = None) -> None:
            async def _job() -> None:
                await release.wait()
                finished.append("done")

            self.task = asyncio.get_running_loop().create_task(_job())

    dispatcher = SlowDispatcher()
    uc, _put_file_uc = _make_uc(project, manager, _pptx_client(), dispatcher)

    result = await uc.execute(_inp(manager, uuid4(), _save_body(manager)))

    assert result == {"error": 0}
    assert finished == []
    release.set()
    await dispatcher.task
    assert finished == ["done"]


@pytest.mark.unit
async def test__callback__bad_sig__rejected(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    project_id = uuid4()
    project = make_project(folder=tmp_path, documents=[make_document("pres", chosen_variant="pptx")])
    uc, put_file_uc = _make_uc(project, manager)
    body = {"status": 2, "key": "k", "token": sign({"status": 2}, manager.jwt_secret)}

    with pytest.raises(PermissionError, match="неверная подпись"):
        await uc.execute(_inp(manager, project_id, body, sig="deadbeef"))
    put_file_uc.execute.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.parametrize(
    ("body", "match"),
    [
        ({"status": 1, "token": sign({"s": 1}, "wrong-secret")}, "недействительный JWT"),
        ({"status": 1}, "отсутствует JWT"),
    ],
)
async def test__callback__bad_jwt__rejected(tmp_path: Path, body: dict, match: str) -> None:
    manager = _make_manager(tmp_path)
    project_id = uuid4()
    project = make_project(folder=tmp_path, documents=[make_document("pres", chosen_variant="pptx")])
    uc, _put_file_uc = _make_uc(project, manager)

    with pytest.raises(PermissionError, match=match):
        await uc.execute(_inp(manager, project_id, body))


@pytest.mark.unit
async def test__callback__status_1_and_4__toggle_active_set(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    project_id = uuid4()
    project = make_project(folder=tmp_path, documents=[make_document("pres", chosen_variant="pptx")])
    uc, _put_file_uc = _make_uc(project, manager)

    result = await uc.execute(
        _inp(manager, project_id, {"status": 1, "key": "key-9", "token": sign({"status": 1}, manager.jwt_secret)})
    )
    assert result == {"error": 0}
    assert "key-9" in manager._active_keys

    result = await uc.execute(
        _inp(manager, project_id, {"status": 4, "key": "key-9", "token": sign({"status": 4}, manager.jwt_secret)})
    )
    assert result == {"error": 0}
    assert "key-9" not in manager._active_keys


@pytest.mark.unit
async def test__callback__jwt_from_authorization_header(tmp_path: Path) -> None:
    # DS может слать JWT не в теле, а в Authorization: Bearer <token>
    manager = _make_manager(tmp_path)
    project_id = uuid4()
    project = make_project(folder=tmp_path, documents=[make_document("pres", chosen_variant="pptx")])
    uc, _put_file_uc = _make_uc(project, manager)
    token = sign({"status": 1}, manager.jwt_secret)

    result = await uc.execute(_inp(manager, project_id, {"status": 1, "key": "k"}, authorization=f"Bearer {token}"))

    assert result == {"error": 0}
    assert "k" in manager._active_keys


@pytest.mark.unit
@pytest.mark.parametrize("status", [3, 7])
async def test__callback__save_error_statuses__logged_but_ok(tmp_path: Path, status: int) -> None:
    manager = _make_manager(tmp_path)
    project_id = uuid4()
    project = make_project(folder=tmp_path, documents=[make_document("pres", chosen_variant="pptx")])
    uc, put_file_uc = _make_uc(project, manager)

    result = await uc.execute(
        _inp(manager, project_id, {"status": status, "token": sign({"status": status}, manager.jwt_secret)})
    )

    assert result == {"error": 0}
    put_file_uc.execute.assert_not_awaited()
