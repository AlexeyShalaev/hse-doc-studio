"""Self-update worker — runs INSIDE a detached "updater" container.

Invoked as a one-shot process (the backend that spawns it is recreated and
dies mid-run, so this must outlive it):

    python -m hse_doc_studio.infra.update.updater <target_container> <new_image> [--log-file PATH]

It records the running container's image digest, pulls the target image,
recreates the container with the *same* runtime config (ports, mounts, env,
restart policy, network, compose labels) on the new image, waits for health,
and rolls back to the recorded digest if the new container doesn't become
healthy.

Pure stdlib only (subprocess + json) — it must run with nothing but the docker
CLI available, and the config-reconstruction logic stays unit-testable in
isolation. See `build_run_command`.
"""

from __future__ import annotations

import argparse
import json
import subprocess  # noqa: S404 — this module IS a thin docker-CLI driver
import sys
import time
from collections.abc import Iterable, Mapping
from typing import Any

_PULL_TIMEOUT_S = 900.0
_DOCKER_TIMEOUT_S = 60.0
_HEALTH_TIMEOUT_S = 120.0
_HEALTH_POLL_INTERVAL_S = 2.0
_RUNNING_STABLE_S = 5.0


# ---------------------------------------------------------------------------
# Pure config reconstruction (unit-tested)
# ---------------------------------------------------------------------------


def _ports_args(host_config: dict[str, Any]) -> list[str]:
    args: list[str] = []
    for port_proto, bindings in (host_config.get("PortBindings") or {}).items():
        for binding in bindings or []:
            host_port = binding.get("HostPort") or ""
            if not host_port:
                continue
            host_ip = binding.get("HostIp") or ""
            if host_ip and host_ip not in ("0.0.0.0", "::"):  # noqa: S104 — matching docker's wildcard, not binding
                args += ["-p", f"{host_ip}:{host_port}:{port_proto}"]
            else:
                args += ["-p", f"{host_port}:{port_proto}"]
    return args


def _mount_args(
    mounts: Iterable[dict[str, Any]] | None,
    extra: Mapping[str, str] | None = None,
) -> list[str]:
    """`-v` для пересоздания. `extra` — «каталог в контейнере → путь на хосте».

    Пункт из `extra` ЗАМЕЩАЕТ существующий маунт с той же точкой назначения:
    мастер настройки переселяет `/data` в выбранную пользователем папку, и два
    `-v` на одну точку докер не примет.
    """
    resolved: dict[str, str] = {}
    for mount in mounts or []:
        dst = mount.get("Destination")
        src = mount.get("Name") or mount.get("Source")
        if not dst or not src:
            continue
        suffix = "" if mount.get("RW", True) else ":ro"
        resolved[dst] = f"{src}:{dst}{suffix}"
    for dst, host in (extra or {}).items():
        resolved[dst] = f"{host}:{dst}"
    args: list[str] = []
    for spec in resolved.values():
        args += ["-v", spec]
    return args


def _env_args(
    container_env: Iterable[str] | None,
    image_env: Iterable[str] | None,
    extra: Mapping[str, str] | None = None,
) -> list[str]:
    # Re-pass only the env the runtime ADDED on top of the new image's defaults,
    # so we don't clobber image defaults. Drop HOSTNAME (docker pins it to the
    # old container id — re-passing would break self-identification on the next
    # update) and PATH (container-runtime default).
    image_set = set(image_env or [])
    overridden = set(extra or {})
    args: list[str] = []
    for entry in container_env or []:
        if entry in image_set or entry.startswith(("HOSTNAME=", "PATH=")):
            continue
        # Переменную, которую переопределяет мастер настройки, старым значением
        # не переносим — иначе в команде окажутся два `-e` с одним ключом.
        if entry.split("=", 1)[0] in overridden:
            continue
        args += ["-e", entry]
    for key, value in (extra or {}).items():
        args += ["-e", f"{key}={value}"]
    return args


def _restart_args(host_config: dict[str, Any]) -> list[str]:
    policy = host_config.get("RestartPolicy") or {}
    name = policy.get("Name") or ""
    if not name or name == "no":
        return []
    if name == "on-failure" and policy.get("MaximumRetryCount"):
        return ["--restart", f"on-failure:{policy['MaximumRetryCount']}"]
    return ["--restart", name]


def _network_args(host_config: dict[str, Any]) -> list[str]:
    mode = host_config.get("NetworkMode") or ""
    if mode in ("", "default", "bridge"):
        return []
    return ["--network", mode]


def _group_args(host_config: dict[str, Any]) -> list[str]:
    """`--group-add` — без него пересозданный контейнер теряет доступ к докеру.

    Процесс внутри непривилегированный, а сокет приезжает с правами владельца с
    хоста: членство в его группе — единственное, что позволяет вообще позвать
    докера. Пропустив его при пересоздании, мы получали приложение, которое
    поднялось и выглядит здоровым, но не собирает ни одного документа — причём
    ровно после успешного обновления версии.
    """
    return [arg for group in host_config.get("GroupAdd") or [] for arg in ("--group-add", str(group))]


def _extra_host_args(host_config: dict[str, Any]) -> list[str]:
    """`--add-host` — на Linux только так резолвится host.docker.internal.

    Через это имя до нас ходит ONLYOFFICE и по нему же мы достаём службы,
    поднятые пользователем на своей машине. Docker Desktop резолвит его сам, а
    на Linux без явного объявления имя просто не существует.
    """
    return [arg for entry in host_config.get("ExtraHosts") or [] for arg in ("--add-host", str(entry))]


def _label_args(labels: dict[str, str] | None) -> list[str]:
    # Re-apply compose's bookkeeping labels so the recreated container is still
    # adopted by its original compose project (no orphan stack).
    args: list[str] = []
    for key, value in (labels or {}).items():
        if key.startswith("com.docker.compose."):
            args += ["--label", f"{key}={value}"]
    return args


def build_run_command(
    container: dict[str, Any],
    image_inspect: dict[str, Any],
    image_ref: str,
    *,
    mounts: Mapping[str, str] | None = None,
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """Reconstruct a `docker run -d ...` command to recreate `container` on `image_ref`.

    `mounts` («каталог в контейнере → путь на хосте») и `env` — точечные правки
    поверх скопированной конфигурации. Без них команда воспроизводит контейнер
    один в один, как при обновлении версии; с ними тот же механизм применяет
    выбор пользователя в мастере первоначальной настройки. Второго пути для
    этого заводить нельзя: пересоздание себя с откатом по здоровью — вещь,
    которую надо иметь ровно в одном экземпляре.
    """
    config = container.get("Config") or {}
    host_config = container.get("HostConfig") or {}
    name = (container.get("Name") or "").lstrip("/")
    image_env = (image_inspect.get("Config") or {}).get("Env") or []

    cmd = ["docker", "run", "-d"]
    if name:
        cmd += ["--name", name]
    cmd += _restart_args(host_config)
    cmd += _network_args(host_config)
    cmd += _group_args(host_config)
    cmd += _extra_host_args(host_config)
    cmd += _ports_args(host_config)
    cmd += _mount_args(container.get("Mounts"), mounts)
    cmd += _label_args(config.get("Labels"))
    cmd += _env_args(config.get("Env"), image_env, env)
    cmd += [image_ref]
    return cmd


# ---------------------------------------------------------------------------
# Orchestration (runs against the real docker daemon)
# ---------------------------------------------------------------------------


class _Log:
    def __init__(self, path: str | None) -> None:
        self._fh = None
        if path:
            try:
                self._fh = open(path, "a", encoding="utf-8")  # noqa: SIM115, PTH123
            except OSError:
                self._fh = None

    def __call__(self, message: str) -> None:
        line = f"[updater] {message}"
        print(line, flush=True)  # noqa: T201 — this is a CLI worker; stdout IS the log
        if self._fh is not None:
            self._fh.write(line + "\n")
            self._fh.flush()


def _docker(args: list[str], timeout: float = _DOCKER_TIMEOUT_S) -> tuple[int, str, str]:
    # `docker` is resolved via PATH (S607): the updater runs in our own image
    # where the CLI is on PATH; an absolute path would vary across base images.
    cmd = ["docker", *args]  # noqa: S607
    try:
        proc = subprocess.run(  # noqa: S603 — args are constructed, never shell
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, "", str(exc)
    return proc.returncode, proc.stdout, proc.stderr


def _inspect(ref: str) -> dict[str, Any] | None:
    rc, out, _err = _docker(["inspect", ref])
    if rc != 0:
        return None
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None
    return data[0] if isinstance(data, list) and data else None


def _wait_healthy(name: str, log: _Log) -> bool:
    deadline = time.monotonic() + _HEALTH_TIMEOUT_S
    running_since: float | None = None
    while time.monotonic() < deadline:
        info = _inspect(name)
        state = (info or {}).get("State") or {}
        health = state.get("Health") or {}
        status = health.get("Status")
        if status == "healthy":
            log("container is healthy")
            return True
        if status in ("starting", "unhealthy"):
            running_since = None  # has a healthcheck — trust it, keep waiting
        elif state.get("Running"):
            # No healthcheck: accept once it's stayed up for a few seconds.
            if running_since is None:
                running_since = time.monotonic()
            elif time.monotonic() - running_since >= _RUNNING_STABLE_S:
                log("container running and stable (no healthcheck)")
                return True
        else:
            running_since = None
        time.sleep(_HEALTH_POLL_INTERVAL_S)
    log("timed out waiting for the container to become healthy")
    return False


def _recreate(name: str, cmd: list[str], log: _Log) -> bool:
    log(f"stopping {name}")
    _docker(["stop", name])
    _docker(["rm", "-f", name])
    log(f"running: {' '.join(cmd)}")
    rc, _out, err = _docker(cmd[1:])  # cmd starts with "docker"
    if rc != 0:
        log(f"docker run failed: {err.strip()}")
        return False
    return True


def _pull(image: str, log: _Log) -> dict[str, Any] | None:
    """Скачать образ и вернуть его inspect; None — не трогаем контейнер вовсе."""
    log(f"pulling {image}")
    rc, _out, err = _docker(["pull", image], timeout=_PULL_TIMEOUT_S)
    if rc != 0:
        log(f"pull failed, nothing changed: {err.strip()}")
        return None
    pulled = _inspect(image)
    if pulled is None:
        log("pulled image not inspectable — aborting before touching the container")
    return pulled


def run_update(  # noqa: PLR0911 — each failure mode returns a distinct exit code
    target: str,
    new_image: str | None,
    log: _Log,
    *,
    mounts: Mapping[str, str] | None = None,
    env: Mapping[str, str] | None = None,
) -> int:
    """Пересоздать контейнер приложения: с новым образом, с новой конфигурацией или и то и другое.

    `new_image is None` — режим перенастройки: образ остаётся текущим, меняются
    только бинды и переменные. Скачивать при этом нечего, а всё остальное —
    подмена с ожиданием здоровья и откатом на прежнюю конфигурацию — работает
    ровно так же, как при обновлении версии.
    """
    container = _inspect(target)
    if container is None:
        log(f"target container not found: {target}")
        return 2
    old_image_id = container.get("Image")
    old_image_inspect = _inspect(old_image_id) if old_image_id else None
    if not old_image_id or old_image_inspect is None:
        log("could not determine current image — aborting")
        return 2

    if new_image is None:
        log("reconfiguring on the current image, no pull needed")
        # Ссылка, какой её задали при запуске (`ghcr.io/...:latest`), а не
        # разрешённый id: перенастройка не меняет версию, и подменять понятную
        # ссылку на sha256 незачем — её потом показывает «О программе» и от неё
        # же отталкивается следующее обновление.
        target_inspect = old_image_inspect
        target_image = (container.get("Config") or {}).get("Image") or old_image_id
    else:
        pulled = _pull(new_image, log)
        if pulled is None:
            return 3
        target_image, target_inspect = new_image, pulled

    new_cmd = build_run_command(container, target_inspect, target_image, mounts=mounts, env=env)
    if not _recreate(target, new_cmd, log):
        log("recreate failed — attempting rollback")
        return _rollback(container, old_image_id, old_image_inspect, log)

    if _wait_healthy((container.get("Name") or "").lstrip("/"), log):
        log(f"recreated on {target_image} successfully")
        return 0

    log("new container unhealthy — rolling back")
    return _rollback(container, old_image_id, old_image_inspect, log)


def _rollback(
    container: dict[str, Any],
    old_image_id: str,
    old_image_inspect: dict[str, Any],
    log: _Log,
) -> int:
    name = (container.get("Name") or "").lstrip("/")
    old_cmd = build_run_command(container, old_image_inspect, old_image_id)
    if not _recreate(name, old_cmd, log):
        log("ROLLBACK FAILED — stack is down; run `docker compose up -d` manually")
        return 5
    if _wait_healthy(name, log):
        log("rolled back to the previous version")
        return 4
    log("rolled back but previous version is unhealthy too — check the host")
    return 5


def _parse_pairs(raw: list[str] | None, what: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for entry in raw or []:
        key, sep, value = entry.partition("=")
        if not sep or not key:
            msg = f"malformed --{what} (expected KEY=VALUE): {entry!r}"
            raise SystemExit(msg)
        pairs[key] = value
    return pairs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="hse-studio self-update worker")
    parser.add_argument("target", help="name or id of the running app container to replace")
    parser.add_argument(
        "new_image",
        nargs="?",
        default=None,
        help="image ref to update to; omit to keep the current image and only change the config",
    )
    parser.add_argument(
        "--mount",
        action="append",
        metavar="CONTAINER_PATH=HOST_PATH",
        help="bind-mount to add or replace (repeatable)",
    )
    parser.add_argument(
        "--env",
        action="append",
        metavar="KEY=VALUE",
        help="environment variable to set or override (repeatable)",
    )
    parser.add_argument("--log-file", default=None)
    args = parser.parse_args(argv)

    mounts = _parse_pairs(args.mount, "mount")
    env = _parse_pairs(args.env, "env")

    log = _Log(args.log_file)
    log(f"recreate started: {args.target} -> {args.new_image or 'same image'}")
    if mounts:
        log(f"mounts: {mounts}")
    if env:
        log(f"env: {sorted(env)}")
    code = run_update(args.target, args.new_image, log, mounts=mounts, env=env)
    log(f"recreate finished with code {code}")
    return code


if __name__ == "__main__":
    sys.exit(main())
