"""Пределы того, что раннер пишет о себе: регистрироваться может любой человек, запись читают списки и маршрут."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.api.schemas.runner import RunnerAnnounceRequestBody, RunnerRegisterRequestBody
from pydantic import ValidationError

_FIXTURES = Path(__file__).resolve().parents[5] / "contracts" / "runner" / "fixtures"


def _announce(**changes: Any) -> dict[str, Any]:
    body = json.loads((_FIXTURES / "RunnerAnnounceRequestBody" / "desktop.json").read_text(encoding="utf-8"))
    return {**body, **changes}


def _register(**changes: Any) -> dict[str, Any]:
    body = {
        "name": "ci",
        "protocol": 1,
        "version": "0.3.0",
        "tags": ["tex", "archive:7z", "GPU"],
        "concurrency": 2,
        "resource_class": "standard",
    }
    return {**body, **changes}


@pytest.mark.parametrize(
    "changes",
    [
        {"version": "v" * 65},
        {"tags": [f"t{i}" for i in range(33)]},
        {"tags": ["x" * 33]},
        {"tags": ["<script>"]},
        {"tags": [" tex"]},
        {"concurrency": 65},
        {"ai_concurrency": 17},
        {"features": ["f"] * 17},
        {"features": ["f" * 33]},
    ],
)
def test__announce__out_of_bounds__rejected(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RunnerAnnounceRequestBody.model_validate(_announce(**changes))


@pytest.mark.parametrize(
    "changes",
    [{"version": "v" * 65}, {"tags": ["a b"]}, {"concurrency": 1000}, {"resource_class": "r" * 33}],
)
def test__register__out_of_bounds__rejected(changes: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        RunnerRegisterRequestBody.model_validate(_register(**changes))


def test__bounds__existing_runner_shapes_still_pass() -> None:
    """Старые раннеры не ломаются: `archive:*`, заглавные теги из окружения, предельные значения."""
    RunnerRegisterRequestBody.model_validate(_register(concurrency=64, tags=[f"t{i}" for i in range(32)]))
    RunnerAnnounceRequestBody.model_validate(_announce(concurrency=64, ai_concurrency=16, version="v" * 64))
