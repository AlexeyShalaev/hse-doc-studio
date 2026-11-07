"""Docker и движки на удалённой машине через SSH-сеанс общего слоя установки (infra/runner_install).

Свой SSH-слоя здесь нет: соединение, проверка отпечатка, SSRF и учётные данные приходят из `SshInstallService`.
Секреты едут только через stdin (файл с правами 0600 на хосте удаляется сразу после `docker run`), не в аргументах.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import AsyncIterator

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.model_servers import (
    LABEL_SERVER,
    ContainerInfo,
    ContainerRunError,
    ContainerSpec,
    Engine,
    PullProgress,
    RemoteRuntime,
)
from hse_doc_studio.core.runner_install import ISshSession
from hse_doc_studio.infra.model_servers.docker_runtime import run_args
from hse_doc_studio.use_cases.runner_install.ssh_service import SshInstallService

_PLACEHOLDER = "@@ENVFILE@@"
_MAX_ERROR_LEN = 400
_SHORT = 60.0
_RUN_TIMEOUT = 1800.0  # первый запуск тянет образ на несколько гигабайт
_INSPECT = "{{.Name}}\t{{.State.Running}}\t{{.State.Status}}\t{{.Config.Image}}\t{{json .Config.Labels}}"


def _scrub(text: str, secrets: list[str]) -> str:
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text.strip()[:_MAX_ERROR_LEN]


class SshContainerRuntime:
    """`IContainerRuntime` поверх ISshSession. `sudo`/`sudo_stdin` приходят от общего слоя."""

    def __init__(self, conn: ISshSession, *, sudo: str, sudo_stdin: str, public_host: str) -> None:
        self._conn = conn
        self._sudo = sudo
        self._stdin = sudo_stdin
        self._public_host = public_host

    async def _docker(self, args: list[str], *, timeout: float = _SHORT, stdin: str = "") -> tuple[int, str, str]:
        result = await self._conn.run(
            f"{self._sudo}docker {shlex.join(args)}", stdin=(self._stdin + stdin) or None, timeout=timeout
        )
        return result.code, result.stdout, result.stderr

    async def available(self) -> bool:
        code, _out, _err = await self._docker(["version", "--format", "{{.Server.Version}}"])
        return code == 0

    async def run(self, spec: ContainerSpec) -> str:
        secrets = list(spec.secret_env.values())
        env_content = "".join(f"{k}={v}\n" for k, v in spec.secret_env.items())

        async def attempt(*, gpu: bool) -> tuple[int, str, str]:
            args = run_args(spec, None, _PLACEHOLDER if env_content else None, gpu=gpu)
            line = shlex.join(["docker", *args]).replace(_PLACEHOLDER, '"$f"')
            if env_content:
                script = f'umask 077; f=$(mktemp) || exit 1; cat >"$f"; {line}; rc=$?; rm -f "$f"; exit $rc'
            else:
                script = line
            result = await self._conn.run(
                f"{self._sudo}sh -c {shlex.quote(script)}",
                stdin=(self._stdin + env_content) or None,
                timeout=_RUN_TIMEOUT,
            )
            return result.code, result.stdout, result.stderr

        code, out, err = await attempt(gpu=spec.gpu)
        if code != 0 and spec.gpu and spec.gpu_optional:
            await self._docker(["rm", "-f", spec.name])
            code, out, err = await attempt(gpu=False)
        if code != 0:
            raise ContainerRunError(_scrub(err or out or "docker run failed", secrets))
        return out.strip()

    async def inspect(self, name: str) -> ContainerInfo | None:
        found = await self._inspect([name])
        return found[0] if found else None

    async def list_managed(self) -> list[ContainerInfo]:
        code, out, _err = await self._docker(
            ["ps", "-a", "--filter", f"label={LABEL_SERVER}", "--format", "{{.Names}}"]
        )
        names = [n.strip() for n in out.splitlines() if n.strip()] if code == 0 else []
        return await self._inspect(names) if names else []

    async def _inspect(self, names: list[str]) -> list[ContainerInfo]:
        code, out, _err = await self._docker(["inspect", "--format", _INSPECT, *names])
        if code != 0:
            return []
        found: list[ContainerInfo] = []
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) != 5:  # noqa: PLR2004 — шаблон выше
                continue
            try:
                labels = json.loads(parts[4]) or {}
            except ValueError:
                labels = {}
            found.append(ContainerInfo(parts[0].lstrip("/"), parts[1] == "true", parts[2], parts[3], labels))
        return found

    async def start(self, name: str) -> bool:
        return (await self._docker(["start", name]))[0] == 0

    async def stop(self, name: str) -> bool:
        return (await self._docker(["stop", name]))[0] == 0

    async def remove(self, name: str, *, volume: str | None = None) -> bool:
        code = (await self._docker(["rm", "-f", name]))[0]
        if volume:
            await self._docker(["volume", "rm", volume])
        return code == 0

    async def logs(self, name: str, tail: int) -> str:
        code, out, err = await self._docker(["logs", "--tail", str(tail), name])
        return (out + err) if code == 0 else ""

    async def endpoint(self, name: str, port: int) -> str | None:
        """Адрес, по которому сервер виден с самой машины (для проверок) либо снаружи, если открыт."""
        return f"http://{self._public_host}:{port}" if self._public_host else f"http://127.0.0.1:{port}"


class SshModelServerClient:
    """Проверки движка через `curl` на самой удалённой машине: loopback хоста Студии недоступен."""

    def __init__(self, conn: ISshSession, runtime: SshContainerRuntime, container: str, port: int) -> None:
        self._conn = conn
        self._runtime = runtime
        self._container = container
        self._port = port

    async def healthy(self, base_url: str, health_path: str, api_key: str = "") -> bool:
        result = await self._conn.run(
            f"curl -sf -o /dev/null --max-time 5 http://127.0.0.1:{self._port}{shlex.quote(health_path)}", timeout=20
        )
        return result.code == 0

    async def installed_models(self, engine: Engine, base_url: str, api_key: str = "") -> list[str]:
        return []

    async def pull(self, base_url: str, model: str) -> AsyncIterator[PullProgress]:
        code, out, err = await self._runtime._docker(  # noqa: SLF001 — один пакет
            ["exec", self._container, "ollama", "pull", model], timeout=7200
        )
        if code != 0:
            yield PullProgress("", error=_scrub(err or out, [])[:200])
            return
        yield PullProgress("success", percent=100, done=True)

    async def delete_model(self, base_url: str, model: str) -> bool:
        code = (await self._runtime._docker(["exec", self._container, "ollama", "rm", model]))[0]  # noqa: SLF001
        return code == 0

    async def ping(self, base_url: str, model: str, api_key: str = "") -> bool:
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 1})
        header = f"Authorization: Bearer {api_key}\n" if api_key else "X-None: 1\n"
        result = await self._conn.run(
            "curl -s -o /dev/null -w '%{http_code}' --max-time 120 -H 'Content-Type: application/json' -H @- "
            f"-d {shlex.quote(body)} http://127.0.0.1:{self._port}/v1/chat/completions",
            stdin=header,
            timeout=150,
        )
        return result.code == 0 and result.stdout.strip() == "200"


class SshRuntimeFactory:
    """Открывает Docker на удалённой машине по сохранённому доступу, через общий слой `SshInstallService`."""

    def __init__(self, ssh: SshInstallService) -> None:
        self._ssh = ssh

    async def open(self, actor: Actor, credential_id: str, public_host: str) -> RemoteRuntime:
        conn = await self._ssh.open_saved(actor, credential_id)
        sudo, stdin = await self._ssh.saved_sudo(credential_id)
        return RemoteRuntime(
            SshContainerRuntime(conn, sudo=sudo, sudo_stdin=stdin, public_host=public_host), conn.close
        )


def build_remote(
    conn: ISshSession, sudo: str, sudo_stdin: str, public_host: str, container: str, port: int
) -> tuple[SshContainerRuntime, SshModelServerClient]:
    runtime = SshContainerRuntime(conn, sudo=sudo, sudo_stdin=sudo_stdin, public_host=public_host)
    return runtime, SshModelServerClient(conn, runtime, container, port)
