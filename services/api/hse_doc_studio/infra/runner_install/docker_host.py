"""Раннер соседним контейнером через docker.sock Студии: тот же `docker`, что у страницы «Диск»."""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

from hse_doc_studio.core.docker_disk.prune import listed_tags, stale_version_tags
from hse_doc_studio.core.runner_install import (
    Capability,
    InstallError,
    InstallStepState,
    InstallTarget,
    LocalInstance,
    LocalRunnerSpec,
    PreviousRelease,
    ProgressReporter,
    ResourceOverrides,
    UnavailableReason,
    UpgradeError,
    UpgradeOutcome,
)
from hse_doc_studio.infra.docker.cli import docker_available, run_docker

INSTALL_LABEL = "hse-doc-studio.runner-install"
DOCKER_SOCK = "/var/run/docker.sock"
_PULL_TIMEOUT_S = 900.0
_RUN_TIMEOUT_S = 60.0
_PRUNE_TIMEOUT_S = 120.0
# Остановка при обновлении: раннер доделывает сборки до 30 с (drain), потом прерывает их; docker ждёт с запасом.
_STOP_GRACE_S = 60
_STOP_TIMEOUT_S = 120.0
_ENV_PREFIX = "HSE_RUNNER__"
_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{1,62}$")


def _socket_present() -> bool:
    return bool(os.environ.get("DOCKER_HOST")) or Path(DOCKER_SOCK).exists()


def _socket_gid() -> int | None:
    try:
        return Path(DOCKER_SOCK).stat().st_gid
    except OSError:
        return None


def _scrub(text: str, token: str) -> str:
    return text.replace(token, "***") if token else text


class DockerLocalHost:
    target = InstallTarget.docker

    def __init__(self, *, enabled: bool = True, office_url: str = "") -> None:
        self._enabled = enabled
        self._office_url = office_url

    async def capability(self) -> Capability:
        if not self._enabled:
            return Capability.no(UnavailableReason.disabled)
        if not _socket_present():
            return Capability.no(UnavailableReason.no_socket)
        if not await docker_available():
            return Capability.no(UnavailableReason.docker_unreachable)
        return Capability.yes()

    def check_resources(self, overrides: ResourceOverrides | None) -> None:
        """Лимиты формы относятся к Kubernetes; docker-раннер их не получает."""

    def steps(self) -> tuple[str, ...]:
        return ("pull", "start")

    async def install(self, spec: LocalRunnerSpec, report: ProgressReporter) -> None:
        if not _NAME_RE.fullmatch(spec.name):
            raise InstallError("invalid_name")
        await report("pull", InstallStepState.running, spec.image)
        code, _, err = await run_docker(["pull", spec.image], timeout=_PULL_TIMEOUT_S)
        if code != 0:
            raise InstallError("image_pull_failed", _scrub(err.strip()[-400:], spec.token))
        await report("pull", InstallStepState.done, "")

        await report("start", InstallStepState.running, spec.name)
        # Старый контейнер с этим именем заменяем только если он наш.
        if await self._owned(spec.name):
            await run_docker(["rm", "-f", spec.name], timeout=_RUN_TIMEOUT_S)
        env = {
            "HSE_RUNNER__API_URL": spec.api_url,
            "HSE_RUNNER__TOKEN": spec.token,
            "HSE_RUNNER__DATA_DIR": spec.data_dir,
            "HSE_RUNNER__CONCURRENCY": str(spec.concurrency),
            "HSE_RUNNER__NAME": spec.name,
        }
        code, err = await self._run(spec.name, spec.image, spec.data_dir, self._with_office(env))
        if code != 0:
            raise InstallError("container_start_failed", _scrub(err.strip()[-400:], spec.token))
        await report("start", InstallStepState.done, "")

    def _with_office(self, env: dict[str, str]) -> dict[str, str]:
        """Нынешний адрес Gotenberg Студии (офисные задачи); без него у раннера остаётся прежний, если был."""
        return {**env, "HSE_RUNNER__OFFICE_URL": self._office_url} if self._office_url else env

    async def _run(self, name: str, image: str, data_dir: str, env: dict[str, str]) -> tuple[int | None, str]:
        """`docker run` раннера; окружение с токеном идёт файлом 0600, а не аргументами, поэтому в `ps` его нет."""
        fd, path = tempfile.mkstemp(prefix="hds-runner-", suffix=".env")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.writelines(f"{key}={value}\n" for key, value in env.items())
            os.chmod(path, 0o600)  # noqa: PTH101
            args = [
                "run",
                "-d",
                "--name",
                name,
                "--restart",
                "unless-stopped",
                "--label",
                f"{INSTALL_LABEL}=true",
                "--env-file",
                path,
                "-v",
                f"{DOCKER_SOCK}:/var/run/docker.sock",
                "-v",
                # Путь одинаков снаружи и внутри: соседние контейнеры сборки монтируют его по пути хоста.
                f"{data_dir}:{data_dir}",
            ]
            gid = _socket_gid()
            if gid is not None:
                args += ["--group-add", str(gid)]
            args += [image, "hse-doc-studio", "runner"]
            code, _, err = await run_docker(args, timeout=_RUN_TIMEOUT_S)
        finally:
            with contextlib.suppress(OSError):
                Path(path).unlink()
        return code, err

    # ---- обновление на месте ----

    def upgrade_steps(self) -> tuple[str, ...]:
        return ("pull", "recreate")

    async def upgrade(self, name: str, image: str, report: ProgressReporter) -> UpgradeOutcome:
        """Новый образ, тот же контейнер по сути: имя, окружение раннера (токен, адрес, каталог) и том данных прежние.

        Образ тянется до остановки, чтобы простой был только на перезапуск. Старый контейнер получает `docker stop`
        (раннер доделывает сборки до 30 с), затем удаляется и запускается заново. Прежний образ и окружение
        запоминаются до остановки: если новый не стартовал, `UpgradeError` несёт их для `rollback`. Отказ `docker`
        не принимается на веру (ответ мог потеряться по таймауту): Студия смотрит, что на самом деле с контейнером.
        """
        if not _NAME_RE.fullmatch(name) or not await self._owned(name):
            raise InstallError("not_installed")
        await report("pull", InstallStepState.running, image)
        old_image, env = await self._inspect(name)
        token = env.get("HSE_RUNNER__TOKEN", "")
        data_dir = env.get("HSE_RUNNER__DATA_DIR", "")
        if not data_dir:
            raise InstallError("not_installed", "HSE_RUNNER__DATA_DIR")
        # Откат возвращает прежнее окружение как было, новый контейнер получает адрес Gotenberg Студии.
        previous = PreviousRelease(image=old_image, state={"env": dict(env)}) if old_image else None
        env = self._with_office(env)
        code, _, err = await run_docker(["pull", image], timeout=_PULL_TIMEOUT_S)
        if code != 0:
            raise InstallError("image_pull_failed", _scrub(err.strip()[-400:], token))
        await report("pull", InstallStepState.done, f"{old_image} {image}".strip())

        await report("recreate", InstallStepState.running, name)
        await run_docker(["stop", "-t", str(_STOP_GRACE_S), name], timeout=_STOP_TIMEOUT_S)
        code, err = await self._recreate(name, image, data_dir, env)
        if code != 0:
            detail = _scrub(err.strip()[-400:], token)
            # Старый контейнер уже остановлен: без прежнего образа возвращать нечего.
            if previous is None:
                raise InstallError("container_start_failed", detail)
            raise UpgradeError("container_start_failed", detail, previous=previous)
        await report("recreate", InstallStepState.done, "")
        return UpgradeOutcome(old_image=old_image, new_image=image, previous=previous)

    async def prune_old_images(self, image: str, previous_image: str) -> list[str]:
        """Снять теги образа раннера ниже `min(прежняя, новая)`: обе версии остаются для отката (A14).

        `image rm` без `--force`: образ под контейнером (в том числе api Студии на том же Docker) не удаляется, тег
        `rollback-prev` апдейтера и теги без номера версии не трогаются (`stale_version_tags`).
        """
        repo, _, current = image.rpartition(":")
        prev_repo, _, previous = previous_image.rpartition(":")
        if not repo or "/" in current or prev_repo != repo:
            return []
        code, out, _ = await run_docker(["image", "ls", "--format", "{{json .}}", repo], timeout=_PRUNE_TIMEOUT_S)
        if code != 0:
            return []
        removed: list[str] = []
        for tag in stale_version_tags(listed_tags(out, repo), current=current, previous=previous):
            # Занятый образ Docker не отдаст (ненулевой код): он просто остаётся.
            code, _, _ = await run_docker(["image", "rm", f"{repo}:{tag}"], timeout=_PRUNE_TIMEOUT_S)
            if code == 0:
                removed.append(f"{repo}:{tag}")
        return removed

    async def rollback(self, name: str, previous: PreviousRelease) -> None:
        """Контейнер с прежним образом и прежним окружением раннера: тем же `docker run`, что и при обновлении."""
        raw_env = previous.state.get("env")
        env = {str(k): str(v) for k, v in raw_env.items()} if isinstance(raw_env, dict) else {}
        data_dir = env.get("HSE_RUNNER__DATA_DIR", "")
        if not _NAME_RE.fullmatch(name) or not previous.image or not data_dir:
            raise InstallError("not_installed")
        token = env.get("HSE_RUNNER__TOKEN", "")
        if await self._owned(name):
            await run_docker(["stop", "-t", str(_STOP_GRACE_S), name], timeout=_STOP_TIMEOUT_S)
        code, err = await self._recreate(name, previous.image, data_dir, env)
        if code != 0:
            raise InstallError("container_start_failed", _scrub(err.strip()[-400:], token))

    async def _recreate(self, name: str, image: str, data_dir: str, env: dict[str, str]) -> tuple[int | None, str]:
        """`docker rm -f` и `docker run` с образом `image`; код ошибки сверяется с тем, что на самом деле.

        `rm` сообщил об ошибке, а контейнера уже нет: идём дальше. `run` сообщил об ошибке (или не ответил вовремя),
        а контейнер с этим образом работает: замена применилась, это успех.
        """
        code, _, err = await run_docker(["rm", "-f", name], timeout=_RUN_TIMEOUT_S)
        if code != 0 and await self._actual(name) is not None:
            return code, err
        code, err = await self._run(name, image, data_dir, env)
        if code != 0 and await self._actual(name) == (image, True):
            return 0, ""
        return code, err

    async def _actual(self, name: str) -> tuple[str, bool] | None:
        """Образ и «работает ли» контейнера `name` по `docker inspect`; нет контейнера или ответа: None."""
        code, out, _ = await run_docker(["inspect", "--type", "container", name], timeout=_RUN_TIMEOUT_S)
        if code != 0:
            return None
        try:
            item = json.loads(out)[0]
            image = item["Config"]["Image"]
            running = item["State"]["Running"]
        except (ValueError, LookupError, TypeError):
            return None
        return (image, running is True) if isinstance(image, str) else None

    async def _inspect(self, name: str) -> tuple[str, dict[str, str]]:
        """Образ и окружение раннера из `docker inspect`; из окружения берутся только переменные раннера."""
        code, out, _ = await run_docker(["inspect", "--type", "container", name], timeout=_RUN_TIMEOUT_S)
        if code != 0:
            raise InstallError("not_installed")
        try:
            data = json.loads(out)
            config = data[0]["Config"]
        except (ValueError, LookupError, TypeError) as exc:
            raise InstallError("not_installed") from exc
        env: dict[str, str] = {}
        for item in config.get("Env") or []:
            key, sep, value = str(item).partition("=")
            if sep and key.startswith(_ENV_PREFIX):
                env[key] = value
        image = config.get("Image")
        return (image if isinstance(image, str) else ""), env

    async def _owned(self, name: str) -> bool:
        code, out, _ = await run_docker(
            ["ps", "-a", "--filter", f"label={INSTALL_LABEL}=true", "--filter", f"name=^{name}$", "-q"],
            timeout=_RUN_TIMEOUT_S,
        )
        return code == 0 and bool(out.strip())

    async def list_instances(self) -> list[LocalInstance]:
        code, out, _ = await run_docker(
            ["ps", "-a", "--filter", f"label={INSTALL_LABEL}=true", "--format", "{{json .}}"], timeout=_RUN_TIMEOUT_S
        )
        if code != 0:
            return []
        items: list[LocalInstance] = []
        for line in out.splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            items.append(
                LocalInstance(
                    target=self.target,
                    name=str(row.get("Names", "")),
                    image=str(row.get("Image", "")),
                    state=str(row.get("State", "")),
                    created_at=_parse_created(str(row.get("CreatedAt", ""))),
                )
            )
        return items

    async def remove(self, name: str) -> bool:
        if not _NAME_RE.fullmatch(name) or not await self._owned(name):
            return False
        code, _, err = await run_docker(["rm", "-f", name], timeout=_RUN_TIMEOUT_S)
        if code != 0:
            raise InstallError("remove_failed", err.strip()[-400:])
        return True


def _parse_created(raw: str) -> datetime | None:
    # "2026-11-06 12:00:00 +0000 UTC": берём первые три части.
    parts = raw.split()
    if len(parts) < 3:
        return None
    try:
        return datetime.strptime(" ".join(parts[:3]), "%Y-%m-%d %H:%M:%S %z")  # noqa: DTZ007
    except ValueError:
        return None
