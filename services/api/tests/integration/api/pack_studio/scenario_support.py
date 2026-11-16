"""Общее для тестов сценариев (срез O6): адреса, тела запросов и разбор ответов строгими моделями контракта."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hse_doc_studio.api.schemas.pack_studio_outcome import (
    PackScenarioEntry,
    PackScenarioListResponse,
    PackScenarioRunResponse,
)
from httpx import Response

from tests.integration.api.pack_studio.conftest import API, Stand

VKR_TEMPLATE = ("hse-cs-se", "vkr")
COURSEWORK_TEMPLATE = ("hse-cs-sse", "coursework")


def scenarios_url(ws: str, template: tuple[str, str], tail: str = "") -> str:
    pack, name = template
    return f"{API}/workspaces/{ws}/templates/{pack}/{name}/scenarios{tail}"


def scenario_path(template: tuple[str, str], scenario_id: str) -> str:
    """Путь файла сценария от папки паков."""
    return f"{template[0]}/templates/{template[1]}/scenarios/{scenario_id}.yaml"


def scenario_body(name: str = "Сценарий", inputs: Mapping[str, str] | None = None, **extra: Any) -> dict[str, Any]:
    """Тело PUT: сценарий `format: 1` с русским названием; `extra` это поля сценария (`assertions`, `versions`...) и
    поля запроса (`record_snapshot`, `version`)."""
    request_keys = ("record_snapshot", "version")
    scenario: dict[str, Any] = {"format": 1, "name": {"ru": name}, "inputs": dict(inputs or {})}
    scenario.update({k: v for k, v in extra.items() if k not in request_keys})
    return {"scenario": scenario, **{k: v for k, v in extra.items() if k in request_keys}}


async def put_scenario(
    stand: Stand,
    ws: str,
    template: tuple[str, str],
    scenario_id: str,
    body: Mapping[str, Any],
    *,
    if_match: str | None = None,
) -> Response:
    headers = {"If-Match": if_match} if if_match is not None else {}
    return await stand.client.put(scenarios_url(ws, template, f"/{scenario_id}"), json=dict(body), headers=headers)


async def list_scenarios(stand: Stand, ws: str, template: tuple[str, str], state: str | None = None) -> Response:
    return await stand.client.get(scenarios_url(ws, template), params={"state": state} if state else None)


async def run_scenarios(
    stand: Stand, ws: str, template: tuple[str, str], body: Mapping[str, Any] | None = None, **headers: str
) -> Response:
    return await stand.client.post(scenarios_url(ws, template, "/run"), json=dict(body or {}), headers=headers)


def parse_entry(resp: Response) -> PackScenarioEntry:
    assert resp.status_code == 200, resp.text
    return PackScenarioEntry.model_validate(resp.json())


def parse_list(resp: Response) -> PackScenarioListResponse:
    assert resp.status_code == 200, resp.text
    return PackScenarioListResponse.model_validate(resp.json())


def parse_run(resp: Response) -> PackScenarioRunResponse:
    assert resp.status_code == 200, resp.text
    return PackScenarioRunResponse.model_validate(resp.json())


def tree_digest(root: Path) -> dict[str, str]:
    """Все файлы под папкой: путь -> хэш содержимого. Нужен, чтобы показать, что запрос ничего не записал."""
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
