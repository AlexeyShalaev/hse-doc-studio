"""Характеризация создания пакета сдачи (POST /submissions).

Фиксирует наблюдаемый результат сборки: имена файлов в архиве, штампы подписей,
командный охват, NDA, формы-extras, замороженные PDF с открепленными подписями,
запись, журнал изменений и тексты ошибок. Это страховочная сетка для разделения
сборки на планировщик и исполнитель: тесты читают только HTTP-ответы, архив и файлы
проекта и не знают, кто и в каком потоке собирает пакет.

Подменяются только внешние зависимости: gpg (проверка и экспорт открытого ключа) и
поиск внешнего архиватора. Реальные паки подходят почти для всех сценариев; пак с
файловой группой NDA и профилем extras собирается копией `hse-cs-se` в tmp_path,
потому что в выпущенных паках блока `nda:` больше нет, а ветка сборки пакета осталась.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import shutil
import zipfile
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring, GpgVerification
from hse_doc_studio.use_cases.forms.render_form import RenderFormUC
from httpx import ASGITransport, AsyncClient, Response
from pypdf import PdfReader
from pytest_mock import MockerFixture
from reportlab.pdfgen import canvas

from tests.factories import project_api_payload
from tests.fixtures.app import _PACKS_DIR, create_test_app, create_test_container
from tests.integration.api.signatures.test_detached_signatures import (
    _attach,
    _enable_detached_slot,
    _freeze,
    _frozen_bytes,
)
from tests.integration.api.submission.test_submission import _CHECKPOINT_1, _PNG_1PX, _sign_annotation
from tests.unit.infra.signatures.gost_fixture import make_detached_cms, make_identity

_CHECKPOINT_3 = "checkpoint-3"
_EXTRAS_PROFILE = "j0b-extras"
_TEAM_AUTHORS = [
    {"name": "Иванов Иван", "group": None, "email": None},
    {"name": "Петров Пётр", "group": None, "email": None},
]
# `<профиль>[-<автор>]-<метка времени>-<8 hex id>`: метка и id зависят от запуска, поэтому только по маске.
_STAMP_RE = r"\d{8}T\d{6}-[0-9a-f]{8}"

_PGP_SIGNATURE = b"-----BEGIN PGP SIGNATURE-----\n\nfake\n-----END PGP SIGNATURE-----\n"
_PGP_PUBLIC_KEY = b"-----BEGIN PGP PUBLIC KEY BLOCK-----\n\nfake-key\n-----END PGP PUBLIC KEY BLOCK-----\n"
_PGP_FINGERPRINT = "A" * 40


# --- helpers ---------------------------------------------------------------


def _make_pdf(path: Path, text: str) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(path))
    pdf.drawString(100, 700, text)
    pdf.save()
    return path.read_bytes()


async def _create_project(client: AsyncClient, folder: Path, **overrides: Any) -> dict[str, Any]:
    folder.mkdir(exist_ok=True)
    payload = {**project_api_payload(str(folder)), **overrides}
    resp = await client.post("/api/v1/projects", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _documents(client: AsyncClient, project: dict[str, Any]) -> dict[str, dict[str, Any]]:
    resp = await client.get(f"/api/v1/projects/{project['id']}/documents")
    assert resp.status_code == 200, resp.text
    return {doc["id"]: doc for doc in resp.json()}


async def _write_outputs(
    client: AsyncClient, project: dict[str, Any], only: set[str] | None = None
) -> dict[str, bytes]:
    """Кладёт на место скомпилированных PDF по одному файлу на документ; возвращает doc_id -> байты."""
    written: dict[str, bytes] = {}
    for doc_id, doc in (await _documents(client, project)).items():
        if only is None or doc_id in only:
            written[doc_id] = _make_pdf(Path(project["folder"]) / doc["output_file"], doc_id)
    return written


def _body(profile_id: str, **extra: Any) -> dict[str, Any]:
    return {"profile_id": profile_id, "items": [], "extra_items": [], "archive_format": "zip", **extra}


async def _submit(client: AsyncClient, project: dict[str, Any], profile_id: str, **extra: Any) -> Response:
    return await client.post(f"/api/v1/projects/{project['id']}/submissions", json=_body(profile_id, **extra))


async def _create(client: AsyncClient, project: dict[str, Any], profile_id: str, **extra: Any) -> dict[str, Any]:
    resp = await _submit(client, project, profile_id, **extra)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _archive(record: dict[str, Any]) -> dict[str, bytes]:
    with zipfile.ZipFile(io.BytesIO(Path(record["output_path"]).read_bytes())) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _folder_content(folder: Path) -> list[str]:
    return sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file())


# --- derived pack: NDA file group and an extras profile -----------------------

_EXTRAS_PROFILE_YAML = f"""\
    - id: {_EXTRAS_PROFILE}
      name: {{ru: "Профиль extras", en: "Extras profile"}}
      description: {{ru: "Тестовый профиль", en: "Test profile"}}
      items:
        - doc_id: topic_presentation
          signatures: []
      extra_items:
        - source: .hse-studio/forms/ai_declaration.json
          output_name: "Декларация ИИ.md"
          format: markdown
        - source: .hse-studio/forms/code_link.json
          output_name: "Ссылка на код.txt"
          format: markdown
        - source: notes/answers.json
          output_name: "Ответы"
          format: markdown
        - source: notes/readme.txt
          output_name: "Заметки/Читай меня.txt"
        - source: notes/absent.txt
          output_name: "Отсутствует.txt"
        - source: ../outside.txt
          output_name: "Побег источника.txt"
        - source: notes/readme.txt
          output_name: "../evil.txt"

"""

_NDA_RECEIPT = "Расписка о неразглашении. Студент: {{ author.name }}\n"
_NDA_SCAN = b"\x89PNG scan bytes"


def _build_extras_pack(packs_dir: Path) -> None:
    """Копия реального пака с блоком `nda:` и профилем `j0b-extras`; выпущенный пак не трогаем."""
    shutil.copytree(_PACKS_DIR / "hse-cs-se", packs_dir / "hse-cs-se")
    version_dir = packs_dir / "hse-cs-se" / "templates" / "vkr" / "versions" / "2026.1"
    manifest = version_dir / "version.yaml"
    text = manifest.read_text(encoding="utf-8")
    anchor = "  profiles:\n    - id: checkpoint-1"
    assert anchor in text
    text = text.replace(anchor, "  profiles:\n" + _EXTRAS_PROFILE_YAML + "    - id: checkpoint-1", 1)
    manifest.write_text(text + "\nnda:\n  source_dir: nda-files\n  submission_dir: NDA\n", encoding="utf-8")
    nda_dir = version_dir / "files" / "nda-files"
    nda_dir.mkdir()
    (nda_dir / "receipt.txt").write_text(_NDA_RECEIPT, encoding="utf-8")
    (nda_dir / "scan.png").write_bytes(_NDA_SCAN)


@pytest_asyncio.fixture
async def extras_client(tmp_path: Path) -> AsyncIterator[AsyncClient]:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    packs_dir = tmp_path / "packs"
    _build_extras_pack(packs_dir)
    container = create_test_container(data_dir, packs_dir=packs_dir)
    app = create_test_app(container)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    await container.close()


# --- имена в архиве ----------------------------------------------------------

_SOLO_NAMES = {
    "ru": {
        "default": {
            "Техническое задание.pdf",
            "Выпускная квалификационная работа.pdf",
            "Программа и методика испытаний.pdf",
            "Текст программы.pdf",
            "Презентация.pptx",
        },
        "chosen": "Презентация.html",
    },
    "en": {
        "default": {
            "Statement of Work.pdf",
            "Thesis.pdf",
            "Test Program and Methodology.pdf",
            "Source Listing.pdf",
            "Presentation.pptx",
        },
        "chosen": "Presentation.html",
    },
}


@pytest.mark.parametrize("lang", ["ru", "en"])
async def test__api__create_submission__solo_zip_member_names_ru_en(
    test_app: AsyncClient, tmp_path: Path, lang: str
) -> None:
    project = await _create_project(test_app, tmp_path / "proj", kind="project", lang=lang)
    await _write_outputs(test_app, project)

    first = await _create(test_app, project, _CHECKPOINT_3)

    # Вариант не выбран: имя берётся у первого варианта презентации (pptx), остальные доки без суффикса автора.
    names = set(_archive(first))
    assert names == _SOLO_NAMES[lang]["default"]
    assert all(" — " not in name for name in names)

    resp = await test_app.patch(
        f"/api/v1/projects/{project['id']}/documents/presentation", json={"chosen_variant": "reveal"}
    )
    assert resp.status_code == 200, resp.text
    await _write_outputs(test_app, project, {"presentation"})

    second = await _create(test_app, project, _CHECKPOINT_3)

    chosen = set(_archive(second))
    assert chosen == (names - {"Презентация.pptx", "Presentation.pptx"}) | {_SOLO_NAMES[lang]["chosen"]}


async def test__api__create_submission__solo_ignores_author_slug(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj", kind="project")
    await _write_outputs(test_app, project, {"thesis"})

    record = await _create(test_app, project, _CHECKPOINT_3, author_slug="whoever")

    names = set(_archive(record))
    assert "Выпускная квалификационная работа.pdf" in names
    assert all(" — " not in name for name in names)
    assert "whoever" not in Path(record["output_path"]).name


# --- штампы подписей -----------------------------------------------------------


async def test__api__create_submission__stamp_present_and_source_untouched(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    await _sign_annotation(test_app, project["id"])
    sources = await _write_outputs(test_app, project, {"annotation", "topic_presentation"})
    folder = Path(project["folder"])

    record = await _create(test_app, project, _CHECKPOINT_1)

    files = _archive(record)
    assert set(files) == {"Презентация защиты темы.pdf", "Аннотация.pdf"}
    stamped = PdfReader(io.BytesIO(files["Аннотация.pdf"])).pages[0]
    # Подписи автора и руководителя наложены картинками на страницу, исходник остаётся чистым.
    assert len(PdfReader(io.BytesIO(sources["annotation"])).pages[0].images) == 0
    assert len(stamped.images) == 2  # noqa: PLR2004
    assert "annotation" in stamped.extract_text()
    assert (folder / "annotation" / "annotation.pdf").read_bytes() == sources["annotation"]
    # Документ без слотов подписей копируется байт в байт.
    assert files["Презентация защиты темы.pdf"] == sources["topic_presentation"]
    assert (Path(record["output_dir"]) / "Аннотация.pdf").read_bytes() == files["Аннотация.pdf"]


# --- командный пакет -----------------------------------------------------------

_TEAM_NAMES = {
    "ivanov": {
        "Общее техническое задание.pdf",
        "Общая программа и методика испытаний.pdf",
        "Техническое задание — Иванов.pdf",
        "Программа и методика испытаний — Иванов.pdf",
        "Текст программы — Иванов.pdf",
        "Выпускная квалификационная работа — Иванов.pdf",
        "Презентация — Иванов.pptx",
    },
    "petrov": {
        "Общее техническое задание.pdf",
        "Общая программа и методика испытаний.pdf",
        "Техническое задание — Петров.pdf",
        "Программа и методика испытаний — Петров.pdf",
        "Текст программы — Петров.pdf",
        "Выпускная квалификационная работа — Петров.pdf",
        "Презентация — Петров.pptx",
    },
}


async def test__api__create_submission__team_author_scope_and_surname_suffix(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj", kind="project", staffing="team", authors=_TEAM_AUTHORS)
    sources = await _write_outputs(test_app, project)

    for slug, surname, other in (("ivanov", "Иванов", "Петров"), ("petrov", "Петров", "Иванов")):
        record = await _create(test_app, project, _CHECKPOINT_3, author_slug=slug)

        files = _archive(record)
        assert set(files) == _TEAM_NAMES[slug]
        assert not any(other in name for name in files)
        # Личный документ берётся из папки автора, общий из shared; содержимое не перепутано.
        assert files[f"Выпускная квалификационная работа — {surname}.pdf"] == sources[f"thesis--{slug}"]
        assert files["Общее техническое задание.pdf"] == sources["shared_technical_specification"]
        assert re.fullmatch(rf"{_CHECKPOINT_3}-{slug}-{_STAMP_RE}\.zip", Path(record["output_path"]).name)
        assert re.fullmatch(rf"{_CHECKPOINT_3}-{slug}-{_STAMP_RE}", Path(record["output_dir"]).name)


@pytest.mark.parametrize(
    ("author_slug", "interface_lang", "detail"),
    [
        (None, "ru", "Командный проект: укажите существующего автора (author_slug) для пакета сдачи"),
        ("nobody", "ru", "Командный проект: укажите существующего автора (author_slug) для пакета сдачи"),
        (None, "en", "Team project: specify an existing author (author_slug) for the submission package"),
        ("nobody", "en", "Team project: specify an existing author (author_slug) for the submission package"),
    ],
)
async def test__api__create_submission__team_author_missing_or_unknown__400(
    test_app: AsyncClient, tmp_path: Path, author_slug: str | None, interface_lang: str, detail: str
) -> None:
    project = await _create_project(test_app, tmp_path / "proj", kind="project", staffing="team", authors=_TEAM_AUTHORS)
    await _write_outputs(test_app, project)
    body = _body(_CHECKPOINT_3, **({"author_slug": author_slug} if author_slug else {}))

    resp = await test_app.post(
        f"/api/v1/projects/{project['id']}/submissions", json=body, headers={"X-Interface-Language": interface_lang}
    )

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == detail
    assert not (Path(project["folder"]) / "submissions").exists()


# --- запись, журнал, форма ответа -------------------------------------------------


@pytest.mark.parametrize(
    ("archive_format", "ext", "media_type"),
    [("zip", ".zip", "application/zip"), ("targz", ".tar.gz", "application/gzip")],
)
async def test__api__create_submission__record_changelog_and_response_shape(
    test_app: AsyncClient, tmp_path: Path, archive_format: str, ext: str, media_type: str
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    await _sign_annotation(test_app, project["id"])
    await _write_outputs(test_app, project, {"annotation", "topic_presentation"})
    folder = Path(project["folder"])

    resp = await _submit(test_app, project, _CHECKPOINT_1, archive_format=archive_format)

    assert resp.status_code == 201, resp.text
    record = resp.json()
    assert set(record) == {
        "id",
        "profile_id",
        "profile_name",
        "created_at",
        "output_path",
        "output_dir",
        "size_bytes",
        "archive_format",
        "doc_count",
    }
    assert record["profile_name"] is None
    assert record["size_bytes"] is None
    assert record["archive_format"] == archive_format
    assert record["doc_count"] == 2  # noqa: PLR2004
    datetime.fromisoformat(record["created_at"])
    # Рядом лежат папка с PDF и архив: общее имя, расширение только у архива.
    base = f"{_CHECKPOINT_1}-{_STAMP_RE}"
    archive_name = Path(record["output_path"]).name
    assert re.fullmatch(rf"{base}{re.escape(ext)}", archive_name)
    assert re.fullmatch(base, Path(record["output_dir"]).name)
    assert Path(record["output_path"]).parent == folder / "submissions" == Path(record["output_dir"]).parent
    assert archive_name.endswith(ext)
    assert record["id"][:8] in archive_name
    assert _folder_content(Path(record["output_dir"])) == ["Аннотация.pdf", "Презентация защиты темы.pdf"]

    # Запись хранит пути относительно проекта и пункты профиля вместе с подписями.
    stored = json.loads((folder / ".hse-studio" / "submissions" / f"{record['id']}.json").read_text(encoding="utf-8"))
    assert stored == {
        "id": record["id"],
        "profile_id": _CHECKPOINT_1,
        "created_at": record["created_at"],
        "doc_items": [
            {"doc_id": "topic_presentation", "signatures": []},
            {"doc_id": "annotation", "signatures": ["author", "supervisor"]},
        ],
        "extra_items": [],
        "output_path": f"submissions/{archive_name}",
        "output_dir": f"submissions/{Path(record['output_dir']).name}",
        "archive_format": archive_format,
    }

    changelog = (await test_app.get(f"/api/v1/projects/{project['id']}/changelog")).json()
    pack_entries = [entry for entry in changelog if entry["kind"] == "pack_submission"]
    assert len(pack_entries) == 1
    assert pack_entries[0]["summary"] == f"Pack submission created: profile={_CHECKPOINT_1}, archive={archive_name}"
    assert pack_entries[0]["doc_id"] is None
    assert pack_entries[0]["note"] is None
    assert pack_entries[0]["at"] == record["created_at"]

    listed = (await test_app.get(f"/api/v1/projects/{project['id']}/submissions")).json()
    assert [item["id"] for item in listed] == [record["id"]]
    assert listed[0]["size_bytes"] == Path(record["output_path"]).stat().st_size

    download = await test_app.get(f"/api/v1/projects/{project['id']}/submissions/{record['id']}/download")
    assert download.status_code == 200, download.text
    assert download.headers["content-type"] == media_type
    assert download.content == Path(record["output_path"]).read_bytes()


async def test__api__create_submission__archive_tool_missing__400_before_any_work(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    await _sign_annotation(test_app, project["id"])
    await _write_outputs(test_app, project, {"annotation", "topic_presentation"})
    mocker.patch("shutil.which", return_value=None)

    resp = await _submit(test_app, project, _CHECKPOINT_1, archive_format="7z")

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == "Archive format '7z' is not available on this host (external tool missing)"
    assert not (Path(project["folder"]) / "submissions").exists()


async def test__api__create_submission__missing_source_skipped(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    await _sign_annotation(test_app, project["id"])
    # Презентация не скомпилирована: пункт пропускается без ошибки, но остаётся в записи пакета.
    await _write_outputs(test_app, project, {"annotation"})

    record = await _create(test_app, project, _CHECKPOINT_1)

    assert set(_archive(record)) == {"Аннотация.pdf"}
    assert record["doc_count"] == 2  # noqa: PLR2004


# --- NDA ---------------------------------------------------------------------


async def _put_form(client: AsyncClient, project: dict[str, Any], form_id: str, answers: dict[str, Any]) -> None:
    resp = await client.put(f"/api/v1/projects/{project['id']}/forms/{form_id}", json={"answers": answers})
    assert resp.status_code == 200, resp.text


async def test__api__create_submission__nda_files_included_solo(extras_client: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(extras_client, tmp_path / "proj", meta={"nda": True})
    await _write_outputs(extras_client, project, {"topic_presentation"})
    folder = Path(project["folder"])

    record = await _create(extras_client, project, _EXTRAS_PROFILE)

    # Файловая группа NDA лежит в корне проекта (receipt.txt отрендерен), а в пакет попадает под NDA/.
    assert (folder / "nda-files" / "receipt.txt").read_text(
        encoding="utf-8"
    ) == "Расписка о неразглашении. Студент: Ivan Ivanov\n"
    assert (folder / "nda-files" / "scan.png").read_bytes() == _NDA_SCAN
    files = _archive(record)
    assert files["NDA/receipt.txt"].decode("utf-8") == "Расписка о неразглашении. Студент: Ivan Ivanov\n"
    assert files["NDA/scan.png"] == _NDA_SCAN
    stored = json.loads((folder / ".hse-studio" / "submissions" / f"{record['id']}.json").read_text(encoding="utf-8"))
    nda_extras = [e for e in stored["extra_items"] if e["output_name"].startswith("NDA/")]
    assert nda_extras == [
        {"source": "nda-files/receipt.txt", "output_name": "NDA/receipt.txt", "format": None},
        {"source": "nda-files/scan.png", "output_name": "NDA/scan.png", "format": None},
    ]


async def test__api__create_submission__nda_off__nothing_instantiated_or_packaged(
    extras_client: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(extras_client, tmp_path / "proj")
    await _write_outputs(extras_client, project, {"topic_presentation"})

    record = await _create(extras_client, project, _EXTRAS_PROFILE)

    assert not (Path(project["folder"]) / "nda-files").exists()
    assert not [name for name in _archive(record) if name.startswith("NDA/")]


async def test__api__create_submission__nda_files_included_team_author_base(
    extras_client: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(
        extras_client,
        tmp_path / "proj",
        kind="project",
        staffing="team",
        authors=_TEAM_AUTHORS,
        meta={"nda": True},
    )
    await _write_outputs(extras_client, project, {"topic_presentation--ivanov", "topic_presentation--petrov"})
    folder = Path(project["folder"])

    record = await _create(extras_client, project, _EXTRAS_PROFILE, author_slug="ivanov")

    # Расписка персональная: в папку каждого автора кладётся своя копия, в пакет идёт только копия автора пакета.
    assert "Студент: Иванов Иван" in (folder / "ivanov" / "nda-files" / "receipt.txt").read_text(encoding="utf-8")
    assert "Студент: Петров Пётр" in (folder / "petrov" / "nda-files" / "receipt.txt").read_text(encoding="utf-8")
    assert not (folder / "nda-files").exists()
    files = _archive(record)
    assert files["NDA/receipt.txt"].decode("utf-8") == "Расписка о неразглашении. Студент: Иванов Иван\n"
    assert files["NDA/scan.png"] == _NDA_SCAN
    assert not [name for name in files if "Петров" in files[name].decode("utf-8", "ignore")]


# --- extras и формы ------------------------------------------------------------------


def _prepare_notes(folder: Path) -> None:
    notes = folder / "notes"
    notes.mkdir()
    (notes / "answers.json").write_text(json.dumps({"alpha": 1, "beta": "два"}), encoding="utf-8")
    (notes / "readme.txt").write_text("читай меня\n", encoding="utf-8")
    (folder.parent / "outside.txt").write_text("за пределами проекта\n", encoding="utf-8")


async def test__api__create_submission__form_extra_rendered_and_static_extras(
    extras_client: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(extras_client, tmp_path / "proj")
    await _write_outputs(extras_client, project, {"topic_presentation"})
    folder = Path(project["folder"])
    _prepare_notes(folder)
    await _put_form(extras_client, project, "ai_declaration", {"used_ai": "no"})
    await _put_form(extras_client, project, "code_link", {"repo_url": "https://example.org/repo"})

    record = await _create(extras_client, project, _EXTRAS_PROFILE)

    files = _archive(record)
    assert set(files) == {
        "Презентация защиты темы.pdf",
        "Декларация ИИ.md",
        "Ссылка на код.txt",
        "Ответы.md",
        "Заметки/",  # shutil.make_archive пишет и записи каталогов
        "Заметки/Читай меня.txt",
    }
    # Форма с шаблоном вывода отдаётся готовым документом, а не дампом json.
    declaration = files["Декларация ИИ.md"].decode("utf-8")
    assert declaration.startswith("# Декларация об использовании систем искусственного интеллекта")
    assert "**Студент:** Ivan Ivanov" in declaration
    assert "не использовал(а)" in declaration
    assert "https://example.org/repo" in files["Ссылка на код.txt"].decode("utf-8")
    # Расширение `.md` дописывается, только если в output_name его нет вовсе.
    assert files["Ответы.md"].decode("utf-8") == "# Ответы\n\n**alpha**: 1\n\n**beta**: два\n"
    assert files["Заметки/Читай меня.txt"] == "читай меня\n".encode()
    # Источник вне проекта, выход за пределы папки пакета и отсутствующий источник пропускаются молча.
    assert not (folder / "submissions" / "evil.txt").exists()
    assert not (Path(record["output_dir"]).parent / "evil.txt").exists()


@pytest.mark.parametrize("answered", [True, False])
async def test__api__create_submission__form_extra_degraded_when_render_fails(
    extras_client: AsyncClient, tmp_path: Path, mocker: MockerFixture, answered: bool
) -> None:
    project = await _create_project(extras_client, tmp_path / "proj")
    await _write_outputs(extras_client, project, {"topic_presentation"})
    _prepare_notes(Path(project["folder"]))
    if answered:
        await _put_form(extras_client, project, "ai_declaration", {"used_ai": "no"})
    mocker.patch.object(RenderFormUC, "execute", side_effect=ValueError("render failed"))

    record = await _create(extras_client, project, _EXTRAS_PROFILE)

    files = _archive(record)
    # Сбой отрисовки не валит сборку: форма уходит дампом ответов, а без сохранённых ответов пункт пропускается.
    assert ("Декларация ИИ.md" in files) is answered
    if answered:
        dump = files["Декларация ИИ.md"].decode("utf-8")
        assert dump.startswith("# Декларация ИИ.md\n\n**")
        assert "Декларация об использовании" not in dump
    assert "Ссылка на код.txt" not in files
    assert files["Ответы.md"].decode("utf-8") == "# Ответы\n\n**alpha**: 1\n\n**beta**: два\n"


# --- замороженные PDF с открепленными подписями ------------------------------------


async def _frozen_signed_project(
    client: AsyncClient, tmp_path: Path, mocker: MockerFixture, *, lang: str, signature_format: str
) -> tuple[dict[str, Any], dict[str, bytes], bytes]:
    """Проект КТ1: автор подписывает штампом, руководитель открепленной подписью замороженной аннотации."""
    project = await _create_project(client, tmp_path / "proj", lang=lang)
    pid = project["id"]
    sources = await _write_outputs(client, project, {"annotation", "topic_presentation"})
    await _enable_detached_slot(client, pid)
    resp = await client.post(
        f"/api/v1/projects/{pid}/signatures/slots/author/png", files={"file": ("sig.png", _PNG_1PX, "image/png")}
    )
    assert resp.status_code == 200, resp.text
    resp = await client.patch(f"/api/v1/projects/{pid}/signatures/placements/annotation/author", json={"enabled": True})
    assert resp.status_code == 200, resp.text
    await _freeze(client, pid)
    frozen = await _frozen_bytes(client, pid)
    if signature_format == "openpgp":
        # gpg в тестах не запускается: проверка подписи и экспорт ключа подменены.
        mocker.patch.object(
            GpgKeyring,
            "verify_detached",
            return_value=GpgVerification(
                status="good",
                fingerprint=_PGP_FINGERPRINT,
                key_id=_PGP_FINGERPRINT[-16:],
                signer="Иван Иванов",
                signed_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
            ),
        )
        mocker.patch.object(GpgKeyring, "get_key", return_value=None)
        mocker.patch.object(GpgKeyring, "export_public", return_value=_PGP_PUBLIC_KEY)
        signature = _PGP_SIGNATURE
    else:
        signature = make_detached_cms(make_identity("Петрова Анна Сергеевна"), frozen)
    attached = await _attach(client, pid, signature, "sig.bin")
    assert attached.status_code == 200, attached.text
    assert attached.json()["signature"]["verdict"] == "valid"
    return project, sources, frozen


@pytest.mark.parametrize(
    ("lang", "signature_format"),
    [("ru", "cms"), ("en", "openpgp")],
)
async def test__api__create_submission__frozen_detached_package_contents(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture, lang: str, signature_format: str
) -> None:
    project, sources, frozen = await _frozen_signed_project(
        test_app, tmp_path, mocker, lang=lang, signature_format=signature_format
    )

    record = await _create(test_app, project, _CHECKPOINT_1)

    files = _archive(record)
    pdf_name = "Аннотация.pdf" if lang == "ru" else "Annotation.pdf"
    top_name = "Презентация защиты темы.pdf" if lang == "ru" else "Topic defence presentation.pdf"
    readme = pdf_name.replace(".pdf", ".README.txt")
    # Подписанный документ уходит ровно теми байтами, что покрывает подпись (не штампом заново), и не равен исходнику.
    assert files[pdf_name] == frozen
    assert files[pdf_name] != sources["annotation"]
    assert files[top_name] == sources["topic_presentation"]
    assert _sha256(frozen) in files[readme].decode("utf-8")
    if signature_format == "cms":
        signature_files = [name for name in files if name.endswith(".p7s")]
        assert signature_files == ["Аннотация.Научный_руководитель.p7s"]
        assert not [name for name in files if name.startswith("public-key.")]
        assert "openssl cms -verify" in files[readme].decode("utf-8")
        assert set(files) == {pdf_name, top_name, readme, *signature_files}
    else:
        signature_files = [name for name in files if name.endswith(".asc") and not name.startswith("public-key.")]
        assert signature_files == ["Annotation.Supervisor.asc"]
        assert files["Annotation.Supervisor.asc"] == _PGP_SIGNATURE
        assert files["public-key.Иван_Иванов.asc"] == _PGP_PUBLIC_KEY
        assert "gpg --verify" in files[readme].decode("utf-8")
        assert set(files) == {pdf_name, top_name, readme, "Annotation.Supervisor.asc", "public-key.Иван_Иванов.asc"}


def _hse_files_with_bytes(folder: Path, data: bytes) -> list[Path]:
    return [p for p in (folder / ".hse-studio").rglob("*") if p.is_file() and p.read_bytes() == data]


@pytest.mark.parametrize(
    ("breakage", "detail"),
    [
        (
            "rebuilt",
            (
                "Аннотация.pdf: the document was rebuilt after the PDF was frozen for signing. "
                "Freeze it again and re-attach the signatures"
            ),
        ),
        ("signature_file_missing", "Signature file is missing for Аннотация.pdf, slot supervisor"),
        ("frozen_pdf_missing", "Frozen PDF is missing for Аннотация.pdf: freeze the document again"),
    ],
)
async def test__api__create_submission__frozen_rebuilt_400_and_pinned_litter(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture, breakage: str, detail: str
) -> None:
    project, _, frozen = await _frozen_signed_project(test_app, tmp_path, mocker, lang="ru", signature_format="cms")
    folder = Path(project["folder"])
    if breakage == "rebuilt":
        _make_pdf(folder / "annotation" / "annotation.pdf", "annotation, rebuilt")
    elif breakage == "signature_file_missing":
        (signature,) = list((folder / ".hse-studio").rglob("*.p7s"))
        signature.unlink()
    else:
        (frozen_file,) = _hse_files_with_bytes(folder, frozen)
        frozen_file.unlink()

    resp = await _submit(test_app, project, _CHECKPOINT_1)

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == detail
    # Ни архива, ни записи, ни строки в журнале.
    assert not list((folder / "submissions").glob("*.zip"))
    assert not list((folder / ".hse-studio" / "submissions").glob("*.json"))
    changelog = (await test_app.get(f"/api/v1/projects/{project['id']}/changelog")).json()
    assert not [entry for entry in changelog if entry["kind"] == "pack_submission"]
    # Сегодняшний мусор: ошибка летит уже после создания папки пакета, и в ней остаются документы, успевшие
    # скопироваться до сбоя (презентация идёт в профиле раньше аннотации, замороженная аннотация копируется
    # раньше проверки файла подписи). Сборка с предварительным планированием должна поднять ту же ошибку до
    # записи на диск; тогда этот тест сознательно меняется на "папки нет".
    leftovers = _folder_content(folder / "submissions")
    expected = ["Презентация защиты темы.pdf"]
    if breakage == "signature_file_missing":
        expected = ["Аннотация.pdf", *expected]
    assert len(leftovers) == len(expected)
    for name, leftover in zip(expected, leftovers, strict=True):
        assert re.fullmatch(rf"{_CHECKPOINT_1}-{_STAMP_RE}/{re.escape(name)}", leftover)
