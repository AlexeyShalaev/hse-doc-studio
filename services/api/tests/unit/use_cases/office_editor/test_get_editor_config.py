from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from hse_doc_studio.core.catalog import DocumentDefinition, DocumentVariant
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import EngineType
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.value_objects import CustomFileOverride
from hse_doc_studio.infra.office.jwt import verify
from hse_doc_studio.use_cases.office_editor.get_editor_config import (
    GetOfficeEditorConfigInput,
    GetOfficeEditorConfigUC,
    NotOfficeDocumentError,
    build_document_key,
    callback_signature,
)

from tests.factories import make_document, make_document_definition, make_project, make_template_version

_SECRET = "test-secret"  # noqa: S105
_BACKEND_BASE = "http://host.docker.internal:17240"


def _pres_definition() -> DocumentDefinition:
    pptx_variant = DocumentVariant(
        id="pptx",
        label={"ru": "PowerPoint"},
        source_file="pres/pptx/presentation.pptx",
        output_file="pres/pptx/presentation.pptx",
        output_name={"ru": "Презентация.pptx"},
        engine=None,
    )
    beamer_variant = DocumentVariant(
        id="beamer",
        label={"ru": "Beamer"},
        source_file="pres/beamer/pres.tex",
        output_file="pres/beamer/pres.pdf",
        output_name={"ru": "Презентация.pdf"},
        engine=EngineType.xelatex,
    )
    return make_document_definition("pres", required=False, variants=(pptx_variant, beamer_variant))


def _reachability_mock() -> MagicMock:
    reachability = MagicMock()
    reachability.base_url = AsyncMock(return_value=_BACKEND_BASE)
    return reachability


def _manager_mock() -> MagicMock:
    manager = MagicMock()
    manager.is_image_missing = AsyncMock(return_value=False)
    manager.ensure_running = AsyncMock(return_value="http://127.0.0.1:9999")
    manager.jwt_secret = _SECRET
    manager.image = "onlyoffice/documentserver:latest"
    return manager


def _make_uc(
    project: Project,
    manager: MagicMock,
    stored_settings: dict[str, object] | None = None,
) -> GetOfficeEditorConfigUC:
    template_repo = MagicMock()
    template_repo.get_version.return_value = make_template_version(documents=(_pres_definition(),))
    settings_repo = MagicMock()
    settings_repo.get.return_value = dict(stored_settings or {})
    uc = GetOfficeEditorConfigUC(
        project_repo=MagicMock(),
        project_index_repo=MagicMock(),
        template_repo=template_repo,
        manager=manager,
        reachability=_reachability_mock(),
        settings_repo=settings_repo,
    )
    uc._get_uc = AsyncMock()
    uc._get_uc.execute.return_value = SimpleNamespace(project=project)
    return uc


def _pptx_project(tmp_path: Path) -> Project:
    (tmp_path / "pres" / "pptx").mkdir(parents=True)
    (tmp_path / "pres" / "pptx" / "presentation.pptx").write_bytes(b"PK-pptx")
    return make_project(folder=tmp_path, documents=[make_document("pres", chosen_variant="pptx")])


@pytest.mark.unit
async def test__editor_config__non_pptx_variant__rejected(tmp_path: Path) -> None:
    # beamer-вариант производит PDF — в DS-редакторе открывать нечего (→ 400)
    project = make_project(folder=tmp_path, documents=[make_document("pres", chosen_variant="beamer")])
    uc = _make_uc(project, _manager_mock())

    with pytest.raises(NotOfficeDocumentError):
        await uc.execute(GetOfficeEditorConfigInput(project_id=uuid4(), doc_id="pres"))


@pytest.mark.unit
async def test__editor_config__ready__full_signed_config(tmp_path: Path) -> None:
    project = _pptx_project(tmp_path)
    uc = _make_uc(project, _manager_mock())
    project_id = uuid4()

    out = await uc.execute(GetOfficeEditorConfigInput(project_id=project_id, doc_id="pres"))

    assert out.state == "ready"
    assert out.editor_base_url == "http://127.0.0.1:9999"
    assert out.api_js_url == "http://127.0.0.1:9999/web-apps/apps/api/documents/api.js"
    config = dict(out.config or {})
    token = config.pop("token")
    # Токен подписывает конфиг БЕЗ поля token — DS валидирует его тем же секретом
    assert verify(token, _SECRET) == config
    doc_cfg = config["document"]
    assert doc_cfg["fileType"] == "pptx"
    assert doc_cfg["title"] == "Презентация.pptx"
    assert doc_cfg["url"] == f"{_BACKEND_BASE}/api/v1/projects/{project_id}/files/pres/pptx/presentation.pptx"
    assert set(doc_cfg["key"]) <= set("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ._-")
    assert len(doc_cfg["key"]) <= 128
    editor_cfg = config["editorConfig"]
    assert editor_cfg["mode"] == "edit"
    sig = callback_signature(_SECRET, project_id, "pres")
    assert editor_cfg["callbackUrl"] == (
        f"{_BACKEND_BASE}/api/v1/office-editor/callback?project_id={project_id}&doc_id=pres&sig={sig}"
    )
    assert editor_cfg["user"] == {"id": "hse-studio", "name": "Test Author"}
    assert editor_cfg["customization"]["forcesave"] is True
    assert config["documentType"] == "slide"


@pytest.mark.unit
async def test__editor_config__key_changes_when_file_mtime_changes(tmp_path: Path) -> None:
    # Новый key после правки файла заставляет DS перечитать документ (сброс кэша)
    project = _pptx_project(tmp_path)
    uc = _make_uc(project, _manager_mock())
    project_id = uuid4()
    artifact = tmp_path / "pres" / "pptx" / "presentation.pptx"

    out1 = await uc.execute(GetOfficeEditorConfigInput(project_id=project_id, doc_id="pres"))
    stat = artifact.stat()
    os.utime(artifact, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))
    out2 = await uc.execute(GetOfficeEditorConfigInput(project_id=project_id, doc_id="pres"))

    assert out1.config is not None
    assert out2.config is not None
    assert out1.config["document"]["key"] != out2.config["document"]["key"]


@pytest.mark.unit
async def test__editor_config__custom_docx__resolves_word_document_type(tmp_path: Path) -> None:
    (tmp_path / "pres" / "_custom").mkdir(parents=True)
    (tmp_path / "pres" / "_custom" / "report.docx").write_bytes(b"PK-docx")
    custom_file = CustomFileOverride(
        original_filename="report.docx",
        stored_path="pres/_custom/report.docx",
        ext=".docx",
        uploaded_at="2026-07-21T00:00:00",
    )
    project = make_project(folder=tmp_path, documents=[make_document("pres", custom_file=custom_file)])
    uc = _make_uc(project, _manager_mock())

    out = await uc.execute(GetOfficeEditorConfigInput(project_id=uuid4(), doc_id="pres"))

    assert out.state == "ready"
    config = dict(out.config or {})
    doc_cfg = config["document"]
    assert doc_cfg["fileType"] == "docx"
    assert doc_cfg["title"] == "report.docx"
    assert doc_cfg["url"].endswith("pres/_custom/report.docx")
    assert config["documentType"] == "word"


@pytest.mark.unit
async def test__editor_config__custom_unsupported_ext__rejected(tmp_path: Path) -> None:
    (tmp_path / "pres" / "_custom").mkdir(parents=True)
    (tmp_path / "pres" / "_custom" / "notes.log").write_bytes(b"plain text")
    custom_file = CustomFileOverride(
        original_filename="notes.log",
        stored_path="pres/_custom/notes.log",
        ext=".log",
        uploaded_at="2026-07-21T00:00:00",
    )
    project = make_project(folder=tmp_path, documents=[make_document("pres", custom_file=custom_file)])
    uc = _make_uc(project, _manager_mock())

    with pytest.raises(NotOfficeDocumentError):
        await uc.execute(GetOfficeEditorConfigInput(project_id=uuid4(), doc_id="pres"))


@pytest.mark.unit
async def test__editor_config__image_missing__reports_opt_in(tmp_path: Path) -> None:
    project = _pptx_project(tmp_path)
    manager = _manager_mock()
    manager.is_image_missing = AsyncMock(return_value=True)
    uc = _make_uc(project, manager)

    out = await uc.execute(GetOfficeEditorConfigInput(project_id=uuid4(), doc_id="pres"))

    assert out.state == "image_missing"
    assert out.image == "onlyoffice/documentserver:latest"
    assert out.settings_section == "presentations"  # фронт ведёт в настройки «Презентации»
    assert out.config is None
    manager.ensure_running.assert_not_awaited()


@pytest.mark.unit
async def test__editor_config__runtime_image_override__used_for_manager_calls(tmp_path: Path) -> None:
    # office_editor_image из настроек побеждает деплой-дефолт: и is_image_missing,
    # и карточка image_missing работают с ЭФФЕКТИВНЫМ образом.
    project = _pptx_project(tmp_path)
    manager = _manager_mock()
    manager.is_image_missing = AsyncMock(return_value=True)
    uc = _make_uc(project, manager, stored_settings={"office_editor_image": "onlyoffice/documentserver:9"})

    out = await uc.execute(GetOfficeEditorConfigInput(project_id=uuid4(), doc_id="pres"))

    assert out.state == "image_missing"
    assert out.image == "onlyoffice/documentserver:9"
    manager.is_image_missing.assert_awaited_once_with("onlyoffice/documentserver:9")


@pytest.mark.unit
async def test__editor_config__container_failed__unavailable(tmp_path: Path) -> None:
    project = _pptx_project(tmp_path)
    manager = _manager_mock()
    manager.ensure_running = AsyncMock(return_value=None)
    uc = _make_uc(project, manager)

    out = await uc.execute(GetOfficeEditorConfigInput(project_id=uuid4(), doc_id="pres"))

    assert out.state == "unavailable"
    assert out.detail
    assert out.config is None


@pytest.mark.unit
async def test__editor_config__missing_artifact__raises(tmp_path: Path) -> None:
    project = make_project(folder=tmp_path, documents=[make_document("pres", chosen_variant="pptx")])
    uc = _make_uc(project, _manager_mock())

    with pytest.raises(NotFoundError, match="не найден"):
        await uc.execute(GetOfficeEditorConfigInput(project_id=uuid4(), doc_id="pres"))


@pytest.mark.unit
def test__build_document_key__sanitizes_and_caps_length() -> None:
    key = build_document_key("докумэнт с пробелами/и слэшами" * 10, 123456789, 42)

    assert len(key) <= 128
    assert set(key) <= set("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ._-")


@pytest.mark.unit
async def test__editor_config__syncs_ai_plugin_settings_before_session(tmp_path: Path) -> None:
    # Перед выдачей конфига новой сессии наши AI-провайдеры реконсилируются в
    # серверные настройки AI-плагина DS (best-effort, через manager).
    from datetime import datetime, timezone

    from hse_doc_studio.core.entities import AIProvider
    from hse_doc_studio.core.enums import AIProviderType

    project = _pptx_project(tmp_path)
    manager = _manager_mock()
    manager.apply_ai_settings = AsyncMock(return_value=True)
    uc = _make_uc(project, manager)
    provider = AIProvider(
        id=uuid4(),
        name="OpenAI",
        type=AIProviderType.openai,
        api_key="sk-key",
        base_url="",
        models=["gpt-4o"],
        created_at=datetime.now(timezone.utc),
    )
    ai_repo = MagicMock()
    ai_repo.list_all.return_value = [provider]
    uc._ai_provider_repo = ai_repo

    out = await uc.execute(GetOfficeEditorConfigInput(project_id=uuid4(), doc_id="pres"))

    assert out.state == "ready"
    manager.apply_ai_settings.assert_awaited_once()
    (desired,) = manager.apply_ai_settings.await_args.args
    assert out.editor_base_url == "http://127.0.0.1:9999"
    assert desired["providers"]["OpenAI"]["key"] == "sk-key"
    assert desired["actions"]["Chat"] == {"model": "gpt-4o"}
