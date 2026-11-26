"""Предпросмотр версии шаблона (template-studio.md, раздел 6, срез T7) в локальной Студии.

Настоящие роутер, DI, рендер в отдельном процессе и встроенный раннер; подменён только бинарник docker
(`tests/fixtures/fake_docker.py`): он кладёт PDF туда, куда положил бы latexmk.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.infra.compile.docker_image_manager import DockerImageManager, DockerStatus, ImageInfo
from pytest_mock import MockerFixture

from tests.fixtures.fake_docker import FakeDocker, install_fake_docker

from .conftest import API, PACK_FILES, TEMPLATE_DIR, Stand, write_pack

VERSION = "2026.1.1"
VERSION_DIR = f"{TEMPLATE_DIR}/versions/{VERSION}"

_DRAFT_YAML = """\
id: "2026.1.1"
status: beta
summary: { ru: "Черновик", en: "Draft" }
langs: [ru, en]
supported_staffing: [solo, team]
author_group_placeholder: "МСПИН261"
meta_fields:
  stage:
    type: select
    label: { ru: "Этап", en: "Stage" }
    options: ["Первый", "Второй"]
    required_at: create
  org:
    type: string
    label: { ru: "Организация", en: "Organisation" }
    placeholder: "ООО «Пример»"
    required_at: finalize
dynamic_includes:
  - { template: common/meta.tex.j2, output: common/meta.tex }
documents:
  - id: report
    name: { ru: "Отчёт", en: "Report" }
    source_file: report/report.tex
    output_file: report/report.pdf
  - id: memo
    name: { ru: "Записка", en: "Memo" }
    source_file: memo/memo.tex
    output_file: memo/memo.pdf
    supported_kinds: [project]
"""

PREVIEW_FILES: Mapping[str, str] = {
    **{k: v for k, v in PACK_FILES.items() if not k.startswith(VERSION_DIR)},
    f"{VERSION_DIR}/version.yaml": _DRAFT_YAML,
    f"{VERSION_DIR}/files/common/meta.tex.j2": (
        "% title={{ project.name | texesc }}\n% stage={{ project.meta.stage }}\n% author={{ author.name }}\n"
    ),
    f"{VERSION_DIR}/files/report/report.tex": (
        "\\documentclass{article}\n\\input{../common/meta}\n% {{ project.lang }}\n"
    ),
    f"{VERSION_DIR}/files/memo/memo.tex": "\\documentclass{article}\n",
    f"{TEMPLATE_DIR}/examples/team.yaml": (
        'label: { ru: "Команда", en: "Team" }\n'
        "staffing: team2\n"
        'name: { ru: "Тема из примера", en: "Example topic" }\n'
        "authors:\n"
        '  - { name: "Шалаев Алексей Дмитриевич", group: "МСПИН261" }\n'
        '  - { name: "Петров Пётр Петрович", group: "МСПИН261" }\n'
        'meta: { org: "ООО «Ромашка»" }\n'
    ),
    f"{TEMPLATE_DIR}/examples/broken.yaml": "authors: 5\n",
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


async def _workspace(stand: Stand) -> str:
    await stand.enable()
    root = write_pack(stand.root / "packs", PREVIEW_FILES)
    ws = await stand.folder_workspace(root.parent, packs_path=root.name)
    return str(ws["id"])


def _preview_url(ws: str) -> str:
    return f"{API}/workspaces/{ws}/versions/demo/report/{VERSION}/preview"


def _build_url(ws: str, build_id: str) -> str:
    return f"{API}/workspaces/{ws}/previews/{build_id}"


async def _start(stand: Stand, ws: str, body: dict[str, Any]) -> tuple[int, list[dict[str, Any]]]:
    resp = await stand.client.post(_preview_url(ws), json=body)
    assert resp.status_code in {200, 202}, resp.text
    return resp.status_code, list(resp.json()["builds"])


async def _settled(stand: Stand, ws: str, build_id: str, *, timeout_s: float = 60.0) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + timeout_s
    while True:
        resp = await stand.client.get(_build_url(ws, build_id))
        assert resp.status_code == 200, resp.text
        body = dict(resp.json())
        if body["status"] in {"succeeded", "failed", "cancelled"}:
            return body
        assert asyncio.get_running_loop().time() < deadline, body
        await asyncio.sleep(0.05)


async def test__options__lists_documents_switches_and_examples(stand: Stand) -> None:
    ws = await _workspace(stand)

    resp = await stand.client.get(_preview_url(ws))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [d["id"] for d in body["documents"]] == ["report", "memo"]
    switches = {s["id"]: s for s in body["switches"]}
    assert switches["lang"]["values"] == ["ru", "en"]
    assert switches["staffing"]["values"] == ["solo", "team2", "team3"]
    assert switches["meta.stage"]["values"] == ["Первый", "Второй"]
    assert switches["meta.stage"]["label"] == {"ru": "Этап", "en": "Stage"}
    examples = {e["id"]: e for e in body["examples"]}
    assert set(examples) == {"team", "broken", "auto:normal", "auto:long", "auto:empty"}
    assert examples["team"]["defaults"] == {"staffing": "team2"}
    assert examples["broken"]["error"]
    assert body["default_example"] == "team"
    assert body["combination"]["staffing"] == "team2"


async def test__preview__builds_pdf_then_serves_cache(stand: Stand, fake_docker: FakeDocker) -> None:
    ws = await _workspace(stand)
    body = {"documents": ["report"], "example": "auto:normal", "combination": {"meta.stage": "Второй"}}

    status, builds = await _start(stand, ws, body)
    done = await _settled(stand, ws, builds[0]["id"])

    assert status == 202
    assert done["status"] == "succeeded", done["error"]
    assert done["cached"] is False
    assert done["source_file"] == "report/report.tex"
    assert done["combination"]["meta.stage"] == "Второй"
    pdf = await stand.client.get(_build_url(ws, done["id"]) + "/pdf")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    log = await stand.client.get(_build_url(ws, done["id"]) + "/log")
    assert "fake latexmk" in log.text
    assert "[render]" not in log.text
    assert len(fake_docker.build_calls()) == 1

    again_status, again = await _start(stand, ws, body)

    assert again_status == 200
    assert again[0]["status"] == "succeeded"
    assert again[0]["cached"] is True
    assert again[0]["key"] == done["key"]
    assert len(fake_docker.build_calls()) == 1


async def test__preview__other_document_edit_keeps_key_own_edit_changes_it(
    stand: Stand, fake_docker: FakeDocker
) -> None:
    ws = await _workspace(stand)
    body = {"documents": ["report"], "example": "auto:normal"}
    _, first = await _start(stand, ws, body)
    await _settled(stand, ws, first[0]["id"])

    other = await stand.client.put(stand.file_url(ws, f"{VERSION_DIR}/files/memo/memo.tex"), content=b"% edited\n")
    assert other.status_code == 200, other.text
    _, after_other = await _start(stand, ws, body)
    own = await stand.client.put(stand.file_url(ws, f"{VERSION_DIR}/files/report/report.tex"), content=b"% edited\n")
    assert own.status_code == 200, own.text
    _, after_own = await _start(stand, ws, body)

    assert after_other[0]["key"] == first[0]["key"]
    assert after_other[0]["cached"] is True
    assert after_own[0]["key"] != first[0]["key"]
    assert after_own[0]["cached"] is False
    await _settled(stand, ws, after_own[0]["id"])


async def test__preview__team_example_renders_personal_base(stand: Stand, fake_docker: FakeDocker) -> None:
    ws = await _workspace(stand)

    _, builds = await _start(stand, ws, {"documents": ["report"], "example": "team"})
    done = await _settled(stand, ws, builds[0]["id"])

    assert done["status"] == "succeeded", done["error"]
    assert done["combination"]["staffing"] == "team2"


async def test__preview__team_author__builds_the_personal_document_of_the_chosen_author(
    stand: Stand, fake_docker: FakeDocker
) -> None:
    await stand.enable()
    personal = _DRAFT_YAML.replace(
        "output_file: report/report.pdf\n", "output_file: report/report.pdf\n    scope: personal\n"
    )
    root = write_pack(stand.root / "packs", {**PREVIEW_FILES, f"{VERSION_DIR}/version.yaml": personal})
    ws = str((await stand.folder_workspace(root.parent, packs_path=root.name))["id"])
    team = {"documents": ["report"], "example": "auto:normal", "combination": {"staffing": "team2"}}

    _, [default] = await _start(stand, ws, team)
    first = await _settled(stand, ws, default["id"])
    _, [chosen] = await _start(stand, ws, {**team, "author": "2"})
    second = await _settled(stand, ws, chosen["id"])
    outside = await stand.client.post(_preview_url(ws), json={**team, "author": "3"})

    # Без выбора автора собирается документ первого автора, как раньше.
    assert first["status"] == "succeeded", first["error"]
    assert (first["author"], first["source_file"]) == ("ivanov", "ivanov/report/report.tex")
    assert second["status"] == "succeeded", second["error"]
    assert (second["author"], second["source_file"]) == ("petrova", "petrova/report/report.tex")
    assert second["key"] != first["key"]
    assert second["authors"] == [
        {"slug": "ivanov", "name": "Иванов Иван Иванович"},
        {"slug": "petrova", "name": "Петрова Мария Сергеевна"},
    ]
    assert outside.status_code == 400, outside.text
    assert (outside.json()["code"], outside.json()["field"]) == ("preview_invalid", "author")
    assert outside.json()["reason"] == "the combination has authors 1..2"


async def test__preview__invalid_requests_are_rejected(stand: Stand) -> None:
    ws = await _workspace(stand)
    url = _preview_url(ws)

    unknown_doc = await stand.client.post(url, json={"documents": ["nope"]})
    absent_doc = await stand.client.post(url, json={"documents": ["memo"], "combination": {"kind": "research"}})
    bad_value = await stand.client.post(url, json={"documents": ["report"], "combination": {"lang": "de"}})
    broken = await stand.client.post(url, json={"documents": ["report"], "example": "broken"})

    assert unknown_doc.status_code == 400
    assert unknown_doc.json()["code"] == "preview_invalid"
    assert unknown_doc.json()["field"] == "document"
    assert absent_doc.json()["reason"] == "not in this combination"
    assert bad_value.json()["field"] == "combination.lang"
    assert broken.json()["field"] == "example"


async def test__preview__render_failure_is_a_failed_build(stand: Stand, fake_docker: FakeDocker) -> None:
    ws = await _workspace(stand)
    gone = await stand.client.delete(stand.file_url(ws, f"{VERSION_DIR}/files/report/report.tex"))
    assert gone.status_code == 204

    _, builds = await _start(stand, ws, {"documents": ["report"], "example": "auto:normal"})
    done = await _settled(stand, ws, builds[0]["id"])

    assert done["status"] == "failed"
    assert done["error"]["code"] == "render_failed"
    assert fake_docker.build_calls() == []
    pdf = await stand.client.get(_build_url(ws, done["id"]) + "/pdf")
    assert pdf.status_code == 409
    assert pdf.json()["code"] == "preview_not_ready"


async def test__preview__image_missing_fails_the_build(stand: Stand, mocker: MockerFixture) -> None:
    mocker.patch.object(
        DockerImageManager, "docker_status", return_value=DockerStatus(available=True, version="fake", detail=None)
    )
    mocker.patch.object(DockerImageManager, "inspect", return_value=None)
    ws = await _workspace(stand)

    _, builds = await _start(stand, ws, {"documents": ["report"], "example": "auto:normal"})
    done = await _settled(stand, ws, builds[0]["id"])

    assert done["status"] == "failed"
    assert done["error"]["code"] == "image_missing"


async def test__preview__unknown_build_is_not_found(stand: Stand) -> None:
    ws = await _workspace(stand)

    resp = await stand.client.get(_build_url(ws, "00000000-0000-4000-8000-000000000000"))

    assert resp.status_code == 404
    assert resp.json()["code"] == "preview_not_found"
