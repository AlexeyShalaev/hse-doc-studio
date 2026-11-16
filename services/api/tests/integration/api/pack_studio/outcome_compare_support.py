"""Общее для тестов сравнений результата над HTTP (срез O7): настоящие версии и стартовые сценарии паков, черновики,
которые можно править, адреса и разбор ответов строгими моделями контракта."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hse_doc_studio.api.schemas.pack_studio_outcome import (
    PackOutcomeCompareResponse,
    PackOutcomeImpactResponse,
    PackOutcomeMatrixResponse,
)
from httpx import Response

from tests.integration.api.pack_studio.conftest import Stand
from tests.integration.api.pack_studio.outcome_support import (
    COURSEWORK,
    REAL_PACKS,
    VKR,
    copy_real_packs,
    outcome_url,
    real_files,
)

DRAFT = "2026.1.9"
DRAFT_COURSEWORK = (COURSEWORK[0], COURSEWORK[1], DRAFT)
DRAFT_COURSEWORK_MANIFEST = f"hse-cs-sse/templates/coursework/versions/{DRAFT}/version.yaml"
SLOT_BEFORE = "when: { person: supervisor, role: company }"
SLOT_AFTER = "when: { person: supervisor }"
DRAFT_ANNOTATION = f"hse-cs-se/templates/vkr/versions/{DRAFT}/files/shared_annotation/doc.yaml"
ANNOTATION_BEFORE = "supported_kinds:\n- research\n"
ANNOTATION_AFTER = "supported_kinds:\n- research\n- project\n"
TEMPLATES = (("hse-cs-se", "vkr"), ("hse-cs-sse", "coursework"))


def real_scenario_files(templates: tuple[tuple[str, str], ...] = TEMPLATES) -> dict[str, bytes]:
    """Стартовые сценарии паков: путь от папки паков -> содержимое."""
    found: dict[str, bytes] = {}
    for pack, template in templates:
        folder = REAL_PACKS / pack / "templates" / template / "scenarios"
        for path in sorted(folder.glob("*.yaml")):
            found[f"{pack}/templates/{template}/scenarios/{path.name}"] = path.read_bytes()
    return found


def draft_coursework_files() -> dict[str, bytes]:
    """Курсовой проект `hse-cs-sse` 2026.1.6 как черновик 2026.1.9 (без записи в реестре выпусков)."""
    files: dict[str, bytes] = {}
    for path, data in real_files((COURSEWORK,)).items():
        if path.endswith("/releases.yaml"):
            continue
        moved = path.replace("/versions/2026.1.6/", f"/versions/{DRAFT}/")
        if moved.endswith("/version.yaml"):
            data = data.replace(b'id: "2026.1.6"', f'id: "{DRAFT}"'.encode(), 1)
        files[moved] = data
    assert SLOT_BEFORE.encode() in files[DRAFT_COURSEWORK_MANIFEST]
    return files


async def folder_with_scenarios(stand: Stand, extra: Mapping[str, bytes] | None = None) -> tuple[str, Path]:
    """Пространство-папка с настоящими версиями ВКР и курсового проекта и стартовыми сценариями; возвращает id и
    папку паков."""
    await stand.enable()
    root = copy_real_packs(stand.root / "packs")
    for rel, data in {**real_scenario_files(), **(extra or {})}.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    ws = await stand.folder_workspace(root.parent, packs_path=root.name)
    return str(ws["id"]), root


async def edit_file(stand: Stand, ws: str, path: str, before: str, after: str) -> None:
    """Несохранённая правка файла через файлы Студии: заменяет текст `before` текстом `after`."""
    read = await stand.read(ws, path)
    assert read.status_code == 200, read.text
    text = read.content.decode("utf-8")
    assert before in text, (path, before)
    written = await stand.client.put(
        stand.file_url(ws, path),
        content=text.replace(before, after, 1).encode("utf-8"),
        headers={"If-Match": read.headers["ETag"]},
    )
    assert written.status_code == 200, written.text


async def post_op(
    stand: Stand, ws: str, ref: tuple[str, str, str], op: str, body: Mapping[str, Any] | None = None, **headers: str
) -> Response:
    return await stand.client.post(outcome_url(ws, ref, f"/{op}"), json=dict(body or {}), headers=headers)


def parse_compare(resp: Response) -> PackOutcomeCompareResponse:
    assert resp.status_code == 200, resp.text
    return PackOutcomeCompareResponse.model_validate(resp.json())


def parse_impact(resp: Response) -> PackOutcomeImpactResponse:
    assert resp.status_code == 200, resp.text
    return PackOutcomeImpactResponse.model_validate(resp.json())


def parse_matrix(resp: Response) -> PackOutcomeMatrixResponse:
    assert resp.status_code == 200, resp.text
    return PackOutcomeMatrixResponse.model_validate(resp.json())


__all__ = ["COURSEWORK", "VKR"]
