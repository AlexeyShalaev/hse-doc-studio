from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.infra.ai.agent.trace import (
    current_tracer,
    install_tracer,
    open_tracer,
    trace,
)


@pytest.mark.unit
def test__open_tracer__disabled_returns_none(tmp_path: Path) -> None:
    assert open_tracer(tmp_path / "traces", uuid4(), enabled=False) is None


@pytest.mark.unit
def test__tracer__writes_jsonl_records(tmp_path: Path) -> None:
    run_id = uuid4()
    tracer = open_tracer(tmp_path / "traces", run_id, enabled=True)
    assert tracer is not None

    tracer.write("loop_start", model="qwen2.5")
    tracer.write("openai_turn", tool_calls=[{"name": "set_theme"}], text="")

    lines = tracer.path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["kind"] == "loop_start"
    assert first["model"] == "qwen2.5"
    assert first["seq"] == 1
    assert first["run_id"] == str(run_id)
    assert json.loads(lines[1])["kind"] == "openai_turn"


@pytest.mark.unit
def test__install_tracer__routes_module_level_trace(tmp_path: Path) -> None:
    tracer = open_tracer(tmp_path / "traces", uuid4(), enabled=True)
    assert tracer is not None

    trace("before", note="no tracer installed")  # no-op: nothing installed yet
    assert current_tracer() is None

    with install_tracer(tracer):
        assert current_tracer() is tracer
        trace("inside", note="installed")

    assert current_tracer() is None
    lines = tracer.path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["kind"] == "inside"


@pytest.mark.unit
def test__install_tracer__none_is_noop() -> None:
    with install_tracer(None) as active:
        assert active is None
        assert current_tracer() is None


@pytest.mark.unit
def test__open_tracer__prunes_to_keep_limit(tmp_path: Path) -> None:
    base = tmp_path / "traces"
    # Files are created lazily on first write, so write to each. keep=2 → after
    # the 3rd is opened, at most 2 trace files remain on disk.
    for _ in range(3):
        tracer = open_tracer(base, uuid4(), enabled=True, keep=2)
        assert tracer is not None
        tracer.write("loop_start")
    remaining = list(base.glob("*.jsonl"))
    assert len(remaining) <= 2


@pytest.mark.unit
def test__tracer__never_raises_on_unserializable_payload(tmp_path: Path) -> None:
    tracer = open_tracer(tmp_path / "traces", uuid4(), enabled=True)
    assert tracer is not None

    class _Weird:
        pass

    # default=str makes this serializable; an object that can't even str() is rare,
    # but the write path must not propagate the error either way.
    tracer.write("odd", value=_Weird())
    assert tracer.path.exists()
