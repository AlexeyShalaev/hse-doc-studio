"""Проверки и правила формой и прогон проверок на предпросмотре (template-studio.md, 5.7, срез T14).

Настоящие роутер, DI, запись файлов, рендер в отдельном процессе и встроенный раннер; подменён только бинарник
docker (`tests/fixtures/fake_docker.py`), как в `test_preview.py`. Проверки после сборки гоняет тот же раннер,
что у проекта.
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
from .test_preview import _settled

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

# Проверки версии.
checks_version:
  disabled_categories: []
  disabled: []
  severity_override: {{}}
"""

_CHECKS = """\
# Демо-правила.
label: { ru: "Демо", en: "Demo" }
ref: { ru: "Демо §1", en: "Demo §1" }

rules:
  # Введение обязательно.
  - id: demo/intro
    title:       { ru: Введение, en: Introduction }
    category:    structure
    applies_to:  [report]
    default_severity: err
    engine: regex
    params:
      file_glob: "report/report.tex"
      pattern: 'Введение'
      message: { ru: "Нет введения", en: "No introduction" }

  - id: demo/todo
    title:       { ru: Нет TODO, en: No TODO }
    category:    typography
    applies_to:  "*"
    default_severity: warn
    engine: regex
    params:
      file_glob: "report/report.tex"
      pattern: 'TODO'
      negate: true
"""

FILES: Mapping[str, str] = {
    **{k: v for k, v in PACK_FILES.items() if not k.endswith("version.yaml") and "/files/" not in k},
    f"{RELEASED_DIR}/version.yaml": _VERSION.format(version=RELEASED, status="stable"),
    f"{RELEASED_DIR}/files/report/report.tex": "\\documentclass{article}\n",
    f"{RELEASED_DIR}/checks/demo.yaml": _CHECKS,
    f"{DRAFT_DIR}/version.yaml": _VERSION.format(version=DRAFT, status="beta"),
    f"{DRAFT_DIR}/files/report/report.tex": "\\documentclass{article}\n% TODO\n",
    f"{DRAFT_DIR}/checks/demo.yaml": _CHECKS,
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
    return f"{API}/workspaces/{ws}/versions/demo/report/{version}/checks"


def _file(body: dict[str, Any]) -> dict[str, Any]:
    return next(f for f in body["files"] if f["name"] == "demo.yaml")


async def test__get__files_rules_and_config(stand: Stand) -> None:
    ws, _ = await _workspace(stand)

    resp = await stand.client.get(_url(ws))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["documents"] == ["report"]
    demo = _file(body)
    assert demo["path"] == f"{DRAFT_DIR}/checks/demo.yaml"
    assert demo["header"]["label"] == {"ru": "Демо", "en": "Demo"}
    assert [r["entry"]["id"] for r in demo["rules"]] == ["demo/intro", "demo/todo"]
    assert demo["rules"][1]["entry"]["applies_to"] is None
    assert body["config"]["path"] == f"{DRAFT_DIR}/version.yaml"
    assert "page_geometry" in body["structural_checks"]


async def test__patch__rule_written_with_if_match_and_comments_kept(stand: Stand) -> None:
    ws, root = await _workspace(stand)
    demo = _file((await stand.client.get(_url(ws))).json())
    rule = {**demo["rules"][0]["entry"], "default_severity": "warn"}
    body = {"ops": [{"op": "set_rule", "index": 0, "rule": rule, "params_yaml": "file_glob: report/report.tex\n"}]}

    resp = await stand.client.patch(f"{_url(ws)}/files/demo.yaml", json=body, headers={"If-Match": demo["etag"]})

    assert resp.status_code == 200, resp.text
    entry = _file(resp.json())["rules"][0]["entry"]
    assert entry["default_severity"] == "warn"
    assert entry["params"] == {"file_glob": "report/report.tex"}
    text = (root / DRAFT_DIR / "checks/demo.yaml").read_text(encoding="utf-8")
    assert "  # Введение обязательно.\n" in text
    assert '      file_glob: "report/report.tex"\n' in text

    stale = await stand.client.patch(f"{_url(ws)}/files/demo.yaml", json=body, headers={"If-Match": demo["etag"]})

    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_file"


async def test__patch__rule_the_loader_drops_is_checks_invalid(stand: Stand) -> None:
    ws, root = await _workspace(stand)
    before = (root / DRAFT_DIR / "checks/demo.yaml").read_text(encoding="utf-8")
    rule = _file((await stand.client.get(_url(ws))).json())["rules"][0]["entry"]

    bad_yaml = await stand.client.patch(
        f"{_url(ws)}/files/demo.yaml",
        json={"ops": [{"op": "set_rule", "index": 0, "rule": rule, "params_yaml": "- a"}]},
    )
    bad_engine = await stand.client.patch(
        f"{_url(ws)}/files/demo.yaml",
        json={"ops": [{"op": "set_rule", "index": 0, "rule": {**rule, "engine": "magic"}}]},
    )

    assert bad_yaml.status_code == 400
    assert bad_yaml.json()["code"] == "checks_invalid"
    assert bad_engine.status_code == 400
    assert "engine" in bad_engine.json()["reason"]
    assert (root / DRAFT_DIR / "checks/demo.yaml").read_text(encoding="utf-8") == before


async def test__put_config__checks_version_and_released_is_read_only(stand: Stand) -> None:
    ws, root = await _workspace(stand)
    body = {"disabled_categories": ["typography"], "disabled": [], "severity_override": {"demo/intro": "info"}}

    resp = await stand.client.put(f"{_url(ws)}/config", json=body)
    released = await stand.client.put(f"{_url(ws, RELEASED)}/config", json=body)
    bad_name = await stand.client.patch(
        f"{_url(ws)}/files/..%2Fversion.yaml", json={"ops": [{"op": "remove_rule", "index": 0}]}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["config"]["disabled_categories"] == ["typography"]
    text = (root / DRAFT_DIR / "version.yaml").read_text(encoding="utf-8")
    assert "# Проверки версии.\n" in text
    assert yaml.safe_load(text)["checks_version"]["severity_override"] == {"demo/intro": "info"}
    assert released.status_code == 409
    assert released.json()["code"] == "version_released"
    assert bad_name.status_code in {400, 404}


async def test__preview__checks_run_on_the_build_and_come_with_it(stand: Stand, fake_docker: FakeDocker) -> None:
    ws, _ = await _workspace(stand)
    url = f"{API}/workspaces/{ws}/versions/demo/report/{DRAFT}/preview"

    plain = await stand.client.post(url, json={"documents": ["report"], "example": "auto:normal"})
    checked = await stand.client.post(url, json={"documents": ["report"], "example": "auto:normal", "checks": True})

    assert plain.status_code in {200, 202}, plain.text
    assert checked.status_code in {200, 202}, checked.text
    first = plain.json()["builds"][0]
    second = checked.json()["builds"][0]
    assert first["key"] != second["key"]
    done = await _settled(stand, ws, second["id"])
    assert done["status"] == "succeeded", done["error"]
    assert done["with_checks"] is True
    found = {c["rule_id"]: c for c in done["checks"]}
    assert set(found) == {"demo/intro", "demo/todo"}
    assert found["demo/intro"]["severity"] == "err"
    assert found["demo/todo"]["line"] == 2
    plain_done = await _settled(stand, ws, first["id"])
    assert plain_done["checks"] is None

    again = await stand.client.post(url, json={"documents": ["report"], "example": "auto:normal", "checks": True})

    cached = again.json()["builds"][0]
    assert cached["cached"] is True
    assert {c["rule_id"] for c in cached["checks"]} == {"demo/intro", "demo/todo"}
