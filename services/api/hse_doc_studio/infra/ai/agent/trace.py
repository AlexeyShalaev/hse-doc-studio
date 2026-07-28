from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import structlog

logger = structlog.get_logger()

# The provider runs inside the same asyncio task as the loop, so a contextvar set
# by the loop is visible to `run_turn` without threading a tracer through the
# IAgentProvider protocol. None when tracing is off (the common case).
_current: ContextVar["AgentTracer | None"] = ContextVar("agent_tracer", default=None)


def current_tracer() -> "AgentTracer | None":
    return _current.get()


def trace(kind: str, **payload: Any) -> None:
    """Module-level convenience: write to the active tracer if one is installed.

    A no-op when tracing is off, so call sites stay one cheap line with no guard.
    """
    tracer = _current.get()
    if tracer is not None:
        tracer.write(kind, **payload)


class AgentTracer:
    """Append-only JSONL trace of one agent run.

    Records the exact request handed to the model, every raw streaming chunk, the
    parsed turn and each tool dispatch — the full picture for debugging why a
    (often weak, local) model did or didn't call a tool. Opt-in via
    ``settings.agent.debug_trace``; writes are best-effort and never raise into
    the run. One file per run so a single trace can be handed over for analysis.
    """

    def __init__(self, path: Path, run_id: UUID) -> None:
        self._path = path
        self._run_id = str(run_id)
        self._seq = 0

    @property
    def path(self) -> Path:
        return self._path

    def write(self, kind: str, **payload: Any) -> None:
        self._seq += 1
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "seq": self._seq,
            "run_id": self._run_id,
            "kind": kind,
            **payload,
        }
        try:
            line = json.dumps(record, ensure_ascii=False, default=_json_default)
        except (TypeError, ValueError):
            # Last resort: never let an unserializable payload break the run.
            line = json.dumps({"ts": record["ts"], "seq": record["seq"], "kind": kind, "error": "unserializable"})
        try:
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        except OSError as exc:
            logger.warning("agent trace write failed", error_type=type(exc).__name__, path=str(self._path))


def _json_default(value: Any) -> str:
    return str(value)


def open_tracer(base_dir: Path, run_id: UUID, *, enabled: bool, keep: int = 0) -> AgentTracer | None:
    """Create a tracer for this run, or None when tracing is disabled/unavailable.

    Failures to create the directory/file degrade to None (tracing off) rather
    than disturbing the run.
    """
    if not enabled:
        return None
    try:
        base_dir.mkdir(parents=True, exist_ok=True)
        if keep > 0:
            _prune(base_dir, keep)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        path = base_dir / f"{stamp}-{run_id}.jsonl"
    except OSError as exc:
        logger.warning("agent trace open failed", error_type=type(exc).__name__, base_dir=str(base_dir))
        return None
    logger.info("agent debug trace enabled", run_id=str(run_id), path=str(path))
    return AgentTracer(path, run_id)


def _prune(base_dir: Path, keep: int) -> None:
    # Keep only the newest `keep` traces so the directory can't grow unbounded.
    try:
        traces = sorted(base_dir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return
    for stale in traces[: max(0, len(traces) - keep + 1)]:
        try:
            stale.unlink()
        except OSError:
            continue


@contextmanager
def install_tracer(tracer: AgentTracer | None) -> Iterator[AgentTracer | None]:
    """Make `tracer` the active one for the duration of the block (loop + nested
    provider calls). A None tracer installs nothing, so callers need no branch."""
    if tracer is None:
        yield None
        return
    token = _current.set(tracer)
    try:
        yield tracer
    finally:
        _current.reset(token)
