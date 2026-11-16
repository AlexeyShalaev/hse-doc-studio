"""Общее для тестов эндпоинтов результата (срез O2): настоящие версии репозитория и запросы к ним."""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hse_doc_studio.api.schemas.pack_studio_outcome import PackOutcomeInputsResponse, PackOutcomeResponse
from httpx import Response

from tests.integration.api.pack_studio.conftest import API, Stand

_REPO = Path(__file__).resolve().parents[6]
REAL_PACKS = _REPO / "packs"
FIXTURES = _REPO / "contracts" / "pack-studio" / "fixtures"

VKR = ("hse-cs-se", "vkr", "2026.1.2")
COURSEWORK = ("hse-cs-sse", "coursework", "2026.1.6")
REAL_VERSIONS = (VKR, COURSEWORK)


def copy_real_packs(dest: Path, versions: tuple[tuple[str, str, str], ...] = REAL_VERSIONS) -> Path:
    """Папка паков с настоящими версиями репозитория (манифесты пака и шаблона, реестр, одна версия каждого шаблона)."""
    dest.mkdir(parents=True, exist_ok=True)
    for pack, template, version in versions:
        source = REAL_PACKS / pack
        shutil.copy(source / "pack.yaml", _mkdir(dest / pack) / "pack.yaml")
        tpl_src = source / "templates" / template
        tpl_dst = _mkdir(dest / pack / "templates" / template)
        for name in ("template.yaml", "releases.yaml"):
            if (tpl_src / name).is_file():
                shutil.copy(tpl_src / name, tpl_dst / name)
        if (tpl_src / "examples").is_dir():
            shutil.copytree(tpl_src / "examples", tpl_dst / "examples", dirs_exist_ok=True)
        shutil.copytree(tpl_src / "versions" / version, tpl_dst / "versions" / version, dirs_exist_ok=True)
    return dest


def real_files(versions: tuple[tuple[str, str, str], ...] = REAL_VERSIONS) -> dict[str, bytes]:
    """Те же файлы словарём (путь от папки паков -> содержимое), чтобы положить их в репозиторий."""
    import tempfile  # noqa: PLC0415 — нужен только здесь

    with tempfile.TemporaryDirectory() as tmp:
        root = copy_real_packs(Path(tmp), versions)
        return {path.relative_to(root).as_posix(): path.read_bytes() for path in root.rglob("*") if path.is_file()}


DRAFT = "2026.1.9"
DRAFT_VKR = ("hse-cs-se", "vkr", DRAFT)
DRAFT_MANIFEST = f"hse-cs-se/templates/vkr/versions/{DRAFT}/version.yaml"
LANGS = "langs: [ru, en]"


def draft_vkr_files() -> dict[str, bytes]:
    """ВКР как черновик `2026.1.9` (копия 2026.1.2 без записи в реестре выпусков): его можно править."""
    files: dict[str, bytes] = {}
    for path, data in real_files((VKR,)).items():
        if path.endswith("/releases.yaml"):
            continue
        moved = path.replace("/versions/2026.1.2/", f"/versions/{DRAFT}/")
        if moved.endswith("/version.yaml"):
            data = data.replace(b'id: "2026.1.2"', f'id: "{DRAFT}"'.encode(), 1)
        files[moved] = data
    assert LANGS.encode() in files[DRAFT_MANIFEST]
    return files


def _mkdir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def outcome_url(ws: str, ref: tuple[str, str, str], tail: str = "") -> str:
    pack, template, version = ref
    return f"{API}/workspaces/{ws}/versions/{pack}/{template}/{version}/outcome{tail}"


async def get_inputs(
    stand: Stand, ws: str, ref: tuple[str, str, str], state: str | None = None, **headers: str
) -> Response:
    params = {"state": state} if state else None
    return await stand.client.get(outcome_url(ws, ref, "/inputs"), params=params, headers=headers)


async def post_outcome(
    stand: Stand, ws: str, ref: tuple[str, str, str], body: Mapping[str, Any] | None = None, **headers: str
) -> Response:
    return await stand.client.post(outcome_url(ws, ref), json=dict(body or {}), headers=headers)


def parse_outcome(resp: Response) -> PackOutcomeResponse:
    """Ответ принимает строгая модель контракта: лишние и недостающие поля отвергаются."""
    assert resp.status_code == 200, resp.text
    return PackOutcomeResponse.model_validate(resp.json())


def parse_inputs(resp: Response) -> PackOutcomeInputsResponse:
    assert resp.status_code == 200, resp.text
    return PackOutcomeInputsResponse.model_validate(resp.json())


async def folder_with_real_packs(stand: Stand) -> str:
    """Пространство-папка с настоящими версиями ВКР и курсового проекта; возвращает id."""
    await stand.enable()
    root = copy_real_packs(stand.root / "packs")
    ws = await stand.folder_workspace(root.parent, packs_path=root.name)
    return str(ws["id"])


async def folder_with_draft(stand: Stand) -> tuple[str, Path]:
    """Пространство-папка с черновиком ВКР `2026.1.9`; возвращает id и папку паков."""
    await stand.enable()
    root = stand.root / "packs"
    for rel, data in draft_vkr_files().items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    ws = await stand.folder_workspace(root.parent, packs_path=root.name)
    return str(ws["id"]), root


async def edit_manifest(stand: Stand, ws: str, before: str, after: str) -> None:
    """Несохранённая правка манифеста черновика через файлы Студии: заменяет строку `before` строкой `after`."""
    read = await stand.read(ws, DRAFT_MANIFEST)
    assert read.status_code == 200, read.text
    text = read.content.decode("utf-8")
    assert before in text
    written = await stand.client.put(
        stand.file_url(ws, DRAFT_MANIFEST),
        content=text.replace(before, after, 1).encode("utf-8"),
        headers={"If-Match": read.headers["ETag"]},
    )
    assert written.status_code == 200, written.text
