"""Канал команд раннера: `RunnerControlLoop` внутри `RunnerLoop` на фейковом сервере (storage-cleanup.md, 6.2, 6.3).

Диск настоящий (`RunnerDiskService`) на фейковом Docker из тестов сервиса диска: шаги можно придержать.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.jobs.disk import RunnerCommandState
from hse_doc_studio.infra.runner.backoff import Backoff
from hse_doc_studio.infra.runner.client import RunnerClient
from hse_doc_studio.infra.runner.control import BUSY_ERROR, ControlLoopConfig, RunnerControlLoop
from hse_doc_studio.infra.runner.loop import RunnerLoop, RunnerLoopConfig

from tests.unit.infra.runner.fake_runner_api import (
    TOKEN,
    FakeRunnerState,
    SwitchTransport,
    create_fake_app,
    envelope_body,
)
from tests.unit.infra.runner.test_runner_disk import _docker, _Probe, _service, _System, _usage
from tests.unit.infra.runner.test_runner_loop import JOB_A, FakeExecutor, until

CMD_A = "7d3f1a2b-4c5d-4e6f-8a9b-0c1d2e3f4a5b"
CMD_B = "8e4f2b3c-5d6e-4f70-9b0c-1d2e3f4a5b6c"


def _command(command_id: str, kind: str = "disk.cleanup", targets: tuple[str, ...] = ()) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if kind == "disk.cleanup":
        payload = {"targets": list(targets or ("build_cache", "dangling_images")), "include_rollback": False}
    return {"id": command_id, "kind": kind, "payload": payload, "issued_at": "2026-11-11T09:31:00+00:00"}


class Rig:
    def __init__(  # noqa: PLR0913
        self,
        tmp_path: Path,
        *,
        control: bool = True,
        report_every_s: float = 3600.0,
        stop_timeout_s: float = 2.0,
        keepalive_s: float = 60.0,
    ) -> None:
        self.state = FakeRunnerState()
        self.transport = SwitchTransport(create_fake_app(self.state))
        self.system = _System()
        self.disk = _service(tmp_path, _docker(_Probe(_usage()), self.system))
        self.executor = FakeExecutor()
        self.client = RunnerClient(
            "http://api",
            TOKEN,
            version="0.3",
            transport=self.transport,
            retries=1,
            backoff_factory=lambda: Backoff(base_s=0.001, cap_s=0.005),
        )
        fast = lambda: Backoff(base_s=0.01, cap_s=0.05, jitter=0.0)  # noqa: E731
        self.control = RunnerControlLoop(
            self.client,
            self.disk,
            ControlLoopConfig(
                wait_s=0,
                min_poll_interval_s=0.01,
                progress_interval_s=0.01,
                progress_keepalive_s=keepalive_s,
                report_every_s=report_every_s,
                report_retry_s=3600.0,
                stop_timeout_s=stop_timeout_s,
                backoff_factory=fast,
            ),
        )
        self.loop = RunnerLoop(
            self.client,
            self.executor,
            RunnerLoopConfig(
                name="r",
                version="0.3",
                poll_wait_s=0,
                log_flush_s=0.02,
                heartbeat_s=0.02,
                drain_timeout_s=2.0,
                backoff_factory=fast,
            ),
            control=self.control if control else None,
        )
        self.task: asyncio.Task[None] | None = None

    def start(self) -> None:
        self.task = asyncio.create_task(self.loop.run())

    async def stop(self) -> None:
        self.loop.request_stop()
        assert self.task is not None
        await asyncio.wait_for(self.task, 10)
        await self.client.aclose()

    def states(self, command_id: str) -> list[str]:
        return [entry["state"] for entry in self.state.progress.get(command_id, [])]

    def final(self, command_id: str) -> dict[str, Any]:
        return self.state.progress[command_id][-1]

    def finished(self, command_id: str) -> bool:
        return any(state != "running" for state in self.states(command_id))


async def test__old_server__no_channel_no_disk_report_and_nothing_in_the_log(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    rig = Rig(tmp_path)
    rig.state.server_features -= {"control", "disk"}
    caplog.set_level(logging.DEBUG, logger="hse_doc_studio.infra.runner.control")
    rig.start()
    await until(lambda: rig.state.polls > 2)
    await rig.stop()

    assert {"control", "disk"} <= set(rig.state.announces[0]["features"])
    assert not {"control", "disk"} & rig.client.features
    assert rig.state.control_polls == 0
    assert rig.state.disks == []
    assert [r for r in caplog.records if r.name == "hse_doc_studio.infra.runner.control"] == []


async def test__server_without_announce__no_channel(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.state.supports_announce = False
    rig.start()
    await until(lambda: rig.state.polls > 2)
    await rig.stop()

    assert rig.state.control_polls == 0
    assert rig.state.disks == []


async def test__runner_without_control__does_not_declare_it(tmp_path: Path) -> None:
    rig = Rig(tmp_path, control=False)
    rig.start()
    await until(lambda: rig.state.polls > 0)
    await rig.stop()

    assert not {"control", "disk"} & set(rig.state.announces[0]["features"])
    assert rig.state.control_polls == 0


async def test__new_server__disk_report_after_announce_and_commands_polled(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.start()
    await until(lambda: rig.state.disks and rig.state.control_polls > 1)
    await rig.stop()

    assert {"control", "disk"} <= rig.client.features
    (report,) = rig.state.disks
    assert report["docker_reason"] is None
    assert report["docker"]["available"] is True
    assert len(report["targets"]) == 6


async def test__long_command_poll__does_not_hold_jobs(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.state.hold_control_s = 5.0
    job = rig.state.enqueue(envelope_body("compile", job_id=JOB_A))
    started = asyncio.get_running_loop().time()
    rig.start()
    await until(lambda: job.completed)
    assert asyncio.get_running_loop().time() - started < 2.0
    await until(lambda: rig.state.control_polls > 0)
    await rig.stop()


async def test__measure_command__fresh_report_then_done_without_steps(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.start()
    await until(lambda: len(rig.state.disks) == 1)
    rig.state.commands.append(_command(CMD_A, "disk.measure"))
    await until(lambda: rig.finished(CMD_A))
    await rig.stop()

    assert len(rig.state.disks) == 2
    assert rig.state.progress[CMD_A] == [{"state": "done", "progress": {"steps": [], "freed_bytes": 0, "error": None}}]
    events = rig.state.events
    assert events.index("progress:done") > len(events) - 1 - events[::-1].index("disk")


async def test__cleanup_command__progress_final_and_a_new_report(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.start()
    await until(lambda: len(rig.state.disks) == 1)
    rig.state.commands.append(_command(CMD_A))
    await until(lambda: rig.finished(CMD_A) and len(rig.state.disks) == 2)
    await rig.stop()

    states = rig.states(CMD_A)
    assert states[-1] == "done"
    assert set(states[:-1]) <= {"running"}
    final = rig.final(CMD_A)["progress"]
    assert final["freed_bytes"] == 70
    assert [step["status"] for step in final["steps"]] == ["done", "done"]
    assert rig.system.calls == ["build_cache", "dangling_images"]


async def test__cleanup__cancel_in_the_progress_reply_stops_after_the_current_step(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.system.gate = asyncio.Event()
    rig.state.cancel_commands.add(CMD_A)
    rig.start()
    rig.state.commands.append(_command(CMD_A))
    await until(lambda: "running" in rig.states(CMD_A))
    await until(lambda: rig.disk.current() is not None and rig.disk.current().cancel_requested)  # type: ignore[union-attr]
    rig.system.gate.set()
    await until(lambda: rig.finished(CMD_A))
    await rig.stop()

    final = rig.final(CMD_A)
    assert final["state"] == "cancelled"
    assert [step["status"] for step in final["progress"]["steps"]] == ["done", "skipped"]
    assert rig.system.calls == ["build_cache"]


async def test__cleanup__command_closed_on_the_server__stops_and_reports_nothing_more(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.system.gate = asyncio.Event()
    rig.state.progress_errors[CMD_A] = (409, "command_finished")
    rig.start()
    rig.state.commands.append(_command(CMD_A))
    await until(lambda: "progress:running" in rig.state.events)
    rig.system.gate.set()
    await until(lambda: rig.disk.current() is not None and rig.disk.current().finished)  # type: ignore[union-attr]
    await asyncio.sleep(0.05)
    await rig.stop()

    run = rig.disk.current()
    assert run is not None
    assert run.state is RunnerCommandState.cancelled
    assert rig.state.events.count("progress:running") == 1
    assert not any(event in rig.state.events for event in ("progress:cancelled", "progress:done"))
    assert rig.system.calls == ["build_cache"]


async def test__cleanup__busy__second_command_closes_with_an_error(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.system.gate = asyncio.Event()
    rig.start()
    rig.state.commands.append(_command(CMD_A))
    await rig.system.started.wait()
    rig.state.commands.append(_command(CMD_B, targets=("runner_cache",)))
    await until(lambda: rig.finished(CMD_B))
    rig.system.gate.set()
    await until(lambda: rig.finished(CMD_A))
    await rig.stop()

    assert rig.final(CMD_B) == {"state": "error", "progress": {"steps": [], "freed_bytes": 0, "error": BUSY_ERROR}}
    assert rig.final(CMD_A)["state"] == "done"


async def test__same_command_delivered_twice__runs_once_and_repeats_the_result(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.system.gate = asyncio.Event()
    rig.start()
    rig.state.commands.extend([_command(CMD_A), _command(CMD_A)])
    await rig.system.started.wait()
    await until(lambda: not rig.state.commands)
    rig.system.gate.set()
    await until(lambda: rig.finished(CMD_A))
    rig.state.commands.append(_command(CMD_A))
    await until(lambda: rig.states(CMD_A).count("done") == 2)
    await rig.stop()

    assert rig.system.calls == ["build_cache", "dangling_images"]


async def test__stop__running_cleanup_is_cancelled_and_reported_before_offline(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.system.gate = asyncio.Event()
    rig.start()
    rig.state.commands.append(_command(CMD_A))
    await rig.system.started.wait()
    stopping = asyncio.create_task(rig.stop())
    await asyncio.sleep(0.05)
    rig.system.gate.set()
    await stopping

    events = rig.state.events
    assert "progress:cancelled" in events
    assert events.index("progress:cancelled") < events.index("offline")
    assert [step["status"] for step in rig.final(CMD_A)["progress"]["steps"]] == ["done", "skipped"]


async def test__stop__stuck_step_is_cut_and_still_reported_cancelled(tmp_path: Path) -> None:
    rig = Rig(tmp_path, stop_timeout_s=0.1)
    rig.system.gate = asyncio.Event()  # шаг так и не закончится
    rig.start()
    rig.state.commands.append(_command(CMD_A))
    await rig.system.started.wait()
    await rig.stop()

    events = rig.state.events
    assert events.index("progress:cancelled") < events.index("offline")


async def test__final_result__repeated_while_the_server_is_unavailable(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.start()
    await until(lambda: len(rig.state.disks) == 1)
    rig.state.progress_unavailable = 3
    rig.state.commands.append(_command(CMD_A, "disk.measure"))
    await until(lambda: rig.finished(CMD_A))
    await rig.stop()

    assert rig.state.events.count("progress:done") == 4
    assert rig.states(CMD_A) == ["done"]


async def test__long_step__progress_is_repeated_to_keep_the_command_alive(tmp_path: Path) -> None:
    rig = Rig(tmp_path, keepalive_s=0.05)
    rig.system.gate = asyncio.Event()
    rig.start()
    rig.state.commands.append(_command(CMD_A))
    await until(lambda: rig.states(CMD_A).count("running") >= 3)
    rig.system.gate.set()
    await until(lambda: rig.finished(CMD_A))
    await rig.stop()


async def test__unsupported_command__closed_with_an_error(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.start()
    rig.state.commands.append({**_command(CMD_A), "kind": "node.reboot"})
    await until(lambda: rig.finished(CMD_A))
    await rig.stop()

    final = rig.final(CMD_A)
    assert final["state"] == "error"
    assert final["progress"]["error"].startswith("unsupported command")
    assert rig.system.calls == []


async def test__network_down__command_poll_backs_off_and_recovers(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.start()
    await until(lambda: rig.state.control_polls > 0)
    rig.transport.down = True
    await asyncio.sleep(0.2)
    rig.transport.down = False
    polls = rig.state.control_polls
    await until(lambda: rig.state.control_polls > polls)
    rig.state.commands.append(_command(CMD_A, "disk.measure"))
    await until(lambda: rig.finished(CMD_A))
    await rig.stop()

    assert rig.control.running is False


async def test__disk_report__repeated_on_schedule(tmp_path: Path) -> None:
    rig = Rig(tmp_path, report_every_s=0.05)
    rig.start()
    await until(lambda: len(rig.state.disks) >= 3)
    await rig.stop()


async def test__reannounce__asks_for_a_fresh_report(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.start()
    await until(lambda: len(rig.state.disks) == 1)
    await rig.loop.reannounce()
    await until(lambda: len(rig.state.disks) == 2)
    await rig.stop()


async def test__server_drops_the_channel__polling_stops_until_the_next_announce(tmp_path: Path) -> None:
    rig = Rig(tmp_path)
    rig.start()
    await until(lambda: rig.state.control_polls > 0)
    rig.state.server_features -= {"control"}
    await until(lambda: not rig.control.running)
    rig.state.server_features |= {"control"}
    await rig.loop.reannounce()
    assert rig.control.running
    polls = rig.state.control_polls
    await until(lambda: rig.state.control_polls > polls)
    await rig.stop()
