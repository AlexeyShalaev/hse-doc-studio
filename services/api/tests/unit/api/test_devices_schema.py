"""Контракт сигнала присутствия: строгий вход и очистка в метаданные состояния (раздел 4 дизайн-заметки)."""

from __future__ import annotations

import json

import pytest
from hse_doc_studio.api.schemas.devices import HeartbeatRequest
from pydantic import ValidationError

DEVICE = "a" * 32
PROJECT = "11111111-1111-1111-1111-111111111111"


def body(**changes: object) -> dict[str, object]:
    base: dict[str, object] = {"device_id": DEVICE, "name": "MacBook Алексея", "version": "0.6.0", "os": "macos"}
    return {**base, **changes}


def parse(**changes: object) -> HeartbeatRequest:
    return HeartbeatRequest.model_validate_json(json.dumps(body(**changes)))


def test__heartbeat__minimal_report_is_accepted() -> None:
    report = parse().to_report()

    assert (report.device_id, report.name, report.os.value, report.activity.value) == (
        DEVICE,
        "MacBook Алексея",
        "macos",
        "idle",
    )
    assert report.projects == ()
    assert report.endpoints == ()


@pytest.mark.parametrize("device_id", ["", "A" * 32, "a" * 31, "g" * 32, "../etc/passwd" + "a" * 19])
def test__heartbeat__device_id_must_be_32_lowercase_hex(device_id: str) -> None:
    with pytest.raises(ValidationError):
        parse(device_id=device_id)


def test__heartbeat__unknown_fields_are_rejected_so_nothing_extra_can_ride_along() -> None:
    with pytest.raises(ValidationError):
        parse(home_dir="/Users/alex")
    with pytest.raises(ValidationError):
        parse(projects=[{"project_id": PROJECT, "sync": "synced", "path": "/Users/alex/p"}])


def test__heartbeat__path_like_device_name_is_replaced_not_stored() -> None:
    assert parse(name="/Users/alex/work").to_report().name == "Studio"
    assert parse(name="C:\\Users\\alex").to_report().name == "Studio"


def test__heartbeat__control_characters_are_stripped_from_name_and_models() -> None:
    report = parse(
        name="Mac\x00Book\x1b",
        endpoints=[
            {"name": "ollama", "flavor": "ollama", "reachable": True, "models": ["qwen3:4b\x07", "/Users/a/m.gguf"]}
        ],
    ).to_report()

    assert report.name == "MacBook"
    assert report.endpoints[0].models == ("qwen3:4b",)


def test__heartbeat__bad_project_ids_and_endpoint_names_are_dropped_without_failing_the_signal() -> None:
    report = parse(
        projects=[
            {"project_id": "x" * 36, "sync": "synced"},
            {"project_id": PROJECT, "sync": "ahead", "ahead": 2},
        ],
        endpoints=[{"name": "../x", "flavor": "ollama"}, {"name": "ollama", "flavor": "openai"}],
    ).to_report()

    assert [(p.project_id.hex[:4], p.sync.value, p.ahead) for p in report.projects] == [("1111", "ahead", 2)]
    assert [e.name for e in report.endpoints] == ["ollama"]


def test__heartbeat__lists_have_size_limits() -> None:
    with pytest.raises(ValidationError):
        parse(projects=[{"project_id": PROJECT, "sync": "synced"}] * 101)
    with pytest.raises(ValidationError):
        parse(endpoints=[{"name": "ollama", "flavor": "ollama"}] * 9)


def test__heartbeat__pdf_doc_id_with_path_fragments_is_dropped() -> None:
    report = parse(
        projects=[
            {
                "project_id": PROJECT,
                "sync": "synced",
                "pdf": {"doc_id": "../../x", "at": "2026-11-03T12:00:00Z", "ok": True, "code": "/etc"},
            }
        ]
    ).to_report()

    assert report.projects[0].pdf is None


def test__heartbeat__runner_id_claim_must_look_like_an_id() -> None:
    ok = parse(runner={"runner_id": "5f9f8fde104348e29d9b17298d93152c", "state": "online"}).to_report()
    odd = parse(runner={"runner_id": "../x", "state": "On line"}).to_report()

    assert ok.runner is not None
    assert ok.runner.runner_id == "5f9f8fde104348e29d9b17298d93152c"
    assert odd.runner is not None
    assert (odd.runner.runner_id, odd.runner.state) == (None, None)
