"""Сигнал присутствия локальной Студии: что уходит на сервер, а что нет (docs/design/connected-devices.md, раздел 4)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

from hse_doc_studio.core.devices.local import LocalDevice
from hse_doc_studio.core.entities import AIProvider
from hse_doc_studio.core.enums import AIProviderType
from hse_doc_studio.core.git_remote.client import PresenceReply, StudioServerError, StudioServerErrorCode
from hse_doc_studio.core.git_sync.entities import (
    CredentialStatus,
    GitCredential,
    GitCredentialKind,
    PdfUploadRecord,
    StoreRemoteConfig,
    SyncUiState,
)
from hse_doc_studio.core.remote_runner import (
    RemoteAiEndpointInfo,
    RemoteRunnerSettings,
    RemoteRunnerState,
    RemoteRunnerStatusInfo,
)
from hse_doc_studio.use_cases.devices.local_presence import (
    IDLE_INTERVAL_S,
    LocalPresenceService,
    PresenceBoard,
)

CLOUD_PROJECT = "11111111-1111-1111-1111-111111111111"
OTHER_SERVER_PROJECT = "22222222-2222-2222-2222-222222222222"
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
PRIVATE_FOLDER = Path("/Users/alex/секретная-папка/диплом")


def credential(host: str, port: int | None = None) -> GitCredential:
    return GitCredential(
        uuid4(), GitCredentialKind.pat, "l", host, "hse", CredentialStatus.ok, NOW, port=port, origin="device"
    )


class Servers:
    def __init__(self, *credentials: GitCredential) -> None:
        self.credentials = list(credentials)
        self.sent: list[tuple[UUID, dict[str, Any]]] = []
        self.errors: dict[UUID, Exception] = {}
        self.interval = 60
        self.overviews = 0

    async def device_credentials(self) -> list[GitCredential]:
        return self.credentials

    async def send_presence(self, credential_id: UUID, report: dict[str, Any]) -> PresenceReply:
        if credential_id in self.errors:
            raise self.errors[credential_id]
        self.sent.append((credential_id, report))
        return PresenceReply(self.interval, 180)

    async def list_servers(self) -> list[Any]:
        return [
            SimpleNamespace(
                credential_id=c.id, server_url=f"https://{c.host}", host=c.host, account_name="Анна", state="ok"
            )
            for c in self.credentials
        ]

    async def presence_overview(self, credential_id: UUID, device_id: str, project_id: UUID | None) -> dict[str, Any]:
        self.overviews += 1
        return {"online_window_s": 180, "device": None, "others": []}


class Identity:
    async def get(self) -> LocalDevice:
        return LocalDevice("d" * 32, "MacBook Алексея", "MacBook Алексея", custom=False)


class Registry:
    def __init__(self, folders: list[Path]) -> None:
        self.folders = folders

    async def list(self) -> list[Path]:
        return self.folders


class Projects:
    def get(self, folder: Path) -> Any:
        return SimpleNamespace(id=uuid4(), folder=folder)


class Remotes:
    def __init__(self, urls: dict[Path, str]) -> None:
        self.urls = urls

    def read(self, project: Any) -> StoreRemoteConfig | None:
        url = self.urls.get(project.folder)
        return StoreRemoteConfig(url=url) if url else None


class Status:
    def __init__(self, state: SyncUiState = SyncUiState.ahead) -> None:
        self.state = state

    async def view(self, _project: Any) -> Any:
        return SimpleNamespace(
            ui_state=self.state,
            ahead=2,
            behind=0,
            last_sync_at=NOW,
            auto_sync=SimpleNamespace(enabled=True),
            pdf_upload=SimpleNamespace(last=PdfUploadRecord("vkr", NOW, ok=True, detail=str(PRIVATE_FOLDER))),
        )


class Operations:
    def current_for(self, _project_id: UUID) -> None:
        return None


class Supervisor:
    def __init__(self, *, paired: bool = True, endpoints: tuple[RemoteAiEndpointInfo, ...] = ()) -> None:
        self.paired = paired
        self.endpoints = endpoints

    def status(self) -> RemoteRunnerStatusInfo:
        return RemoteRunnerStatusInfo(
            settings=RemoteRunnerSettings(enabled=True),
            state=RemoteRunnerState.online if self.paired else RemoteRunnerState.unpaired,
            paired=self.paired,
            runner_id="5f9f8fde104348e29d9b17298d93152c" if self.paired else None,
            runner_name="MacBook Алексея",
            running_jobs=1,
            ai_endpoints=self.endpoints,
        )


class Providers:
    async def get(self, provider_id: UUID) -> Any:
        return AIProvider(
            id=provider_id,
            name="Ollama",
            type=AIProviderType.ollama,
            api_key="",
            base_url="http://localhost:11434/v1",
            models=[],
            created_at=NOW,
        )


class Lister:
    def __init__(self, models: list[str] | Exception) -> None:
        self.models = models
        self.calls = 0

    async def list_models(self, _provider: Any) -> list[str]:
        self.calls += 1
        if isinstance(self.models, Exception):
            raise self.models
        return self.models


PROVIDER_ID = str(uuid4())


def endpoint(announced: bool = True) -> RemoteAiEndpointInfo:
    return RemoteAiEndpointInfo("ollama", PROVIDER_ID, "ollama", "http://localhost:11434/v1", announced)


def service(
    servers: Servers,
    folders: dict[Path, str] | None = None,
    *,
    supervisor: Supervisor | None = None,
    lister: Lister | None = None,
    board: PresenceBoard | None = None,
    busy: bool = False,
    state: SyncUiState = SyncUiState.ahead,
) -> LocalPresenceService:
    urls = folders or {}
    return LocalPresenceService(
        identity=Identity(),  # type: ignore[arg-type]
        servers=servers,  # type: ignore[arg-type]
        registry=Registry(list(urls)),  # type: ignore[arg-type]
        project_repo=Projects(),  # type: ignore[arg-type]
        store_remotes=Remotes(urls),  # type: ignore[arg-type]
        status=Status(state),  # type: ignore[arg-type]
        operations=Operations(),  # type: ignore[arg-type]
        supervisor=supervisor or Supervisor(),  # type: ignore[arg-type]
        providers=Providers(),  # type: ignore[arg-type]
        model_lister=lister or Lister(["qwen3:4b-instruct"]),  # type: ignore[arg-type]
        busy_building=lambda: busy,
        board=board or PresenceBoard(),
        version="0.6.0",
        os_hint="macos",
        clock=lambda: NOW,
        monotonic=lambda: 1000.0,
    )


async def test__tick__without_a_server_login_nothing_is_sent_and_the_loop_sleeps_briefly() -> None:
    servers = Servers()

    result = await service(servers).tick()

    assert servers.sent == []
    assert (result.sent, result.servers, result.next_in_s) == (0, 0, IDLE_INTERVAL_S)


async def test__report__carries_only_state_metadata_never_paths_or_texts() -> None:
    cloud = credential("studio.example.org")
    servers = Servers(cloud)
    folders = {PRIVATE_FOLDER: f"https://studio.example.org/git/{CLOUD_PROJECT}.git"}

    await service(servers, folders, supervisor=Supervisor(endpoints=(endpoint(),))).tick()

    (_, sent) = servers.sent[0]
    text = json.dumps(sent, ensure_ascii=False)
    assert "Users" not in text
    assert "секретная" not in text
    assert "http://localhost:11434" not in text
    assert set(sent) == {"device_id", "name", "version", "os", "activity", "runner", "endpoints", "projects"}
    assert set(sent["projects"][0]) == {"project_id", "sync", "ahead", "behind", "last_sync_at", "auto_sync", "pdf"}
    assert set(sent["projects"][0]["pdf"]) == {"doc_id", "at", "ok", "code"}


async def test__report__projects_of_other_servers_and_non_cloud_projects_are_left_out() -> None:
    cloud = credential("studio.example.org")
    other = credential("other.example.org")
    servers = Servers(cloud, other)
    folders = {
        Path("/p/a"): f"https://studio.example.org/git/{CLOUD_PROJECT}.git",
        Path("/p/b"): f"https://other.example.org/git/{OTHER_SERVER_PROJECT}.git",
        Path("/p/c"): "https://github.com/alex/thesis.git",
    }

    result = await service(servers, folders).tick()

    by_server = {cid: [p["project_id"] for p in rep["projects"]] for cid, rep in servers.sent}
    assert by_server == {cloud.id: [CLOUD_PROJECT], other.id: [OTHER_SERVER_PROJECT]}
    assert result.sent == 2


async def test__report__activity_building_wins_over_syncing_and_idle_is_default() -> None:
    cloud = credential("studio.example.org")
    folders = {Path("/p/a"): f"https://studio.example.org/git/{CLOUD_PROJECT}.git"}
    busy, syncing, idle = Servers(cloud), Servers(cloud), Servers(cloud)

    await service(busy, folders, busy=True, state=SyncUiState.syncing).tick()
    await service(syncing, folders, state=SyncUiState.syncing).tick()
    await service(idle, folders).tick()

    assert [s.sent[0][1]["activity"] for s in (busy, syncing, idle)] == ["building", "syncing", "idle"]


async def test__report__models_come_from_a_live_probe_and_unreachable_model_is_reported_as_such() -> None:
    cloud = credential("studio.example.org")
    ok, down = Servers(cloud), Servers(cloud)
    pair = Supervisor(endpoints=(endpoint(),))

    await service(ok, supervisor=pair, lister=Lister(["a", "b"])).tick()
    await service(down, supervisor=pair, lister=Lister(RuntimeError("refused"))).tick()

    assert ok.sent[0][1]["endpoints"] == [
        {"name": "ollama", "flavor": "ollama", "reachable": True, "models": ["a", "b"]}
    ]
    assert down.sent[0][1]["endpoints"][0]["reachable"] is False
    assert down.sent[0][1]["endpoints"][0]["models"] == []


async def test__report__endpoint_not_announced_to_the_server_is_not_claimed() -> None:
    cloud = credential("studio.example.org")
    servers = Servers(cloud)

    await service(servers, supervisor=Supervisor(endpoints=(endpoint(announced=False),))).tick()

    assert servers.sent[0][1]["endpoints"] == []


async def test__report__model_probe_is_cached_between_servers_and_ticks() -> None:
    first, second = credential("a.example.org"), credential("b.example.org")
    servers = Servers(first, second)
    lister = Lister(["m"])
    pair = Supervisor(endpoints=(endpoint(),))
    svc = service(servers, supervisor=pair, lister=lister)

    await svc.tick()
    await svc.tick()

    assert lister.calls == 1


async def test__report__unpaired_studio_sends_no_runner() -> None:
    servers = Servers(credential("studio.example.org"))

    await service(servers, supervisor=Supervisor(paired=False)).tick()

    assert servers.sent[0][1]["runner"] is None


async def test__tick__failure_of_one_server_does_not_stop_the_others_and_is_remembered() -> None:
    good, bad = credential("good.example.org"), credential("bad.example.org")
    servers = Servers(good, bad)
    servers.errors[bad.id] = StudioServerError(StudioServerErrorCode.unreachable)
    board = PresenceBoard()

    result = await service(servers, board=board).tick()

    assert (result.sent, result.failed) == (1, 1)
    assert board.sent[good.id].ok is True
    assert (board.sent[bad.id].ok, board.sent[bad.id].code) == (False, "git_server_unreachable")
    assert result.next_in_s >= 60


async def test__tick__interval_comes_from_the_server_within_sane_bounds() -> None:
    servers = Servers(credential("studio.example.org"))

    servers.interval = 5
    low = await service(servers).tick()
    servers.interval = 90
    mid = await service(servers).tick()
    servers.interval = 99999
    high = await service(servers).tick()

    assert (low.next_in_s, mid.next_in_s, high.next_in_s) == (15, 90, 300)


async def test__link__shows_every_server_with_the_cloud_view_cached_for_a_moment() -> None:
    cloud = credential("studio.example.org")
    servers = Servers(cloud)
    svc = service(servers, supervisor=Supervisor(endpoints=(endpoint(),)))

    first = await svc.link(None)
    await svc.link(None)

    assert [s.host for s in first.servers] == ["studio.example.org"]
    assert first.servers[0].cloud == {"online_window_s": 180, "device": None, "others": []}
    assert first.device.name == "MacBook Алексея"
    assert first.runner.paired is True
    assert [e.name for e in first.endpoints] == ["ollama"]
    assert servers.overviews == 1
