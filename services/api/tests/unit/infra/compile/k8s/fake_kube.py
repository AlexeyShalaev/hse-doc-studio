"""Фейковый Kubernetes API: «файловая система пода» в каталоге, exec с tar, лог из сценария сборки."""

from __future__ import annotations

import asyncio
import io
import tarfile
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import IO, cast

from hse_doc_studio.infra.compile.k8s.api import ExecResult, KubeApiError, PodManifest, PodState
from hse_doc_studio.infra.compile.k8s.pod import probe_command

_BASE = datetime(2026, 11, 3, 10, 0, 0, tzinfo=UTC)


@dataclass
class FakePod:
    name: str
    manifest: dict[str, object]
    work: Path
    states: list[PodState]
    ready: asyncio.Event = field(default_factory=asyncio.Event)
    log: list[str] = field(default_factory=list)
    reads: int = 0
    deleted: bool = False
    # Что отдаёт exec `probe_command` (итог из файлов /tmp/.hds пода); пусто значит latexmk ещё идёт.
    probe: str = ""

    @property
    def labels(self) -> dict[str, str]:
        meta = cast(dict[str, object], self.manifest["metadata"])
        return cast(dict[str, str], meta["labels"])

    @property
    def container(self) -> dict[str, object]:
        spec = cast(dict[str, object], self.manifest["spec"])
        return cast(list[dict[str, object]], spec["containers"])[0]

    @property
    def nonce(self) -> str:
        env = cast(list[dict[str, str]], self.container["env"])
        return next(e["value"] for e in env if e["name"] == "HDS_NONCE")

    def mark(self, kind: str, value: str = "") -> str:
        return f"{self.nonce}:{kind}:{value}"


# Сценарий сборки: получает под (вход уже распакован в `work`), пишет файлы и возвращает строки лога.
Build = Callable[[FakePod], Awaitable[list[str]]]


async def ok_build(pod: FakePod) -> list[str]:
    build = pod.work / "tz" / ".build" / "tz"
    build.mkdir(parents=True, exist_ok=True)
    (build / "main.pdf").write_bytes(b"%PDF-1.5 built")
    (build / "main.log").write_text("Output written on main.xdv (3 pages, 1234 bytes).\n", encoding="utf-8")
    return [
        "Latexmk: This is Latexmk",
        "latexmk ok",
        pod.mark("exit", "0"),
        pod.mark("words", "4+1+1 (1/0/0/0) Total"),
        pod.mark("chars", "20+5+0 (1/0/0/0) Total"),
        pod.mark("end"),
    ]


async def failing_build(pod: FakePod) -> list[str]:
    build = pod.work / "tz" / ".build" / "tz"
    build.mkdir(parents=True, exist_ok=True)
    (build / "main.log").write_text("! boom\n", encoding="utf-8")
    (build / "main.fdb_latexmk").write_text("state", encoding="utf-8")
    return ["! boom", pod.mark("exit", "12"), pod.mark("end")]


class FakeKubeApi:
    def __init__(  # noqa: PLR0913
        self,
        root: Path,
        *,
        build: Build = ok_build,
        states: Sequence[PodState] = (PodState(phase="Pending"), PodState(phase="Running", container_running=True)),
        create_error: KubeApiError | None = None,
        hang_after_log: bool = True,
        drop_log_after: int | None = None,
        after_log_state: PodState | None = None,
        stall_after: int | None = None,
    ) -> None:
        self._root = root
        self._build = build
        self._states = list(states)
        self._create_error = create_error
        self._hang = hang_after_log
        self._drop_after = drop_log_after
        self._after_log_state = after_log_state
        # Первый поток лога отдаёт столько строк и виснет, не закрываясь (как зависший поток kubelet).
        self._stall_after = stall_after
        self.pods: dict[str, FakePod] = {}
        self.deleted: list[str] = []
        self.log_requests: list[str | None] = []
        self.execs: list[list[str]] = []
        self.extra: dict[str, dict[str, str]] = {}

    def only_pod(self) -> FakePod:
        (pod,) = self.pods.values()
        return pod

    async def create_pod(self, namespace: str, manifest: PodManifest) -> None:
        if self._create_error is not None:
            raise self._create_error
        meta = cast(Mapping[str, object], manifest["metadata"])
        name = cast(str, meta["name"])
        work = self._root / name / "work"
        work.mkdir(parents=True)
        self.pods[name] = FakePod(name, dict(manifest), work, list(self._states))

    async def read_pod(self, namespace: str, name: str) -> PodState | None:
        pod = self.pods.get(name)
        if pod is None or pod.deleted:
            return None
        pod.reads += 1
        return pod.states.pop(0) if len(pod.states) > 1 else pod.states[0]

    async def delete_pod(self, namespace: str, name: str) -> None:
        self.deleted.append(name)
        if name in self.pods:
            self.pods[name].deleted = True

    async def list_pods(self, namespace: str, label_selector: str) -> list[str]:
        wanted = dict(part.split("=", 1) for part in label_selector.split(","))
        labelled = {name: pod.labels for name, pod in self.pods.items() if not pod.deleted}
        labelled.update(self.extra)
        return [name for name, labels in labelled.items() if all(labels.get(k) == v for k, v in wanted.items())]

    async def stream_log(  # noqa: C901
        self, namespace: str, name: str, container: str, since_time: str | None
    ) -> AsyncIterator[str]:
        self.log_requests.append(since_time)
        pod = self.pods[name]
        await pod.ready.wait()
        if not pod.log:
            for i, line in enumerate(await self._build(pod)):
                pod.log.append(f"{_stamp(i)} {line}")
        lines = pod.log
        if since_time is not None:
            lines = [line for line in lines if line[:19] >= since_time[:19]]
        for count, line in enumerate(lines):
            if self._drop_after is not None and count >= self._drop_after:
                self._drop_after = None
                raise KubeApiError("log stream reset")
            if self._stall_after is not None and count >= self._stall_after:
                self._stall_after = None
                await asyncio.Event().wait()
            yield line
        if self._after_log_state is not None:
            pod.states = [self._after_log_state]
            return
        if self._hang:
            await asyncio.Event().wait()

    async def exec(  # noqa: PLR0913
        self,
        namespace: str,
        name: str,
        container: str,
        command: Sequence[str],
        *,
        stdin: IO[bytes] | None = None,
        stdout: Callable[[bytes], None] | None = None,
    ) -> ExecResult:
        self.execs.append(list(command))
        pod = self.pods[name]
        if stdin is not None:
            data = stdin.read()
            with tarfile.open(fileobj=io.BytesIO(data), mode="r:") as tar:
                tar.extractall(pod.work, filter="data")
            pod.ready.set()
            return ExecResult(0)
        if list(command) == probe_command():
            if stdout is not None and pod.probe:
                stdout(pod.probe.encode())
            return ExecResult(0)
        assert command[:2] == ["tar", "-c"], command  # noqa: S101
        rel = command[-1]
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as tar:
            tar.add(pod.work / rel, arcname=rel)
        payload = buffer.getvalue()
        assert stdout is not None  # noqa: S101
        for start in range(0, len(payload), 4096):
            stdout(payload[start : start + 4096])
        return ExecResult(0)

    async def aclose(self) -> None:
        return None


def _stamp(index: int) -> str:
    """Две строки на секунду, наносекунды без хвостовых нулей, как у kubelet."""
    moment = _BASE + timedelta(seconds=index // 2, microseconds=(index % 2) * 500_000)
    nanos = f"{moment.microsecond * 1000:09d}".rstrip("0")
    return moment.strftime("%Y-%m-%dT%H:%M:%S") + (f".{nanos}" if nanos else "") + "Z"
