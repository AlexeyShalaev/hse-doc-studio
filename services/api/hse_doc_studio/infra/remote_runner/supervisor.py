"""Супервизор облачных сборок локальной Студии: сопряжение, жизненный цикл сессии раннера, состояние.

Живёт в процессе локального api (синглтон контейнера). Пока переключатель выключен, ничего не
запускает и в сеть не ходит. Включённый и сопряжённый, держит одну сессию раннера; смена
настроек заканчивает её мягко и открывает новую.
"""

from __future__ import annotations

import asyncio
import contextlib
import time
from collections.abc import Callable, Coroutine
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import structlog

from hse_doc_studio.core.remote_runner import (
    REMOTE_RUNNER_MAX_CONCURRENCY,
    REMOTE_RUNNER_NAME_MAX,
    IRemoteRunnerSettingsStore,
    RemoteRunnerDetail,
    RemoteRunnerError,
    RemoteRunnerErrorCode,
    RemoteRunnerPairing,
    RemoteRunnerSettings,
    RemoteRunnerState,
    RemoteRunnerStatusInfo,
    normalize_server_url,
)
from hse_doc_studio.infra.remote_runner.session import (
    IRunnerSession,
    RunnerSessionFactory,
    RunnerSessionFatal,
    RunnerSessionSpec,
    SessionFatalCode,
    SessionState,
)
from hse_doc_studio.infra.runner.client import RunnerApiError, RunnerUnreachable
from hse_doc_studio.infra.runner.identity import RunnerIdentity, RunnerIdentityStore
from hse_doc_studio.infra.runner.pairing_client import (
    SLOW_DOWN_CODE,
    PairingPoll,
    PairingStart,
    PairingStatus,
    RunnerPairingClient,
    is_disabled,
)

logger = structlog.get_logger(__name__)

HOST_KIND_DESKTOP = "desktop"
# Каталог раннера внутри data_dir Студии: HostPathResolver образа all-in-one переводит его в путь хоста.
RUNNER_DIR_NAME = "remote-runner"
# Мягкая остановка: идущие облачные сборки доделываются, дольше ждать выход из приложения не должен.
DRAIN_TIMEOUT_S = 30.0
# Раннер выключен на сервере (хозяин отключён или личные раннеры выключены): повтор раз в 5 минут.
DISABLED_RETRY_S = 300.0
CRASH_RETRY_S = 30.0
# Сервер просит опрашивать сопряжение реже: прибавка к интервалу по RFC 8628.
SLOW_DOWN_STEP_S = 5.0

PairingClientFactory = Callable[[str], RunnerPairingClient]


class _SlowDownError(Exception):
    """Сервер просит опрашивать сопряжение реже."""


Sleep = Callable[[float], Coroutine[object, object, None]]


class RemoteRunnerSupervisor:
    def __init__(  # noqa: PLR0913
        self,
        store: IRemoteRunnerSettingsStore,
        *,
        runner_dir: Path,
        default_name: str,
        pairing_client: PairingClientFactory,
        session_factory: RunnerSessionFactory | None,
        min_pairing_interval_s: float = 1.0,
        disabled_retry_s: float = DISABLED_RETRY_S,
        crash_retry_s: float = CRASH_RETRY_S,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._store = store
        self._runner_dir = runner_dir
        self._identities = RunnerIdentityStore(runner_dir)
        self._default_name = default_name[:REMOTE_RUNNER_NAME_MAX] or "Studio"
        self._pairing_client = pairing_client
        self._session_factory = session_factory
        self._min_pairing_interval_s = min_pairing_interval_s
        self._disabled_retry_s = disabled_retry_s
        self._crash_retry_s = crash_retry_s
        self._sleep = sleep
        self._lock = asyncio.Lock()
        self._settings = RemoteRunnerSettings()
        self._identity: RunnerIdentity | None = None
        # Токен регистрации живёт только в памяти: до регистрации, потом его заменяет личность на диске.
        self._registration_token: str | None = None
        self._pairing: RemoteRunnerPairing | None = None
        self._pairing_task: asyncio.Task[None] | None = None
        self._session: IRunnerSession | None = None
        self._session_task: asyncio.Task[None] | None = None
        self._session_stop = asyncio.Event()
        self._session_state = SessionState.connecting
        # Исход, который держится до следующего действия человека: отзыв, отказ сервера, сбой.
        self._sticky: RemoteRunnerState | None = None
        self._detail: RemoteRunnerDetail | None = None

    # --- чтение --------------------------------------------------------------------------------

    def status(self) -> RemoteRunnerStatusInfo:
        state = self._state()
        identity = self._identity
        return RemoteRunnerStatusInfo(
            settings=self._settings,
            state=state,
            paired=identity is not None,
            runner_id=identity.runner_id if identity else None,
            runner_name=None if state is RemoteRunnerState.off and identity is None else self._name(),
            detail_code=self._detail.value if self._detail else None,
            running_jobs=self._session.running_jobs if self._session else 0,
            pairing=self._pairing,
        )

    def _state(self) -> RemoteRunnerState:
        if not self._settings.enabled:
            return RemoteRunnerState.off
        if self._pairing is not None:
            return RemoteRunnerState.pairing
        if self._sticky is not None:
            return self._sticky
        if self._session_task is None:
            return RemoteRunnerState.unpaired
        return RemoteRunnerState(self._session_state.value)

    def _name(self) -> str:
        return self._settings.name or self._default_name

    # --- жизненный цикл ------------------------------------------------------------------------

    async def start(self) -> None:
        async with self._lock:
            self._settings = await self._store.load()
            self._reload_identity()
            await self._restart_session()

    async def stop(self) -> None:
        async with self._lock:
            await self._cancel_pairing()
            await self._stop_session()

    # --- действия человека ---------------------------------------------------------------------

    async def apply(self, settings: RemoteRunnerSettings) -> None:
        _validate(settings)
        async with self._lock:
            previous = self._settings
            if settings.server_url is not None:
                settings = replace(settings, server_url=normalize_server_url(settings.server_url))
            await self._store.save(settings)
            self._settings = settings
            if not settings.enabled:
                await self._cancel_pairing()
                self._clear_outcome()
            if settings.server_url != previous.server_url:
                # Личность выдана другим сервером: здесь она не годится, повторно подключаться надо заново.
                self._registration_token = None
                self._reload_identity()
            if _session_inputs(settings) != _session_inputs(previous):
                self._clear_outcome()
                await self._restart_session()

    async def start_pairing(self, server_url: str, name: str) -> None:
        url = normalize_server_url(server_url)
        name = _clean_name(name)
        async with self._lock:
            await self._cancel_pairing()
            client = self._pairing_client(url)
            try:
                started = await client.start(name, HOST_KIND_DESKTOP)
            except RunnerUnreachable as exc:
                await client.aclose()
                raise RemoteRunnerError(RemoteRunnerErrorCode.unreachable, str(exc)) from exc
            except RunnerApiError as exc:
                await client.aclose()
                if is_disabled(exc):
                    raise RemoteRunnerError(RemoteRunnerErrorCode.disabled, exc.detail) from exc
                raise RemoteRunnerError(RemoteRunnerErrorCode.unreachable, str(exc)) from exc
            await self._stop_session()
            self._settings = replace(self._settings, enabled=True, server_url=url, name=name)
            await self._store.save(self._settings)
            self._registration_token = None
            self._reload_identity()
            self._clear_outcome()
            self._pairing = RemoteRunnerPairing(
                user_code=started.user_code,
                verification_uri_complete=started.verification_uri_complete,
                expires_at=datetime.now(UTC) + timedelta(seconds=started.expires_in),
            )
            self._pairing_task = asyncio.create_task(self._pair(client, started))

    async def cancel_pairing(self) -> None:
        async with self._lock:
            await self._cancel_pairing()

    async def use_token(self, server_url: str, token: str) -> None:
        url = normalize_server_url(server_url)
        async with self._lock:
            await self._cancel_pairing()
            await self._stop_session()
            self._settings = replace(self._settings, enabled=True, server_url=url)
            await self._store.save(self._settings)
            # Новый токен значит новый раннер: прежняя личность для этого сервера больше не нужна.
            self._identities.forget()
            self._identity = None
            self._registration_token = token.strip()
            self._clear_outcome()
            await self._restart_session()

    async def unpair(self) -> None:
        async with self._lock:
            await self._cancel_pairing()
            await self._stop_session()
            identity = self._identity
            if identity is not None:
                await self._deregister(identity)
            self._identities.forget()
            self._identity = None
            self._registration_token = None
            self._clear_outcome()
            self._settings = replace(self._settings, enabled=False)
            await self._store.save(self._settings)

    # --- сопряжение ----------------------------------------------------------------------------

    async def _pair(self, client: RunnerPairingClient, started: PairingStart) -> None:
        try:
            token = await self._wait_for_approval(client, started)
        finally:
            await client.aclose()
        async with self._lock:
            self._pairing = None
            self._pairing_task = None
            if token is None:
                return
            self._registration_token = token
            await self._restart_session()

    async def _wait_for_approval(self, client: RunnerPairingClient, started: PairingStart) -> str | None:
        """Токен регистрации после подтверждения; None при отказе, истечении или выключенных раннерах."""
        interval = max(float(started.interval), self._min_pairing_interval_s)
        deadline = time.monotonic() + started.expires_in
        while True:
            await self._sleep(interval)
            try:
                polled = await self._poll_pairing(client, started.device_code)
            except _SlowDownError:
                interval += SLOW_DOWN_STEP_S
                continue
            except RunnerApiError:
                return None
            if polled is not None and polled.status is PairingStatus.approved and polled.registration_token:
                return polled.registration_token
            if self._pairing_ended(polled, deadline):
                return None

    async def _poll_pairing(self, client: RunnerPairingClient, device_code: str) -> PairingPoll | None:
        """Ответ опроса; None, если сервер мигнул (код ещё жив, пробуем дальше до его срока)."""
        try:
            return await client.poll(device_code)
        except RunnerUnreachable as exc:
            logger.info("remote runner pairing poll failed", error=str(exc))
            return None
        except RunnerApiError as exc:
            if exc.code == SLOW_DOWN_CODE:
                raise _SlowDownError from exc
            if is_disabled(exc):
                self._finish_pairing(RemoteRunnerState.disabled, RemoteRunnerDetail.runner_disabled)
            else:
                self._finish_pairing(RemoteRunnerState.error, RemoteRunnerDetail.unreachable)
            raise

    def _pairing_ended(self, polled: PairingPoll | None, deadline: float) -> bool:
        if polled is not None and polled.status is PairingStatus.denied:
            self._finish_pairing(RemoteRunnerState.unpaired, RemoteRunnerDetail.pairing_denied)
            return True
        # approved без токена значит секрет уже выдан другому опросу: для этого процесса код истёк.
        expired = polled is not None and polled.status in (PairingStatus.expired, PairingStatus.approved)
        if expired or time.monotonic() >= deadline:
            self._finish_pairing(RemoteRunnerState.unpaired, RemoteRunnerDetail.pairing_expired)
            return True
        return False

    def _finish_pairing(self, state: RemoteRunnerState, detail: RemoteRunnerDetail) -> None:
        self._sticky = None if state is RemoteRunnerState.unpaired else state
        self._detail = detail

    async def _cancel_pairing(self) -> None:
        task, self._pairing_task = self._pairing_task, None
        self._pairing = None
        if task is not None and not task.done():
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    # --- сессия раннера ------------------------------------------------------------------------

    async def _restart_session(self) -> None:
        await self._stop_session()
        settings = self._settings
        if not settings.enabled or settings.server_url is None:
            return
        if self._identity is None and self._registration_token is None:
            return
        self._session_state = SessionState.connecting
        self._session_stop = asyncio.Event()
        self._session_task = asyncio.create_task(self._run_sessions(self._session_stop))

    async def _stop_session(self) -> None:
        task, self._session_task = self._session_task, None
        self._session_stop.set()
        if task is None or task.done():
            return
        if self._session is not None:
            self._session.request_stop()
        # Цикл сам доделывает идущие задачи в пределах drain; запас сверху на отчёт серверу.
        done, _ = await asyncio.wait({task}, timeout=DRAIN_TIMEOUT_S + 10.0)
        if not done:
            task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await task

    async def _run_sessions(self, stop: asyncio.Event) -> None:
        if self._session_factory is None:
            return
        while not stop.is_set():
            retry_s = await self._run_session_once(self._session_factory, stop)
            if retry_s is None:
                return
            await self._sleep_or_stop(stop, retry_s)
            self._sticky = None
            self._session_state = SessionState.connecting

    async def _run_session_once(self, factory: RunnerSessionFactory, stop: asyncio.Event) -> float | None:
        """Одна сессия до конца; пауза перед повтором или None, когда повторять нечего."""
        try:
            async with factory(self._spec(), self) as session:
                self._session = session
                # Остановку могли попросить, пока сессия открывалась: тогда она не берёт ни одной задачи.
                if stop.is_set():
                    session.request_stop()
                await session.run()
        except RunnerSessionFatal as exc:
            if exc.code is SessionFatalCode.unauthorized:
                self._on_unauthorized()
                return None
            logger.info("remote runner disabled on server, retrying later")
            self._sticky, self._detail = RemoteRunnerState.disabled, RemoteRunnerDetail.runner_disabled
            return self._disabled_retry_s
        except Exception:
            logger.exception("remote runner session crashed")
            self._sticky, self._detail = RemoteRunnerState.error, RemoteRunnerDetail.crashed
            return self._crash_retry_s
        finally:
            self._session = None
        return None

    async def _sleep_or_stop(self, stop: asyncio.Event, delay_s: float) -> None:
        sleeper = asyncio.create_task(self._sleep(delay_s))
        stopper = asyncio.create_task(stop.wait())
        try:
            await asyncio.wait({sleeper, stopper}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            sleeper.cancel()
            stopper.cancel()

    def _on_unauthorized(self) -> None:
        if self._identity is not None:
            # Раннер отозван на сайте или токен сменили: личность бесполезна, переключатель остаётся включённым.
            self._identities.forget()
            self._identity = None
            self._sticky, self._detail = RemoteRunnerState.revoked, RemoteRunnerDetail.runner_revoked
        else:
            self._sticky, self._detail = RemoteRunnerState.error, RemoteRunnerDetail.token_rejected
        self._registration_token = None

    def _spec(self) -> RunnerSessionSpec:
        settings = self._settings
        if settings.server_url is None:
            raise RuntimeError("remote runner session without server url")
        return RunnerSessionSpec(
            server_url=settings.server_url,
            registration_token=self._registration_token,
            name=self._name(),
            concurrency=settings.concurrency,
            data_dir=self._runner_dir,
        )

    # IRunnerSessionListener: зовётся из задачи цикла, в том же потоке событий.
    def on_session_state(self, state: SessionState) -> None:
        self._session_state = state
        if state is SessionState.online:
            self._detail = None

    def on_registered(self, runner_id: str) -> None:
        self._registration_token = None
        self._reload_identity()
        logger.info("remote runner registered", runner_id=runner_id)

    # --- служебное -----------------------------------------------------------------------------

    def _reload_identity(self) -> None:
        url = self._settings.server_url
        self._identity = self._identities.load(url) if url else None

    def _clear_outcome(self) -> None:
        self._sticky = None
        self._detail = None

    async def _deregister(self, identity: RunnerIdentity) -> None:
        """Сообщить серверу, что раннера больше нет; сервер недоступен, значит раннер отзовёт хозяин на сайте."""
        client = self._pairing_client(identity.api_url)
        try:
            await client.deregister(identity.runner_id, identity.runner_token)
        except (RunnerApiError, RunnerUnreachable) as exc:
            logger.info("remote runner deregister failed", error=str(exc))
        finally:
            await client.aclose()


def _session_inputs(settings: RemoteRunnerSettings) -> tuple[object, ...]:
    """Поля, смена которых требует нового цикла; `yield_to_local` читается шлюзом на лету."""
    return (settings.enabled, settings.server_url, settings.name, settings.concurrency)


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned or len(cleaned) > REMOTE_RUNNER_NAME_MAX:
        raise ValueError("runner name must be 1..128 characters")
    return cleaned


def _validate(settings: RemoteRunnerSettings) -> None:
    if not 1 <= settings.concurrency <= REMOTE_RUNNER_MAX_CONCURRENCY:
        raise ValueError("concurrency must be within 1..4")
    if settings.name is not None:
        _clean_name(settings.name)
