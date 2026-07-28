from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.catalog import DocumentDefinition, DocumentVariant
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.value_objects import CustomFileOverride
from hse_doc_studio.infra.docker.siblings import SiblingNetwork
from hse_doc_studio.infra.office.editor_manager import OfficeEditorManager
from hse_doc_studio.infra.office.jwt import sign
from hse_doc_studio.use_cases.office_editor.get_editor_config import callback_signature
from hse_doc_studio.use_cases.office_editor.handle_callback import (
    OfficeEditorCallbackInput,
    OfficeEditorCallbackUC,
)

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


def _make_uc(
    project: Project,
    manager: OfficeEditorManager,
    client: MagicMock | None = None,
    convert_manager: AsyncMock | None = None,
) -> tuple[OfficeEditorCallbackUC, AsyncMock]:
    template_repo = MagicMock()
    template_repo.get_version.return_value = make_template_version(documents=(_pres_definition(),))
    put_file_uc = AsyncMock()
    if convert_manager is None:
        # Дефолт — «конвертация недоступна»: сохранение не должно от неё зависеть.
        convert_manager = AsyncMock()
        convert_manager.convert_to_pdf.return_value = None
    settings_repo = MagicMock()
    settings_repo.get.return_value = {}
    uc = OfficeEditorCallbackUC(
        project_repo=MagicMock(),
        project_index_repo=MagicMock(),
        template_repo=template_repo,
        manager=manager,
        put_file_uc=put_file_uc,
        convert_manager=convert_manager,
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
    # Доконвертация предпросмотра фоновая — дожидаемся детерминированно.
    await asyncio.gather(*uc._preview_tasks)

    assert result == {"error": 0}
    client.get.assert_called_once()
    assert client.get.call_args.args[0] == "http://127.0.0.1:5555/cache/files/data/output.pptx?md5=x"
    put_file_uc.execute.assert_awaited_once()
    put_inp = put_file_uc.execute.await_args.args[0]
    assert put_inp.project_id == project_id
    assert put_inp.path == "pres/pptx/presentation.pptx"  # путь резолвится по шаблону, не из колбэка
    assert put_inp.content == b"PPTX-EDITED"
    assert "key-1" not in manager._active_keys  # сохранение закрывает сессию


@pytest.mark.unit
async def test__callback__save__refreshes_pdf_preview_in_background(tmp_path: Path) -> None:
    # Сохранение переконвертирует соседний PDF-предпросмотр (без пересборки);
    # сбой/недоступность конвертера сохранение не ломает (см. тест выше, где
    # convert_to_pdf → None).
    manager = _make_manager(tmp_path)
    manager._base_url = "http://127.0.0.1:5555"
    project_id = uuid4()
    project = make_project(folder=tmp_path, documents=[make_document("pres", chosen_variant="pptx")])
    (tmp_path / "pres" / "pptx").mkdir(parents=True)
    client = MagicMock()
    client.get.return_value = SimpleNamespace(status_code=200, content=b"PPTX-EDITED")
    convert_manager = AsyncMock()
    convert_manager.convert_to_pdf.return_value = b"%PDF-preview"
    uc, _put_file_uc = _make_uc(project, manager, client, convert_manager)
    body = {
        "status": 2,
        "key": "key-1",
        "url": "http://ds-internal:80/cache/files/data/output.pptx?md5=x",
        "token": sign({"status": 2, "key": "key-1"}, manager.jwt_secret),
    }

    result = await uc.execute(_inp(manager, project_id, body))
    await asyncio.gather(*uc._preview_tasks)

    assert result == {"error": 0}
    convert_manager.convert_to_pdf.assert_awaited_once()
    assert convert_manager.convert_to_pdf.await_args.args[0] == tmp_path / "pres/pptx/presentation.pptx"
    assert (tmp_path / "pres/pptx/presentation.pdf").read_bytes() == b"%PDF-preview"


@pytest.mark.unit
async def test__callback__custom_docx__writes_to_stored_path_and_refreshes_preview(tmp_path: Path) -> None:
    # A custom-file doc has no chosen_variant/template output — the callback
    # must resolve output_file from custom_file.stored_path, not the pack.
    manager = _make_manager(tmp_path)
    manager._base_url = "http://127.0.0.1:5555"
    project_id = uuid4()
    custom_file = CustomFileOverride(
        original_filename="report.docx",
        stored_path="pres/_custom/report.docx",
        ext=".docx",
        uploaded_at="2026-07-21T00:00:00",
    )
    project = make_project(folder=tmp_path, documents=[make_document("pres", custom_file=custom_file)])
    (tmp_path / "pres" / "_custom").mkdir(parents=True)
    client = MagicMock()
    client.get.return_value = SimpleNamespace(status_code=200, content=b"DOCX-EDITED")
    convert_manager = AsyncMock()
    convert_manager.convert_to_pdf.return_value = b"%PDF-preview"
    uc, put_file_uc = _make_uc(project, manager, client, convert_manager)
    body = {
        "status": 2,
        "key": "key-1",
        "url": "http://ds-internal:80/cache/files/data/output.docx?md5=x",
        "token": sign({"status": 2, "key": "key-1"}, manager.jwt_secret),
    }

    result = await uc.execute(_inp(manager, project_id, body))
    await asyncio.gather(*uc._preview_tasks)

    assert result == {"error": 0}
    put_inp = put_file_uc.execute.await_args.args[0]
    assert put_inp.path == "pres/_custom/report.docx"
    assert put_inp.content == b"DOCX-EDITED"
    convert_manager.convert_to_pdf.assert_awaited_once()
    assert (tmp_path / "pres/_custom/report.pdf").read_bytes() == b"%PDF-preview"


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
