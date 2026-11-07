"""Исполнитель kubernetes: каждая сборка TeX отдельным подом в namespace раннера (docs/design/k8s-runner.md)."""

from __future__ import annotations

import asyncio
import re
import secrets
import uuid
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

import structlog

from hse_doc_studio.core.compile.errors import (
    BuildBackendUnavailableError,
    BuildOutOfMemoryError,
    BuildStorageExceededError,
    ImageMissingError,
)
from hse_doc_studio.core.jobs.artifacts import IArtifactStore, PublishPdfRequest
from hse_doc_studio.core.jobs.protocols import ProcessHandle
from hse_doc_studio.infra.compile.docker_image_manager import DockerStatus, ImageInfo
from hse_doc_studio.infra.compile.k8s.api import IKubeApi, KubeApiError, PodState
from hse_doc_studio.infra.compile.k8s.config import KubernetesExecutorConfig
from hse_doc_studio.infra.compile.k8s.pod import (
    CONTAINER,
    BuildPodSpec,
    build_pod_manifest,
    build_selector,
    download_command,
    new_pod_name,
    probe_command,
    upload_command,
)
from hse_doc_studio.infra.compile.k8s.transfer import OutputSpool, OutputTooLargeError, extract_build, pack_workspace
from hse_doc_studio.infra.compile.latexmk import (
    ENGINE_FLAG,
    SENTINEL_DONE,
    SENTINEL_FAILED,
    SENTINEL_PAGES,
    SENTINEL_WORDS,
    extract_log_page_count,
    reset_latexmk_state,
    sum_texcount_total,
    tex_source,
)
from hse_doc_studio.infra.jobs.artifact_store import LocalDiskArtifactStore

logger = structlog.get_logger()

# Ждать pull дальше бессмысленно: образа нет или имя неверно.
_IMAGE_FATAL = frozenset({"ImagePullBackOff", "InvalidImageName", "ErrImageNeverPull"})
_CONFIG_FATAL = frozenset({"CreateContainerConfigError", "CreateContainerError", "RunContainerError"})
_TS_RE = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d{1,9}))?Z$")
_SIGKILL_EXIT = 137
_POLL_S = 0.5
_RECONNECT_S = 1.0
# Сколько тишины в потоке лога терпеть до проверки итога через exec и переподключения потока.
_PROBE_S = 30.0
# Сколько ждать texcount после выхода latexmk: счётчики не стоят сборки.
_COUNTS_TIMEOUT_S = 120.0


@dataclass
class _Run:
    """Итог сборки из маркеров лога (или из файлов пода, если поток лога замолчал)."""

    rc: int | None = None
    words: list[str] | None = None
    chars: list[str] | None = None
    ended: bool = False
    timed_out: bool = False
    counts_skipped: bool = False

    def take(self, line: str, nonce: str) -> str | None:
        """Снимает с строки маркеры `<nonce>:<вид>:` и возвращает остаток для журнала (None, если остатка нет).

        Маркер ищется не только в начале строки: вывод без перевода строки в конце (latexmk, texcount
        с ошибками разбора) склеивается со следующим маркером, и маркер конца терять нельзя.
        """
        prefix = f"{nonce}:"
        head, sep, rest = line.partition(prefix)
        if not sep:
            return line
        for chunk in rest.split(prefix):
            kind, _, value = chunk.partition(":")
            self._mark(kind, value)
        return head or None

    def _mark(self, kind: str, value: str) -> None:
        if kind == "end":
            self.ended = True
        elif kind == "exit":
            with suppress(ValueError):
                self.rc = int(value.strip())
        elif kind == "words":
            self.words = [*(self.words or ()), value]
        elif kind == "chars":
            self.chars = [*(self.chars or ()), value]

    def adopt(self, probe: str) -> None:
        """Итог из файлов пода (`probe_command`): код latexmk, а после конца ещё и строки texcount."""
        words: list[str] = []
        chars: list[str] = []
        ended = False
        for line in probe.splitlines():
            kind, _, value = line.partition(":")
            if kind == "rc" and self.rc is None:
                with suppress(ValueError):
                    self.rc = int(value.strip())
            elif line == "end":
                ended = True
            elif kind == "words":
                words.append(value)
            elif kind == "chars":
                chars.append(value)
        if ended and self.rc is not None:
            self.ended = True
            self.words = self.words or words or None
            self.chars = self.chars or chars or None


class LogCursor:
    """Позиция в логе пода для переподключения: метка времени последней строки и сколько строк с этой меткой отдано.

    Метки RFC3339Nano без хвостовых нулей, поэтому сравниваются секунды и наносекунды отдельно. После
    переподключения с `sinceTime` (точность секунда) повторённые строки пропускаются.
    """

    def __init__(self) -> None:
        self._last: tuple[str, int] | None = None
        self._seen_at_last = 0
        self._replay = False
        self._replayed = 0
        self.since: str | None = None

    def reconnect(self) -> None:
        self._replay, self._replayed = self._last is not None, 0

    def accept(self, stamp: str) -> bool:
        key = _ts_key(stamp)
        if key is None:
            return True
        if self._replay and self._last is not None:
            if key < self._last:
                return False
            if key == self._last and self._replayed < self._seen_at_last:
                self._replayed += 1
                return False
            self._replay = False
        if key == self._last:
            self._seen_at_last += 1
        else:
            self._last, self._seen_at_last = key, 1
        self.since = stamp[:19] + "Z"
        return True


class KubernetesTexExecutor:
    """`ITexBuildExecutor`: создать под, отдать вход, читать лог, забрать `.build/<doc_id>`, удалить под."""

    def __init__(  # noqa: PLR0913
        self,
        api: IKubeApi,
        config: KubernetesExecutorConfig,
        *,
        image: str,
        instance: str,
        idle_timeout_s: float,
        artifacts: IArtifactStore | None = None,
        poll_s: float = _POLL_S,
        reconnect_s: float = _RECONNECT_S,
        probe_s: float = _PROBE_S,
        counts_timeout_s: float = _COUNTS_TIMEOUT_S,
    ) -> None:
        self._api = api
        self._cfg = config
        self._namespace = config.resolved_namespace()
        self._image = config.image or image
        self._instance = instance
        self._idle_timeout_s = idle_timeout_s
        self._artifacts = artifacts or LocalDiskArtifactStore()
        self._poll_s = poll_s
        self._reconnect_s = reconnect_s
        self._probe_s = min(probe_s, idle_timeout_s)
        self._counts_timeout_s = counts_timeout_s

    @property
    def namespace(self) -> str:
        return self._namespace

    async def run(  # noqa: PLR0913
        self,
        project_folder: Path,
        source_file: str,
        engine: str,
        max_iterations: int,
        doc_id: str,
        compile_id: uuid.UUID,
        image: str | None = None,
        on_process_started: Callable[[ProcessHandle], None] | None = None,
        project_id: uuid.UUID | None = None,
    ) -> AsyncGenerator[str, None]:
        return self._stream(
            project_folder=project_folder,
            source_file=source_file,
            engine=engine,
            max_iterations=max_iterations,
            doc_id=doc_id,
            compile_id=compile_id,
            # Образ пода задаёт раннер (K8S__IMAGE или TEX_IMAGE), а не выбор образа в api.
            image=self._image if self._cfg.image else (image or self._image),
            project_id=project_id,
        )

    async def _stream(  # noqa: C901, PLR0911, PLR0912, PLR0913, PLR0915
        self,
        *,
        project_folder: Path,
        source_file: str,
        engine: str,
        max_iterations: int,
        doc_id: str,
        compile_id: uuid.UUID,
        image: str,
        project_id: uuid.UUID | None,
    ) -> AsyncGenerator[str, None]:
        engine_flag = ENGINE_FLAG.get(engine)
        if engine_flag is None:
            yield f"[error] unsupported engine: {engine}"
            yield SENTINEL_FAILED
            return
        src = tex_source(source_file, doc_id)
        build_dir = project_folder / src.build_rel
        try:
            build_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            yield f"[error] cannot create build dir {build_dir}: {exc}"
            yield SENTINEL_FAILED
            return
        spec = BuildPodSpec(
            name=new_pod_name(compile_id),
            nonce=secrets.token_hex(12),
            image=image,
            engine=engine,
            engine_flag=engine_flag,
            max_iterations=max_iterations,
            source=src,
            compile_id=compile_id,
            instance=self._instance,
        )
        yield (
            f"[compile:{compile_id}] {engine} via latexmk (max_repeat={max_iterations}, image={image}, "
            f"pod={self._namespace}/{spec.name})"
        )
        created = False
        try:
            try:
                await self._api.create_pod(self._namespace, build_pod_manifest(spec, self._cfg, self._namespace))
            except KubeApiError as exc:
                raise BuildBackendUnavailableError(f"cannot create build pod: {exc}") from exc
            created = True
            async for line in self._wait_running(spec.name, image):
                yield line
            await self._upload(spec.name, project_folder, src.build_rel)
            run = _Run()
            async for line in self._follow(spec, run):
                yield line
            if run.counts_skipped:
                yield f"[warn] texcount did not finish in {self._counts_timeout_s:.0f}s, word counts skipped"
            if run.timed_out:
                yield f"[error] no output for {self._idle_timeout_s:.0f}s, killing pod"
                yield SENTINEL_FAILED
                return
            if not run.ended or run.rc is None:
                await self._raise_if_resource_stop(spec.name)
                yield f"[error] build pod stopped before the build finished: {await self._describe_stop(spec.name)}"
                yield SENTINEL_FAILED
                return
            if run.rc == _SIGKILL_EXIT:
                # Под жив, а latexmk убит SIGKILL: так ядро останавливает процесс по лимиту памяти cgroup.
                raise BuildOutOfMemoryError(
                    f"latexmk was killed (exit code {_SIGKILL_EXIT}); memory limit {self._cfg.memory_limit}"
                )
            try:
                await self._download(spec.name, project_folder, src.build_rel)
            except OutputTooLargeError as exc:
                yield f"[error] {exc}"
                yield SENTINEL_FAILED
                return
        finally:
            if created:
                await asyncio.shield(self._delete(spec.name))

        if run.rc != 0:
            yield f"[compile:{compile_id}] latexmk exited with code {run.rc}"
            reset_latexmk_state(build_dir, src.stem)
            yield SENTINEL_FAILED
            return
        yield f"[compile:{compile_id}] latexmk converged (rc=0)"
        built_pdf = build_dir / f"{src.stem}.pdf"
        if not built_pdf.exists():
            yield f"[error] expected PDF not produced: {built_pdf.name}"
            yield SENTINEL_FAILED
            return
        outcome = await self._artifacts.publish_pdf(
            PublishPdfRequest(
                workspace=project_folder,
                doc_id=doc_id,
                job_id=compile_id,
                source_file=source_file,
                project_id=project_id,
            )
        )
        if not outcome.replaced:
            yield (
                f"[warn] could not replace {outcome.final_name} next to the sources "
                f"(file is open in another program); fresh PDF kept in .build"
            )
        else:
            yield f"[compile:{compile_id}] pdf written to {outcome.final_name}"
        pages = extract_log_page_count(build_dir / f"{src.stem}.log")
        if pages is not None:
            yield f"{SENTINEL_PAGES}{pages}"
        words = sum_texcount_total("\n".join(run.words or ()))
        chars = sum_texcount_total("\n".join(run.chars or ()))
        if words is not None and chars is not None:
            yield f"{SENTINEL_WORDS}{words}:{chars}"
        yield SENTINEL_DONE

    async def _wait_running(self, name: str, image: str) -> AsyncIterator[str]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._cfg.pod_start_timeout_s
        last = ""
        while True:
            try:
                state = await self._api.read_pod(self._namespace, name)
            except KubeApiError as exc:
                raise BuildBackendUnavailableError(f"cannot read build pod: {exc}") from exc
            if state is None:
                raise BuildBackendUnavailableError(f"build pod {name} disappeared")
            if _started(state, image):
                return
            status = state.unschedulable or state.waiting_reason or state.phase
            if status != last:
                last = status
                yield f"[k8s] waiting for build pod: {status}"
            if loop.time() >= deadline:
                raise BuildBackendUnavailableError(
                    f"build pod not running after {self._cfg.pod_start_timeout_s:.0f}s: {status}"
                )
            await asyncio.sleep(self._poll_s)

    async def _upload(self, name: str, root: Path, build_rel: str) -> None:
        archive, size = await asyncio.to_thread(pack_workspace, root, build_rel)
        try:
            result = await self._api.exec(
                self._namespace, name, CONTAINER, upload_command(size), stdin=archive, stdout=None
            )
        except KubeApiError as exc:
            raise BuildBackendUnavailableError(f"cannot upload sources to the build pod: {exc}") from exc
        finally:
            archive.close()
        if result.exit_code != 0:
            raise BuildBackendUnavailableError(f"upload to the build pod failed ({result.exit_code}): {result.stderr}")

    async def _download(self, name: str, root: Path, build_rel: str) -> None:
        spool = OutputSpool(self._cfg.max_output_bytes)
        try:
            try:
                result = await self._api.exec(
                    self._namespace, name, CONTAINER, download_command(build_rel), stdout=spool.write
                )
            except KubeApiError as exc:
                raise BuildBackendUnavailableError(f"cannot fetch build output: {exc}") from exc
            if result.exit_code != 0:
                raise BuildBackendUnavailableError(
                    f"fetch of build output failed ({result.exit_code}): {result.stderr}"
                )
            await asyncio.to_thread(extract_build, spool.file, root, build_rel)
        finally:
            spool.close()

    async def _follow(self, spec: BuildPodSpec, run: _Run) -> AsyncIterator[str]:  # noqa: C901
        """Строки лога до маркера конца.

        Тишина в потоке ещё не сбой: поток kubelet может зависнуть, не закрывшись, а texcount может идти долго.
        Каждые `probe_s` тишины итог читается из файлов пода через exec, а поток переподключается с `sinceTime`.
        Сборку убивает только настоящее отсутствие прогресса: latexmk молчит дольше `idle_timeout_s` и не
        завершился. После выхода latexmk счётчики texcount ждутся не дольше `counts_timeout_s`, дальше сборка
        идёт без них, как у исполнителя docker.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[str | None] = asyncio.Queue()
        cursor = LogCursor()
        pump = asyncio.create_task(self._pump(spec.name, queue, cursor))
        last_line = loop.time()
        exited_at: float | None = None
        try:
            while True:
                try:
                    line = await asyncio.wait_for(queue.get(), timeout=self._probe_s)
                except TimeoutError:
                    await self._probe(spec.name, run)
                    if run.ended:
                        return
                    now = loop.time()
                    if run.rc is not None:
                        exited_at = exited_at if exited_at is not None else now
                        if now - exited_at >= self._counts_timeout_s:
                            logger.warning("texcount did not finish, build goes on without counts", pod=spec.name)
                            run.ended = run.counts_skipped = True
                            return
                    elif now - last_line >= self._idle_timeout_s:
                        run.timed_out = True
                        return
                    # Поток мог зависнуть, не закрывшись: новое соединение с `sinceTime` догонит пропущенное.
                    pump.cancel()
                    await asyncio.gather(pump, return_exceptions=True)
                    pump = asyncio.create_task(self._pump(spec.name, queue, cursor))
                    continue
                if line is None:
                    return
                last_line = loop.time()
                had_rc = run.rc is not None
                text = run.take(line, spec.nonce)
                if text is not None:
                    yield text
                if run.rc is not None and not had_rc:
                    exited_at = loop.time()
                if run.ended:
                    return
        finally:
            pump.cancel()
            await asyncio.gather(pump, return_exceptions=True)

    async def _probe(self, name: str, run: _Run) -> None:
        """Итог сборки из файлов пода через exec; сбой exec не ошибка, решает таймер тишины."""
        out = bytearray()
        try:
            result = await self._api.exec(self._namespace, name, CONTAINER, probe_command(), stdout=out.extend)
        except KubeApiError as exc:
            logger.warning("cannot probe build pod", pod=name, error=str(exc))
            return
        if result.exit_code == 0:
            run.adopt(out.decode("utf-8", errors="replace"))

    async def _pump(self, name: str, queue: asyncio.Queue[str | None], cursor: LogCursor) -> None:
        """Лог с переподключением, пока контейнер жив; конец потока обозначает `None`.

        Отменённый насос (переподключение по тишине) `None` не кладёт: читатель ждёт следующий насос.
        """
        try:
            while True:
                cursor.reconnect()
                try:
                    async for raw in self._api.stream_log(self._namespace, name, CONTAINER, cursor.since):
                        stamp, text = _split_timestamp(raw)
                        if cursor.accept(stamp):
                            queue.put_nowait(text)
                except KubeApiError as exc:
                    logger.warning("build pod log stream failed", pod=name, error=str(exc))
                if not await self._container_alive(name):
                    queue.put_nowait(None)
                    return
                await asyncio.sleep(self._reconnect_s)
        except Exception:
            queue.put_nowait(None)
            raise

    async def _container_alive(self, name: str) -> bool:
        try:
            state = await self._api.read_pod(self._namespace, name)
        except KubeApiError:
            return False
        return state is not None and state.phase in ("Pending", "Running") and state.container_running

    async def _raise_if_resource_stop(self, name: str) -> None:
        """Под остановлен по памяти или выселен за эфемерное хранилище: сбой ресурса, а не LaTeX и не общий сбой."""
        try:
            state = await self._api.read_pod(self._namespace, name)
        except KubeApiError:
            return
        if state is not None:
            resource_stop_error(state, self._cfg.memory_limit)

    async def _describe_stop(self, name: str) -> str:
        try:
            state = await self._api.read_pod(self._namespace, name)
        except KubeApiError as exc:
            return str(exc)
        if state is None:
            return "pod deleted"
        if state.reason == "DeadlineExceeded":
            return f"activeDeadlineSeconds={self._cfg.active_deadline_s} exceeded"
        return _why(state)

    async def _delete(self, name: str) -> None:
        try:
            await self._api.delete_pod(self._namespace, name)
        except KubeApiError as exc:
            # Не удалился сейчас: его уберут activeDeadlineSeconds, владелец или уборка на старте раннера.
            logger.warning("cannot delete build pod", pod=name, error=str(exc))

    async def sweep(self) -> int:
        """Удаляет поды сборки этого экземпляра раннера, пережившие его прошлый процесс."""
        try:
            names = await self._api.list_pods(self._namespace, build_selector(self._instance))
        except KubeApiError as exc:
            logger.warning("cannot list leftover build pods", error=str(exc))
            return 0
        for name in names:
            await self._delete(name)
        return len(names)


class KubernetesBuildEnvironment:
    """`IBuildEnvironment`: образ не проверить заранее, его отсутствие видно при запуске пода (`image_missing`)."""

    async def docker_status(self) -> DockerStatus:
        return DockerStatus(available=True, version="kubernetes", detail=None)

    async def inspect(self, image: str) -> ImageInfo | None:
        return ImageInfo(image=image, id="", size_bytes=0, created="")


def _started(state: PodState, image: str) -> bool:
    """Под запущен: True; ждать дальше: False; ждать бессмысленно: исключение."""
    if state.phase == "Running" and state.container_running:
        return True
    if state.phase in ("Succeeded", "Failed"):
        resource_stop_error(state)
        raise BuildBackendUnavailableError(f"build pod {state.phase}: {_why(state)}")
    if state.waiting_reason in _IMAGE_FATAL:
        raise ImageMissingError(image)
    if state.waiting_reason in _CONFIG_FATAL:
        raise BuildBackendUnavailableError(f"{state.waiting_reason}: {state.waiting_message}")
    return False


def resource_stop_error(state: PodState, memory_limit: str = "") -> None:
    """Бросает понятную ошибку, если под убит по памяти (OOMKilled, код 137) или выселен за эфемерное хранилище."""
    if state.terminated_reason == "OOMKilled":
        suffix = f", memory limit {memory_limit}" if memory_limit else ""
        raise BuildOutOfMemoryError(f"OOMKilled (exit code 137){suffix}")
    if state.reason == "Evicted" and any(word in state.message.lower() for word in ("ephemeral", "emptydir")):
        raise BuildStorageExceededError(state.message)


def _why(state: PodState) -> str:
    parts = [state.reason, state.message, state.terminated_reason]
    if state.terminated_exit_code is not None:
        parts.append(f"exit code {state.terminated_exit_code}")
    text = ", ".join(part for part in parts if part)
    return text or state.phase


def _split_timestamp(raw: str) -> tuple[str, str]:
    stamp, sep, text = raw.partition(" ")
    if sep and _TS_RE.match(stamp):
        return stamp, text.rstrip("\r")
    return "", raw.rstrip("\r")


def _ts_key(stamp: str) -> tuple[str, int] | None:
    """Метки RFC3339Nano без хвостовых нулей разной длины: сравниваются секунды и наносекунды отдельно."""
    m = _TS_RE.match(stamp)
    if m is None:
        return None
    return m.group(1), int((m.group(2) or "0").ljust(9, "0"))
