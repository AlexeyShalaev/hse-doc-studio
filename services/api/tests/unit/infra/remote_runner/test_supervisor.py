from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from hse_doc_studio.core.remote_runner import (
    RemoteRunnerError,
    RemoteRunnerErrorCode,
    RemoteRunnerSettings,
    RemoteRunnerSettingsPatch,
    RemoteRunnerState,
)
from hse_doc_studio.infra.remote_runner.session import RunnerSessionFatal, SessionFatalCode, SessionState
from hse_doc_studio.infra.remote_runner.supervisor import RemoteRunnerSupervisor
from hse_doc_studio.infra.runner.identity import RunnerIdentityStore
from hse_doc_studio.infra.runner.pairing_client import RunnerPairingClient

from tests.unit.infra.remote_runner.fake_pairing_api import PAIRED_TOKEN, USER_CODE, FakePairingServer
from tests.unit.infra.remote_runner.fakes import (
    RUNNER_ID,
    RUNNER_TOKEN,
    FakeSessions,
    MemorySettingsStore,
    eventually,
    save_identity,
)

_URL = "https://studio.example.org"


class Harness:
    def __init__(self, tmp_path: Path, settings: RemoteRunnerSettings | None = None) -> None:
        self.runner_dir = tmp_path / "remote-runner"
        self.store = MemorySettingsStore(settings)
        self.server = FakePairingServer()
        self.sessions = FakeSessions()
        self.sleeps: list[float] = []
        self.supervisor = RemoteRunnerSupervisor(
            self.store,
            runner_dir=self.runner_dir,
            default_name="studio-mac",
            pairing_client=lambda url: RunnerPairingClient(url, version="0.3.0", transport=self.server.transport()),
            session_factory=self.sessions,
            min_pairing_interval_s=0.0,
            sleep=self._sleep,
        )

    async def _sleep(self, delay_s: float) -> None:
        self.sleeps.append(delay_s)
        await asyncio.sleep(0)

    @property
    def state(self) -> RemoteRunnerState:
        return self.supervisor.status().state


@pytest.fixture
async def harness(tmp_path: Path) -> Harness:
    return Harness(tmp_path)


async def test__start__toggle_off__state_off_and_no_network(harness: Harness) -> None:
    await harness.supervisor.start()

    status = harness.supervisor.status()
    assert (status.state, status.paired, status.runner_name) == (RemoteRunnerState.off, False, None)
    assert harness.sessions.specs == []
    assert harness.server.starts == []


async def test__apply__enabled_without_pairing__unpaired_with_default_name(harness: Harness) -> None:
    await harness.supervisor.start()

    await harness.supervisor.apply(RemoteRunnerSettings(enabled=True, server_url=_URL + "/"))

    status = harness.supervisor.status()
    assert (status.state, status.runner_name) == (RemoteRunnerState.unpaired, "studio-mac")
    assert harness.store.settings.server_url == _URL


async def test__pairing__approved__registers_with_token_and_goes_online(harness: Harness) -> None:
    await harness.supervisor.start()

    await harness.supervisor.start_pairing(_URL, "MacBook Анны")

    pairing = harness.supervisor.status().pairing
    assert pairing is not None
    assert pairing.user_code == USER_CODE
    assert harness.server.starts == [{"name": "MacBook Анны", "host_kind": "desktop"}]
    await eventually(lambda: harness.state is RemoteRunnerState.online)
    spec = harness.sessions.specs[0]
    assert (spec.server_url, spec.registration_token, spec.name) == (_URL, PAIRED_TOKEN, "MacBook Анны")
    status = harness.supervisor.status()
    assert (status.paired, status.runner_id, status.pairing) == (True, RUNNER_ID, None)
    assert harness.store.settings.enabled is True
    await harness.supervisor.stop()


async def test__pairing__denied__unpaired_with_detail_and_no_session(harness: Harness) -> None:
    harness.server.statuses = ["pending", "denied"]
    await harness.supervisor.start()

    await harness.supervisor.start_pairing(_URL, "MacBook")

    await eventually(lambda: harness.supervisor.status().pairing is None)
    status = harness.supervisor.status()
    assert (status.state, status.detail_code) == (RemoteRunnerState.unpaired, "pairing_denied")
    assert harness.sessions.specs == []


async def test__pairing__slow_down__backs_off_and_keeps_waiting(harness: Harness) -> None:
    harness.server.poll_errors = [(429, "slow_down")]
    await harness.supervisor.start()

    await harness.supervisor.start_pairing(_URL, "MacBook")

    await eventually(lambda: harness.state is RemoteRunnerState.online)
    assert 5.0 in harness.sleeps
    await harness.supervisor.stop()


async def test__start_pairing__stale_identity__forgotten_so_approved_token_registers(tmp_path: Path) -> None:
    harness = Harness(tmp_path, RemoteRunnerSettings(enabled=False, server_url=_URL))
    save_identity(harness.runner_dir, _URL)
    harness.server.statuses = ["pending", "approved"]
    await harness.supervisor.start()

    await harness.supervisor.start_pairing(_URL, "MacBook")

    # Прежняя личность съела бы подтверждённый токен: цикл восстановился бы по ней и не зарегистрировался.
    assert RunnerIdentityStore(harness.runner_dir).load(_URL) is None
    assert harness.supervisor.status().paired is False
    await eventually(lambda: harness.state is RemoteRunnerState.online)
    assert harness.sessions.specs[0].registration_token == PAIRED_TOKEN
    await harness.supervisor.stop()


async def test__apply__server_url_changed_during_pairing__cancels_pairing(harness: Harness) -> None:
    harness.server.statuses = ["pending"]
    await harness.supervisor.start()
    await harness.supervisor.start_pairing(_URL, "MacBook")

    await harness.supervisor.apply(replace(harness.store.settings, server_url="https://other.example.org"))

    status = harness.supervisor.status()
    assert (status.pairing, status.state) == (None, RemoteRunnerState.unpaired)
    polls = harness.server.polls
    await asyncio.sleep(0.05)
    assert harness.server.polls == polls
    assert harness.sessions.specs == []


async def test__apply_patch__merges_over_settings_set_by_pairing(harness: Harness) -> None:
    harness.server.statuses = ["pending"]
    await harness.supervisor.start()
    await harness.supervisor.start_pairing(_URL, "MacBook Анны")

    await harness.supervisor.apply_patch(RemoteRunnerSettingsPatch(concurrency=2))

    settings = harness.store.settings
    assert (settings.enabled, settings.server_url, settings.name, settings.concurrency) == (
        True,
        _URL,
        "MacBook Анны",
        2,
    )
    assert harness.supervisor.status().pairing is not None
    await harness.supervisor.cancel_pairing()


@pytest.mark.parametrize("concurrency", [0, 5])
async def test__apply_patch__concurrency_out_of_range__rejected(harness: Harness, concurrency: int) -> None:
    await harness.supervisor.start()

    with pytest.raises(ValueError, match="concurrency"):
        await harness.supervisor.apply_patch(RemoteRunnerSettingsPatch(concurrency=concurrency))


async def test__start_pairing__server_disabled_personal_runners__raises_disabled(harness: Harness) -> None:
    harness.server.start_error = (403, "runner_disabled")
    await harness.supervisor.start()

    with pytest.raises(RemoteRunnerError) as caught:
        await harness.supervisor.start_pairing(_URL, "MacBook")

    assert caught.value.code is RemoteRunnerErrorCode.disabled
    assert harness.state is RemoteRunnerState.off


async def test__start_pairing__server_down__raises_unreachable(harness: Harness) -> None:
    harness.server.unreachable = True
    await harness.supervisor.start()

    with pytest.raises(RemoteRunnerError) as caught:
        await harness.supervisor.start_pairing(_URL, "MacBook")

    assert caught.value.code is RemoteRunnerErrorCode.unreachable


async def test__cancel_pairing__stops_polling(harness: Harness) -> None:
    harness.server.statuses = ["pending"]
    await harness.supervisor.start()
    await harness.supervisor.start_pairing(_URL, "MacBook")

    await harness.supervisor.cancel_pairing()

    polls = harness.server.polls
    await asyncio.sleep(0.05)
    assert harness.server.polls == polls
    assert harness.state is RemoteRunnerState.unpaired


async def test__use_token__registers_and_forgets_token_after_registration(harness: Harness) -> None:
    await harness.supervisor.start()

    await harness.supervisor.use_token(_URL, " hsrt_pasted ")

    await eventually(lambda: harness.state is RemoteRunnerState.online)
    assert harness.sessions.specs[0].registration_token == "hsrt_pasted"
    assert harness.supervisor.status().paired is True
    # Перезапуск после регистрации идёт по личности, а не по истраченному токену.
    await harness.supervisor.apply(replace(harness.store.settings, concurrency=2))
    await eventually(lambda: len(harness.sessions.specs) == 2)
    assert harness.sessions.specs[1].registration_token is None
    await harness.supervisor.stop()


async def test__registered_without_successful_poll__settings_change_reopens_and_unpair_deregisters(
    harness: Harness,
) -> None:
    # Регистрация прошла, а первый опрос до сервера не дошёл: личность на диске, токен уже истрачен.
    harness.sessions.state_after_start = SessionState.connecting
    await harness.supervisor.start()
    await harness.supervisor.use_token(_URL, "hsrt_pasted")
    await eventually(lambda: RunnerIdentityStore(harness.runner_dir).load(_URL) is not None)

    await harness.supervisor.apply(replace(harness.store.settings, concurrency=2))

    await eventually(lambda: len(harness.sessions.specs) == 2)
    assert harness.sessions.specs[1].registration_token is None
    status = harness.supervisor.status()
    assert (status.state, status.paired) == (RemoteRunnerState.connecting, True)

    await harness.supervisor.unpair()

    assert harness.server.deregistered == [(RUNNER_ID, RUNNER_TOKEN)]
    assert RunnerIdentityStore(harness.runner_dir).load(_URL) is None


async def test__start__saved_identity__opens_session_without_token(tmp_path: Path) -> None:
    harness = Harness(tmp_path, RemoteRunnerSettings(enabled=True, server_url=_URL))
    save_identity(harness.runner_dir, _URL)

    await harness.supervisor.start()

    await eventually(lambda: harness.state is RemoteRunnerState.online)
    assert harness.sessions.specs[0].registration_token is None
    await harness.supervisor.stop()
    assert harness.sessions.sessions[0].stopped is True


async def test__session__unauthorized_with_identity__revoked_identity_forgotten(tmp_path: Path) -> None:
    harness = Harness(tmp_path, RemoteRunnerSettings(enabled=True, server_url=_URL))
    save_identity(harness.runner_dir, _URL)
    harness.sessions.fatal = [RunnerSessionFatal(SessionFatalCode.unauthorized)]

    await harness.supervisor.start()

    await eventually(lambda: harness.state is RemoteRunnerState.revoked)
    status = harness.supervisor.status()
    assert (status.paired, status.detail_code, status.settings.enabled) == (False, "runner_revoked", True)
    assert RunnerIdentityStore(harness.runner_dir).load(_URL) is None


async def test__session__unauthorized_registration_token__error_token_rejected(harness: Harness) -> None:
    harness.sessions.fatal = [RunnerSessionFatal(SessionFatalCode.unauthorized)]
    await harness.supervisor.start()

    await harness.supervisor.use_token(_URL, "hsrt_used")

    await eventually(lambda: harness.state is RemoteRunnerState.error)
    assert harness.supervisor.status().detail_code == "token_rejected"


async def test__session__disabled__waits_and_retries(tmp_path: Path) -> None:
    harness = Harness(tmp_path, RemoteRunnerSettings(enabled=True, server_url=_URL))
    save_identity(harness.runner_dir, _URL)
    harness.sessions.fatal = [RunnerSessionFatal(SessionFatalCode.disabled)]

    await harness.supervisor.start()

    await eventually(lambda: len(harness.sessions.specs) == 2)
    assert 300.0 in harness.sleeps
    await eventually(lambda: harness.state is RemoteRunnerState.online)
    await harness.supervisor.stop()


async def test__listener__paused_state__is_reported(tmp_path: Path) -> None:
    harness = Harness(tmp_path, RemoteRunnerSettings(enabled=True, server_url=_URL))
    save_identity(harness.runner_dir, _URL)
    harness.sessions.state_after_start = SessionState.paused

    await harness.supervisor.start()

    await eventually(lambda: harness.state is RemoteRunnerState.paused)
    await harness.supervisor.stop()


async def test__unpair__deregisters_forgets_identity_and_turns_off(tmp_path: Path) -> None:
    harness = Harness(tmp_path, RemoteRunnerSettings(enabled=True, server_url=_URL))
    save_identity(harness.runner_dir, _URL)
    await harness.supervisor.start()
    await eventually(lambda: harness.state is RemoteRunnerState.online)

    await harness.supervisor.unpair()

    assert harness.server.deregistered == [(RUNNER_ID, RUNNER_TOKEN)]
    assert harness.state is RemoteRunnerState.off
    assert harness.store.settings.enabled is False
    assert RunnerIdentityStore(harness.runner_dir).load(_URL) is None
    assert harness.sessions.sessions[0].stopped is True


async def test__unpair__server_down__still_forgets_locally(tmp_path: Path) -> None:
    harness = Harness(tmp_path, RemoteRunnerSettings(enabled=True, server_url=_URL))
    save_identity(harness.runner_dir, _URL)
    harness.server.unreachable = True
    await harness.supervisor.start()

    await harness.supervisor.unpair()

    assert harness.supervisor.status().paired is False


async def test__apply__yield_to_local_only__keeps_session(tmp_path: Path) -> None:
    harness = Harness(tmp_path, RemoteRunnerSettings(enabled=True, server_url=_URL))
    save_identity(harness.runner_dir, _URL)
    await harness.supervisor.start()
    await eventually(lambda: harness.state is RemoteRunnerState.online)

    await harness.supervisor.apply(replace(harness.store.settings, yield_to_local=False))

    assert len(harness.sessions.specs) == 1
    await harness.supervisor.stop()


async def test__apply__toggle_off__stops_session(tmp_path: Path) -> None:
    harness = Harness(tmp_path, RemoteRunnerSettings(enabled=True, server_url=_URL))
    save_identity(harness.runner_dir, _URL)
    await harness.supervisor.start()
    await eventually(lambda: harness.state is RemoteRunnerState.online)

    await harness.supervisor.apply(replace(harness.store.settings, enabled=False))

    assert harness.sessions.sessions[0].stopped is True
    assert harness.state is RemoteRunnerState.off
    # Личность остаётся: включение снова подключает без нового кода.
    assert harness.supervisor.status().paired is True


@pytest.mark.parametrize("concurrency", [0, 5])
async def test__apply__concurrency_out_of_range__rejected(harness: Harness, concurrency: int) -> None:
    await harness.supervisor.start()

    with pytest.raises(ValueError, match="concurrency"):
        await harness.supervisor.apply(RemoteRunnerSettings(enabled=True, concurrency=concurrency))
