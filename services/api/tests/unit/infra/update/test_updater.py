from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

import pytest
from hse_doc_studio.infra.update import updater
from hse_doc_studio.infra.update.updater import build_run_command

# A representative `docker inspect <container>`[0] payload for an all-in-one
# container started by compose, with a custom network, a published port, a
# named data volume, a restart policy and the compose bookkeeping labels.
_CONTAINER: dict[str, Any] = {
    "Name": "/hse-studio",
    "Image": "sha256:oldoldoldold",
    "Config": {
        "Env": [
            "PATH=/usr/local/bin:/usr/bin",
            "HOSTNAME=abc123def456",
            "HSE_STUDIO__SERVER__PORT=8000",
            "HSE_STUDIO__DATA_DIR=/data",
            "LANG=C.UTF-8",  # present in the image defaults too -> must NOT be re-passed
        ],
        "Labels": {
            "com.docker.compose.project": "hse-doc-studio",
            "com.docker.compose.service": "hse-doc-studio",
            "org.opencontainers.image.title": "ignore-me",
        },
    },
    "HostConfig": {
        "PortBindings": {"8000/tcp": [{"HostIp": "", "HostPort": "17240"}]},
        "RestartPolicy": {"Name": "unless-stopped", "MaximumRetryCount": 0},
        "NetworkMode": "hse-doc-studio_default",
        # Ровно то, чем продукт запускается на самом деле: без группы-владельца
        # сокета докер недоступен, без host-gateway на Linux не резолвится имя,
        # по которому до нас ходит ONLYOFFICE.
        "GroupAdd": ["0"],
        "ExtraHosts": ["host.docker.internal:host-gateway"],
    },
    "Mounts": [
        {"Type": "volume", "Name": "hse-studio-data", "Destination": "/data", "RW": True},
        {"Type": "bind", "Source": "/var/run/docker.sock", "Destination": "/var/run/docker.sock", "RW": True},
    ],
}

# The new image's default Env — LANG is a default here, so it should be dropped
# from the re-passed env (the container only added the HSE_STUDIO__* ones).
_NEW_IMAGE: dict[str, Any] = {
    "Config": {"Env": ["PATH=/usr/local/bin:/usr/bin", "LANG=C.UTF-8"]},
}

_NEW_REF = "ghcr.io/alexeyshalaev/hse-doc-studio:0.2.0"

# Папка, которую пользователь выбирает в мастере настройки: с пробелом и
# windows-овским диском — ровно то, что приезжает с реальной машины.
_HOST_DATA_DIR = "C:/Users/user/HSE Studio"


def _flag_values(cmd: list[str], flag: str) -> list[str]:
    """Все значения повторяющегося флага (`-v`, `-e`, `--label`) в команде."""
    return [cmd[i + 1] for i, tok in enumerate(cmd) if tok == flag]


@pytest.fixture
def cmd() -> list[str]:
    return build_run_command(_CONTAINER, _NEW_IMAGE, _NEW_REF)


@pytest.mark.unit
def test__build_run_command__default_container__starts_with_docker_run_detached(cmd: list[str]) -> None:
    assert cmd[:3] == ["docker", "run", "-d"]


@pytest.mark.unit
def test__build_run_command__default_container__ends_with_target_image(cmd: list[str]) -> None:
    assert cmd[-1] == _NEW_REF


@pytest.mark.unit
def test__build_run_command__container_name_has_leading_slash__strips_slash_and_preserves_name(
    cmd: list[str],
) -> None:
    assert "--name" in cmd
    assert cmd[cmd.index("--name") + 1] == "hse-studio"


@pytest.mark.unit
def test__build_run_command__published_port__preserves_port_binding(cmd: list[str]) -> None:
    assert "-p" in cmd
    assert cmd[cmd.index("-p") + 1] == "17240:8000/tcp"


@pytest.mark.unit
def test__build_run_command__restart_policy_set__preserves_restart_flag(cmd: list[str]) -> None:
    assert "--restart" in cmd
    assert cmd[cmd.index("--restart") + 1] == "unless-stopped"


@pytest.mark.unit
def test__build_run_command__custom_network__preserves_network_flag(cmd: list[str]) -> None:
    assert "--network" in cmd
    assert cmd[cmd.index("--network") + 1] == "hse-doc-studio_default"


@pytest.mark.unit
def test__build_run_command__named_volume_and_bind_mounts__preserves_both(cmd: list[str]) -> None:
    mount_values = [cmd[i + 1] for i, tok in enumerate(cmd) if tok == "-v"]
    assert "hse-studio-data:/data" in mount_values
    assert "/var/run/docker.sock:/var/run/docker.sock" in mount_values


@pytest.mark.unit
def test__build_run_command__compose_and_noncompose_labels__reapplies_only_compose_labels(
    cmd: list[str],
) -> None:
    label_values = [cmd[i + 1] for i, tok in enumerate(cmd) if tok == "--label"]
    assert "com.docker.compose.project=hse-doc-studio" in label_values
    assert "com.docker.compose.service=hse-doc-studio" in label_values
    # Non-compose labels are NOT re-applied (the new image carries its own).
    assert not any(v.startswith("org.opencontainers") for v in label_values)


@pytest.mark.unit
def test__build_run_command__hostname_env__drops_it(cmd: list[str]) -> None:
    # Re-passing HOSTNAME would pin the new container to the OLD container id and
    # break self-identification on the next update.
    env_values = [cmd[i + 1] for i, tok in enumerate(cmd) if tok == "-e"]
    assert not any(v.startswith("HOSTNAME=") for v in env_values)


@pytest.mark.unit
def test__build_run_command__path_env__drops_it(cmd: list[str]) -> None:
    env_values = [cmd[i + 1] for i, tok in enumerate(cmd) if tok == "-e"]
    assert not any(v.startswith("PATH=") for v in env_values)


@pytest.mark.unit
def test__build_run_command__env_matches_new_image_default__drops_it(cmd: list[str]) -> None:
    # LANG is identical to the new image's default -> not re-passed.
    env_values = [cmd[i + 1] for i, tok in enumerate(cmd) if tok == "-e"]
    assert "LANG=C.UTF-8" not in env_values


@pytest.mark.unit
def test__build_run_command__runtime_added_env__repasses_it(cmd: list[str]) -> None:
    env_values = [cmd[i + 1] for i, tok in enumerate(cmd) if tok == "-e"]
    assert "HSE_STUDIO__SERVER__PORT=8000" in env_values
    assert "HSE_STUDIO__DATA_DIR=/data" in env_values


@pytest.mark.unit
def test__build_run_command__read_only_mount__gets_ro_suffix() -> None:
    container = {
        "Name": "/ro-test",
        "Config": {"Env": [], "Labels": {}},
        "HostConfig": {},
        "Mounts": [{"Name": "packs", "Destination": "/app/packs", "RW": False}],
    }
    cmd = build_run_command(container, {"Config": {"Env": []}}, "img:1")
    mount_values = [cmd[i + 1] for i, tok in enumerate(cmd) if tok == "-v"]
    assert "packs:/app/packs:ro" in mount_values


@pytest.mark.unit
def test__build_run_command__explicit_host_ip__preserved_in_port_binding() -> None:
    container = {
        "Name": "/ip-test",
        "Config": {"Env": [], "Labels": {}},
        "HostConfig": {"PortBindings": {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "17240"}]}},
        "Mounts": [],
    }
    cmd = build_run_command(container, {"Config": {"Env": []}}, "img:1")
    assert cmd[cmd.index("-p") + 1] == "127.0.0.1:17240:8000/tcp"


@pytest.mark.unit
def test__build_run_command__no_restart_policy__emits_no_restart_flag() -> None:
    container = {
        "Name": "/norestart",
        "Config": {"Env": [], "Labels": {}},
        "HostConfig": {"RestartPolicy": {"Name": "no"}},
        "Mounts": [],
    }
    cmd = build_run_command(container, {"Config": {"Env": []}}, "img:1")
    assert "--restart" not in cmd


# ---------------------------------------------------------------------------
# Точечные правки конфигурации: mounts / env (режим перенастройки)
# ---------------------------------------------------------------------------

# Команда, которую сборщик выдавал до появления точечных правок. Обновление
# версии ходит по тому же коду, что и мастер настройки, поэтому пустые
# `mounts`/`env` обязаны оставить её байт в байт прежней.
_PLAIN_COMMAND: list[str] = [
    "docker",
    "run",
    "-d",
    "--name",
    "hse-studio",
    "--restart",
    "unless-stopped",
    "--network",
    "hse-doc-studio_default",
    "--group-add",
    "0",
    "--add-host",
    "host.docker.internal:host-gateway",
    "-p",
    "17240:8000/tcp",
    "-v",
    "hse-studio-data:/data",
    "-v",
    "/var/run/docker.sock:/var/run/docker.sock",
    "--label",
    "com.docker.compose.project=hse-doc-studio",
    "--label",
    "com.docker.compose.service=hse-doc-studio",
    "-e",
    "HSE_STUDIO__SERVER__PORT=8000",
    "-e",
    "HSE_STUDIO__DATA_DIR=/data",
    _NEW_REF,
]


@pytest.mark.unit
def test__build_run_command__no_mounts_and_no_env__reproduces_the_plain_update_command(cmd: list[str]) -> None:
    assert cmd == _PLAIN_COMMAND


@pytest.mark.unit
def test__build_run_command__empty_mounts_and_env__leave_the_command_unchanged(cmd: list[str]) -> None:
    assert build_run_command(_CONTAINER, _NEW_IMAGE, _NEW_REF, mounts={}, env={}) == cmd


@pytest.mark.unit
def test__build_run_command__mount_for_an_occupied_destination__replaces_the_old_binding() -> None:
    cmd = build_run_command(_CONTAINER, _NEW_IMAGE, _NEW_REF, mounts={"/data": _HOST_DATA_DIR})

    mounts = _flag_values(cmd, "-v")
    assert f"{_HOST_DATA_DIR}:/data" in mounts
    assert "hse-studio-data:/data" not in mounts


@pytest.mark.unit
def test__build_run_command__mount_for_an_occupied_destination__leaves_a_single_binding_for_it() -> None:
    # Суть починки: два `-v` на одну точку докер не примет, контейнер не
    # поднимется вовсе — вместо переезда /data пользователь получит лежащее
    # приложение.
    cmd = build_run_command(_CONTAINER, _NEW_IMAGE, _NEW_REF, mounts={"/data": _HOST_DATA_DIR})

    assert sum(value.endswith(":/data") for value in _flag_values(cmd, "-v")) == 1


@pytest.mark.unit
def test__build_run_command__mount_for_a_free_destination__adds_it_next_to_the_existing_ones() -> None:
    cmd = build_run_command(_CONTAINER, _NEW_IMAGE, _NEW_REF, mounts={"/packs": "C:/packs"})

    mounts = _flag_values(cmd, "-v")
    assert "C:/packs:/packs" in mounts
    assert "hse-studio-data:/data" in mounts


@pytest.mark.unit
def test__build_run_command__env_with_an_unknown_key__adds_the_variable() -> None:
    cmd = build_run_command(_CONTAINER, _NEW_IMAGE, _NEW_REF, env={"HSE_STUDIO__HOST_DATA_DIR": _HOST_DATA_DIR})

    assert f"HSE_STUDIO__HOST_DATA_DIR={_HOST_DATA_DIR}" in _flag_values(cmd, "-e")


@pytest.mark.unit
def test__build_run_command__env_overriding_a_container_variable__drops_the_old_value() -> None:
    cmd = build_run_command(_CONTAINER, _NEW_IMAGE, _NEW_REF, env={"HSE_STUDIO__SERVER__PORT": "9000"})

    values = _flag_values(cmd, "-e")
    assert "HSE_STUDIO__SERVER__PORT=9000" in values
    assert "HSE_STUDIO__SERVER__PORT=8000" not in values


@pytest.mark.unit
def test__build_run_command__env_overriding_a_container_variable__passes_the_key_once() -> None:
    # Какой из двух `-e` с одним ключом победит — деталь реализации докера, а не
    # контракт; опираться на неё, чтобы применить выбор пользователя, нельзя.
    cmd = build_run_command(_CONTAINER, _NEW_IMAGE, _NEW_REF, env={"HSE_STUDIO__SERVER__PORT": "9000"})

    assert sum(value.startswith("HSE_STUDIO__SERVER__PORT=") for value in _flag_values(cmd, "-e")) == 1


# ---------------------------------------------------------------------------
# run_update: перенастройка на текущем образе
# ---------------------------------------------------------------------------

_OLD_IMAGE_ID: str = str(_CONTAINER["Image"])

# `docker inspect` образа, на котором контейнер работает СЕЙЧАС: в режиме
# перенастройки именно он становится целевым.
_OLD_IMAGE: dict[str, Any] = {"Config": {"Env": ["PATH=/usr/local/bin:/usr/bin", "LANG=C.UTF-8"]}}

# Тот же контейнер, но со здоровым состоянием: `_wait_healthy` опрашивает его по
# имени и без этого поля крутил бы опрос до таймаута.
_HEALTHY_CONTAINER: dict[str, Any] = {**_CONTAINER, "State": {"Health": {"Status": "healthy"}}}


class _DockerStub:
    """Подмена `_docker`: записывает команды и отвечает так, будто всё удалось."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self._inspectable: dict[str, dict[str, Any]] = {
            "hse-studio": _HEALTHY_CONTAINER,
            _OLD_IMAGE_ID: _OLD_IMAGE,
            _NEW_REF: _NEW_IMAGE,
        }

    def __call__(self, args: list[str], timeout: float = 0.0) -> tuple[int, str, str]:
        self.calls.append(list(args))
        if args[0] == "inspect":
            found = self._inspectable.get(args[1])
            if found is None:
                return 1, "", f"no such object: {args[1]}"
            return 0, json.dumps([found]), ""
        return 0, "", ""

    @property
    def verbs(self) -> list[str]:
        return [call[0] for call in self.calls]

    @property
    def run_command(self) -> list[str]:
        """Единственный `docker run` сценария — то, чем контейнер пересоздан."""
        return next(call for call in self.calls if call[0] == "run")


@pytest.fixture
def docker(monkeypatch: pytest.MonkeyPatch) -> _DockerStub:
    """Ставит заглушку вместо docker-CLI — иначе тест пошёл бы в реальный демон."""
    stub = _DockerStub()
    monkeypatch.setattr(updater, "_docker", stub)
    return stub


def _reconfigure(
    mounts: Mapping[str, str] | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    return updater.run_update("hse-studio", None, updater._Log(None), mounts=mounts, env=env)


@pytest.mark.unit
def test__run_update__without_a_new_image__never_pulls(docker: _DockerStub) -> None:
    # Перенастройка не меняет версию: тянуть тот же образ — это минуты ожидания
    # и отказ там, где до реестра просто не дотянуться.
    _reconfigure()

    assert "pull" not in docker.verbs


@pytest.mark.unit
def test__run_update__without_a_new_image__recreates_on_the_current_image(docker: _DockerStub) -> None:
    _reconfigure()

    assert docker.run_command[-1] == _OLD_IMAGE_ID


@pytest.mark.unit
def test__run_update__without_a_new_image__healthy_container__reports_success(docker: _DockerStub) -> None:
    assert _reconfigure() == 0


@pytest.mark.unit
def test__run_update__reconfigure_with_mounts__applies_them_to_the_new_container(docker: _DockerStub) -> None:
    _reconfigure(mounts={"/data": _HOST_DATA_DIR})

    assert f"{_HOST_DATA_DIR}:/data" in _flag_values(docker.run_command, "-v")


@pytest.mark.unit
def test__run_update__reconfigure_with_env__applies_it_to_the_new_container(docker: _DockerStub) -> None:
    _reconfigure(env={"HSE_STUDIO__HOST_DATA_DIR": _HOST_DATA_DIR})

    assert f"HSE_STUDIO__HOST_DATA_DIR={_HOST_DATA_DIR}" in _flag_values(docker.run_command, "-e")


@pytest.mark.unit
def test__run_update__with_a_new_image__pulls_it_before_recreating(docker: _DockerStub) -> None:
    updater.run_update("hse-studio", _NEW_REF, updater._Log(None))

    verbs = docker.verbs
    assert verbs.index("pull") < verbs.index("run")


# ---------------------------------------------------------------------------
# CLI: разбор --mount/--env и передача их в run_update
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test__parse_pairs__key_value_entries__parses_them_into_a_mapping() -> None:
    assert updater._parse_pairs(["/data=C:/data", "/packs=C:/packs"], "mount") == {
        "/data": "C:/data",
        "/packs": "C:/packs",
    }


@pytest.mark.unit
def test__parse_pairs__value_contains_an_equals_sign__splits_on_the_first_one_only() -> None:
    # Значение переменной вполне может содержать «=» — base64, query-строка.
    assert updater._parse_pairs(["TOKEN=a=b=c"], "env") == {"TOKEN": "a=b=c"}


@pytest.mark.unit
@pytest.mark.parametrize("entry", ["/data", "=C:/data"], ids=["no-separator", "empty-key"])
def test__parse_pairs__malformed_entry__aborts_the_worker(entry: str) -> None:
    # Проглотить мусор молча — значит пересоздать контейнер без запрошенного
    # маунта: данные уедут в пустой том вместо папки пользователя.
    with pytest.raises(SystemExit):
        updater._parse_pairs([entry], "mount")


@pytest.fixture
def captured_run_update(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_run_update(
        target: str,
        new_image: str | None,
        log: object,
        *,
        mounts: Mapping[str, str] | None = None,
        env: Mapping[str, str] | None = None,
    ) -> int:
        captured.update(target=target, new_image=new_image, mounts=mounts, env=env)
        return 0

    monkeypatch.setattr(updater, "run_update", fake_run_update)
    return captured


@pytest.mark.unit
def test__main__only_the_target_given__runs_update_without_a_new_image(captured_run_update: dict[str, Any]) -> None:
    updater.main(["hse-studio"])

    assert captured_run_update["new_image"] is None


@pytest.mark.unit
def test__main__mount_flag__forwards_the_parsed_mount(captured_run_update: dict[str, Any]) -> None:
    updater.main(["hse-studio", "--mount", f"/data={_HOST_DATA_DIR}"])

    assert captured_run_update["mounts"] == {"/data": _HOST_DATA_DIR}


@pytest.mark.unit
def test__main__env_flag__forwards_the_parsed_variable(captured_run_update: dict[str, Any]) -> None:
    updater.main(["hse-studio", "--env", f"HSE_STUDIO__HOST_DATA_DIR={_HOST_DATA_DIR}"])

    assert captured_run_update["env"] == {"HSE_STUDIO__HOST_DATA_DIR": _HOST_DATA_DIR}


# ---------------------------------------------------------------------------
# Регрессии, найденные живым прогоном мастера настройки.
#
# Пересозданный контейнер поднимался и выглядел здоровым, но терял то, что не
# видно снаружи: членство в группе docker-сокета и объявление host-gateway.
# Приложение при этом переставало собирать документы — причём сразу ПОСЛЕ
# успешного обновления версии, где искать причину никто не станет.


@pytest.mark.unit
def test__build_run_command__container_is_in_the_socket_group__keeps_the_membership(cmd: list[str]) -> None:
    assert _flag_values(cmd, "--group-add") == ["0"]


@pytest.mark.unit
def test__build_run_command__container_declares_host_gateway__keeps_the_declaration(cmd: list[str]) -> None:
    assert _flag_values(cmd, "--add-host") == ["host.docker.internal:host-gateway"]


@pytest.mark.unit
def test__build_run_command__container_without_them__adds_no_empty_flags() -> None:
    bare = {**_CONTAINER, "HostConfig": {}}

    result = build_run_command(bare, _NEW_IMAGE, _NEW_REF)

    assert "--group-add" not in result
    assert "--add-host" not in result


@pytest.mark.unit
def test__run_update__reconfigure__recreates_on_the_image_ref_not_its_digest(monkeypatch) -> None:
    # Перенастройка версию не меняет, и подменять понятную ссылку на sha256
    # незачем: её показывает «О программе», и от неё же отталкивается следующее
    # обновление.
    container = {**_CONTAINER, "Config": {**_CONTAINER["Config"], "Image": "ghcr.io/hse/studio:0.1.0"}}
    commands: list[list[str]] = []

    def fake_docker(args: list[str], timeout: float = 0) -> tuple[int, str, str]:
        commands.append(args)
        if args[0] == "inspect":
            payload = container if args[1] == "hse-studio" else {"Config": {"Env": []}}
            if args[1] == "hse-studio":
                payload = {**container, "State": {"Running": True, "Health": {"Status": "healthy"}}}
            return 0, json.dumps([payload]), ""
        return 0, "", ""

    monkeypatch.setattr(updater, "_docker", fake_docker)

    code = updater.run_update("hse-studio", None, updater._Log(None))

    run_cmd = next(c for c in commands if c[0] == "run")
    assert code == 0
    assert run_cmd[-1] == "ghcr.io/hse/studio:0.1.0"
