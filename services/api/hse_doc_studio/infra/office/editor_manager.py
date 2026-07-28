from __future__ import annotations

import asyncio
import json
import secrets
import socket
import time
from asyncio import subprocess as asubprocess
from contextlib import suppress
from pathlib import Path
from typing import Any

import httpx
import structlog

from hse_doc_studio.infra.docker.cli import docker_binary, managed_label_args
from hse_doc_studio.infra.docker.siblings import SiblingNetwork

logger = structlog.get_logger()

# Конфиг Document Server (node-config): local.json переопределяет default.json.
# Стартовый скрипт образа пишет туда JWT-ключи один раз при старте контейнера —
# в рантайме конкурирующих писателей нет, безопасно перезаписывать целиком.
_DS_LOCAL_CONFIG = "/etc/onlyoffice/documentserver/local.json"

_PS_TIMEOUT_S = 10.0
_INSPECT_TIMEOUT_S = 5.0
_VERSION_TIMEOUT_S = 5.0
_RUN_TIMEOUT_S = 60.0
_START_TIMEOUT_S = 30.0
_STOP_TIMEOUT_S = 30.0
_RM_TIMEOUT_S = 30.0
_EXEC_TIMEOUT_S = 15.0
_HEALTH_POLL_INTERVAL_S = 1.0
_REAPER_INTERVAL_S = 30.0


class OfficeEditorManager:
    """Auto-manages an on-demand ONLYOFFICE Document Server container.

    Даёт in-app редактирование pptx-презентации: DS встраивается фронтом через
    свой JS API, а правки прилетают колбэком в бэкенд и пишутся через put-file
    (значит — попадают в ProjectVCS). Жизненный цикл — как у Gotenberg
    (`infra/office/convert_manager.py`): контейнер поднимается лениво на
    свободном порту при первом открытии редактора, гасится reaper'ом после
    простоя; opt-in — установленный образ (`docker pull
    onlyoffice/documentserver`), тумблера и URL в настройках нет.

    Отличия от Gotenberg-блюпринта:
    - JWT: контейнер стартует с JWT_ENABLED и общим секретом, который живёт в
      `<data_dir>/office-editor-jwt.secret` — усыновлённый после рестарта
      бэкенда контейнер продолжает валидировать те же токены;
    - `--add-host=host.docker.internal:host-gateway` — DS должен сам ходить в
      НАШ бэкенд (скачать документ, отдать сохранение), на Linux без этого
      host.docker.internal не резолвится;
    - активные сессии: reaper не гасит контейнер, пока открыт хоть один
      редактор (набор активных document key + touch()-keepalive от вкладки);
    - шрифты монтируются в fontconfig-путь DS и после ПЕРВОГО старта нового
      контейнера пинается пересборка шрифтового кэша DS (best-effort), чтобы
      HSE Sans / Times New Roman появились в списке шрифтов редактора.
    """

    def __init__(
        self,
        *,
        image: str,
        container_name: str,
        container_port: int,
        health_path: str,
        health_timeout_s: float,
        startup_timeout_s: float,
        idle_timeout_s: float,
        secret_path: Path,
        fonts_dir: Path | None,
        fonts_host_dir: str | None,
        client: httpx.Client,
        siblings: SiblingNetwork,
    ) -> None:
        self._image = image
        self._name = container_name
        self._container_port = container_port
        self._health_path = health_path
        self._health_timeout_s = health_timeout_s
        self._startup_timeout_s = startup_timeout_s
        self._idle_timeout_s = idle_timeout_s
        self._secret_path = secret_path
        self._fonts_dir = fonts_dir
        self._fonts_host_dir = fonts_host_dir
        self._client = client
        self._jwt_secret: str | None = None
        self._siblings = siblings
        # ДВА адреса, и это не дубль: `_base_url` уезжает в браузер (он грузит
        # api.js прямо с DS), поэтому обязан оставаться опубликованным портом
        # хоста. `_internal_base_url` — для запросов САМОГО бэкенда (health,
        # правка конфига): из контейнера опубликованный loopback недостижим.
        self._base_url: str | None = None
        self._internal_base_url: str | None = None
        self._last_used: float | None = None
        self._active_keys: set[str] = set()
        self._lock = asyncio.Lock()

    # ── public state ────────────────────────────────────────────────────────

    @property
    def image(self) -> str:
        return self._image

    @property
    def base_url(self) -> str | None:
        """Current published base URL (None until ensure_running succeeded)."""
        return self._base_url

    @property
    def jwt_secret(self) -> str:
        """Shared DS JWT secret, persisted at `<data_dir>/office-editor-jwt.secret`.

        Создаётся один раз (secrets.token_urlsafe) и переиспользуется всегда:
        контейнер, усыновлённый после рестарта бэкенда, был запущен со старым
        секретом и обязан продолжать валидировать наши токены.
        """
        if self._jwt_secret is None:
            self._jwt_secret = self._load_or_create_secret()
        return self._jwt_secret

    def _load_or_create_secret(self) -> str:
        try:
            existing = self._secret_path.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        except OSError:
            pass
        secret = secrets.token_urlsafe(32)
        try:
            self._secret_path.parent.mkdir(parents=True, exist_ok=True)
            self._secret_path.write_text(secret, encoding="utf-8")
        except OSError as exc:
            # Без персиста секрет доживёт до рестарта бэкенда — редактор
            # работает, но после рестарта контейнер придётся пересоздать.
            logger.warning("office-editor: cannot persist JWT secret", exc=str(exc))
        return secret

    # ── editor sessions / keepalive ─────────────────────────────────────────

    def mark_active(self, key: str) -> None:
        """DS reported an open editing session for this document key."""
        if key:
            self._active_keys.add(key)
        self._last_used = time.monotonic()

    def mark_closed(self, key: str) -> None:
        """DS reported the document closed (or saved-and-closed)."""
        self._active_keys.discard(key)
        self._last_used = time.monotonic()

    def touch(self) -> None:
        """Keepalive from an open editor tab — postpone the idle reaper."""
        self._last_used = time.monotonic()

    # ── lazy lifecycle (mirrors OfficeConvertManager) ───────────────────────

    async def is_image_missing(self, image: str | None = None) -> bool:
        """True когда docker жив, а образ НЕ установлен (opt-in не выполнен).

        Docker недоступен → False: это состояние «unavailable», а не
        «image_missing» (см. GetOfficeEditorConfigUC). `image` — runtime-
        выбранный образ (Settings → активный); None → образ из конструктора.
        """
        if not await self._docker_available():
            return False
        return not await self._image_present(image or self._image)

    async def ensure_running(self, image: str | None = None) -> str | None:
        """Ensure a healthy Document Server container; return its base URL.

        Returns None when Docker is unavailable, the image isn't installed or
        the container failed to become healthy. Idempotent and serialized:
        concurrent editor opens share one container. May block up to
        `startup_timeout_s` on a cold start (DS boots slowly).
        `image` — runtime-выбранный образ (Settings → активный); None → образ
        из конструктора. Контейнер от ДРУГОГО образа сносится и пересоздаётся
        из эффективного образа вызова.
        """
        effective_image = image or self._image
        async with self._lock:
            self._last_used = time.monotonic()
            if self._base_url is not None and await self._probe(self._internal_url()):
                return self._base_url
            if not await self._docker_available():
                return None
            if not await self._image_present(effective_image):
                logger.info("office-editor: image not installed, editor unavailable", image=effective_image)
                return None

            base, created = await self._bring_up(effective_image)
            if base is None:
                return None
            self._base_url = base
            await self._refresh_internal_url()
            if not await self._wait_healthy(self._internal_url()):
                logger.warning("office-editor: container did not become healthy", url=base)
                self._base_url = None
                return None
            if created:
                # Только для СВЕЖЕСОЗДАННОГО контейнера: смонтированные шрифты
                # появятся в редакторе после пересборки шрифтового кэша DS.
                await self._kick_font_cache()
            return base

    async def _bring_up(self, image: str) -> tuple[str | None, bool]:
        """(base_url, created): fast paths reuse the container, else run a new one."""
        state = await self._inspect(image)
        if state == "running":
            return await self._published_base_url(), False
        if state == "stopped":  # same-name container, same image — fast restart
            rc, _out, err = await self._run_docker_raw(["start", self._name], timeout=_START_TIMEOUT_S)
            if rc != 0:
                logger.warning("office-editor: docker start failed", err=err.strip())
                return None, False
            return await self._published_base_url(), False
        return await self._run_new(image), True

    async def _run_new(self, image: str) -> str | None:
        port = self._free_port()
        await self._siblings.ensure()
        args = [
            "run",
            "-d",
            "--name",
            self._name,
            *managed_label_args(),
            "-p",
            f"127.0.0.1:{port}:{self._container_port}",
            # Плюс общая сеть: браузер ходит в DS по опубликованному порту, а
            # бэкенд из своего контейнера — по имени контейнера.
            *self._network_args(),
            # DS сам ходит в бэкенд (download + callback); на Linux без
            # host-gateway host.docker.internal не резолвится.
            "--add-host=host.docker.internal:host-gateway",
            "-e",
            "JWT_ENABLED=true",
            "-e",
            f"JWT_SECRET={self.jwt_secret}",
            *self._fonts_mount_args(),
            image,
        ]
        rc, _out, err = await self._run_docker_raw(args, timeout=_RUN_TIMEOUT_S)
        if rc != 0:
            logger.warning("office-editor: docker run failed", err=err.strip())
            return None
        return f"http://127.0.0.1:{port}"

    def _fonts_mount_args(self) -> list[str]:
        """Bind-mount управляемых шрифтов (как у Gotenberg/texlive).

        `fonts_host_dir` — путь ХОСТА, когда бэкенд сам живёт в контейнере
        (docker -v резолвится демоном против хоста); нативно — сам fonts_dir.
        Пустая/отсутствующая папка не монтируется.
        """
        if self._fonts_dir is None:
            return []
        try:
            has_fonts = self._fonts_dir.is_dir() and any(self._fonts_dir.iterdir())
        except OSError:
            return []
        if not has_fonts:
            return []
        host_path = self._fonts_host_dir or str(self._fonts_dir)
        return ["-v", f"{host_path}:/usr/share/fonts/truetype/hse:ro"]

    async def _kick_font_cache(self) -> None:
        """Best-effort: пнуть пересборку шрифтового кэша DS (detached).

        Скрипт идёт в образе DS; без него смонтированные HSE-шрифты не видны в
        выпадашке редактора. Никогда не роняет открытие редактора.
        """
        try:
            rc, _out, err = await self._run_docker_raw(
                ["exec", "-d", self._name, "documentserver-generate-allfonts.sh"],
                timeout=_EXEC_TIMEOUT_S,
            )
            if rc == 0:
                logger.info("office-editor: font cache rebuild kicked")
            else:
                logger.info("office-editor: font cache rebuild not started", err=err.strip())
        except Exception as exc:  # noqa: BLE001 — best-effort by design
            logger.info("office-editor: font cache rebuild failed", exc=str(exc))

    async def _wait_healthy(self, base_url: str) -> bool:
        deadline = time.monotonic() + self._startup_timeout_s
        while time.monotonic() < deadline:
            if await self._probe(base_url):
                return True
            await asyncio.sleep(_HEALTH_POLL_INTERVAL_S)
        return False

    # ── AI plugin server settings (aiSettings в конфиге DS) ─────────────────

    async def apply_ai_settings(self, desired: dict[str, Any]) -> bool:
        """Синк серверных настроек AI-плагина: aiSettings в local.json DS.

        Best-effort реконсиляция при каждом открытии редактора: читаем текущий
        aiSettings из контейнера, при расхождении пишем желаемый и перезапускаем
        docservice (только он читает aiSettings; уже открытые редакторы теряют
        websocket и переподключаются сами). True — конфиг актуален (совпал или
        применён), False — синк не удался (редактор работает, AI не синкнут).
        """
        try:
            return await self._apply_ai_settings_unsafe(desired)
        except Exception as exc:  # noqa: BLE001 — синк AI не важнее самого редактора
            logger.warning("office-editor: ai settings sync failed", exc=str(exc))
            return False

    async def _apply_ai_settings_unsafe(self, desired: dict[str, Any]) -> bool:
        current = await self._read_ds_config()
        if current is None:
            return False
        if current.get("aiSettings") == desired:
            return True
        current["aiSettings"] = desired
        payload = json.dumps(current, ensure_ascii=False, indent=2).encode("utf-8")
        rc, _out, err = await self._run_docker_raw(
            ["exec", "-i", self._name, "sh", "-c", f"cat > {_DS_LOCAL_CONFIG}"],
            timeout=_EXEC_TIMEOUT_S,
            stdin=payload,
        )
        if rc != 0:
            logger.warning("office-editor: ai settings write failed", err=err.strip())
            return False
        rc, _out, err = await self._run_docker_raw(
            ["exec", self._name, "supervisorctl", "restart", "ds:docservice"],
            timeout=_STOP_TIMEOUT_S,
        )
        if rc != 0:
            logger.warning("office-editor: docservice restart failed", err=err.strip())
            return False
        healthy = await self._wait_healthy(self._internal_url())
        logger.info(
            "office-editor: ai settings applied",
            providers=len(desired.get("providers") or {}),
            models=len(desired.get("models") or []),
            healthy=healthy,
        )
        return healthy

    async def _read_ds_config(self) -> dict[str, Any] | None:
        rc, out, err = await self._run_docker_raw(
            ["exec", self._name, "cat", _DS_LOCAL_CONFIG], timeout=_EXEC_TIMEOUT_S
        )
        if rc != 0:
            logger.warning("office-editor: cannot read DS config", err=err.strip())
            return None
        try:
            parsed = json.loads(out)
        except ValueError:
            logger.warning("office-editor: DS config is not valid JSON, refusing to overwrite")
            return None
        if not isinstance(parsed, dict):
            logger.warning("office-editor: DS config has unexpected shape, refusing to overwrite")
            return None
        return parsed

    async def idle_reaper_loop(self) -> None:
        """Background loop: stop the container after `idle_timeout_s` without activity."""
        while True:
            await asyncio.sleep(_REAPER_INTERVAL_S)
            with suppress(Exception):
                await self._maybe_reap()

    async def _maybe_reap(self) -> None:
        if self._active_keys:
            # Живой редактор (вкладка шлёт touch, DS шлёт status=1) — не гасим
            # контейнер под ним, даже если last_used почему-то устарел.
            return
        if self._last_used is None:
            return
        if time.monotonic() - self._last_used < self._idle_timeout_s:
            return
        async with self._lock:
            if await self._inspect() == "running":
                logger.info("office-editor: idle stop", idle_timeout_s=self._idle_timeout_s)
                await self._run_docker_raw(["stop", self._name], timeout=_STOP_TIMEOUT_S)
            self._base_url = None
            self._last_used = None

    async def reconcile(self) -> None:
        """Startup hook: adopt an already-running managed container."""
        if await self._inspect() == "running":
            self._base_url = await self._published_base_url()
            await self._refresh_internal_url()
            self._last_used = time.monotonic()
            logger.info("office-editor: adopted running container", url=self._base_url)

    async def stop(self) -> None:
        """Shutdown hook: stop the managed container (auto-starts again on demand)."""
        self._base_url = None
        self._last_used = None
        self._active_keys.clear()
        if await self._inspect() == "running":
            await self._run_docker_raw(["stop", self._name], timeout=_STOP_TIMEOUT_S)

    # ── docker plumbing ─────────────────────────────────────────────────────

    async def inspect_state(self) -> tuple[bool, bool, str | None]:
        """(present, running, status_text) — чистое чтение для status-API.

        В отличие от `_inspect` НЕ сверяет образ и ничего не удаляет: статусный
        эндпоинт не должен иметь побочных эффектов.
        """
        rc, out, _err = await self._run_docker_raw(
            [
                "ps",
                "-a",
                "--filter",
                f"name=^/{self._name}$",
                "--format",
                "{{.State}}|{{.Status}}",
            ],
            timeout=_PS_TIMEOUT_S,
        )
        if rc != 0:
            return False, False, None
        line = next((ln for ln in out.splitlines() if ln.strip()), "")
        if not line:
            return False, False, None
        state, _, status = line.partition("|")
        return True, state.strip() == "running", status.strip() or None

    async def _inspect(self, expected_image: str | None = None) -> str:
        """'running' | 'stopped' | 'absent' — состояние именованного контейнера.

        При заданном `expected_image` контейнер от ДРУГОГО образа сносится
        сразу (absent → пересоздание), чтобы смена активного образа (runtime-
        настройка или office_editor.image) подхватывалась без ручного rm.
        Без `expected_image` (reaper/stop/reconcile) образ не сверяется —
        обслуживаем контейнер, каким бы образом он ни был запущен.
        """
        rc, out, _err = await self._run_docker_raw(
            [
                "ps",
                "-a",
                "--filter",
                f"name=^/{self._name}$",
                "--format",
                "{{.State}}|{{.Image}}",
            ],
            timeout=_PS_TIMEOUT_S,
        )
        if rc != 0:
            return "absent"
        line = next((ln for ln in out.splitlines() if ln.strip()), "")
        if not line:
            return "absent"
        state, _, image = line.partition("|")
        if expected_image is not None and image.strip() != expected_image:
            await self._run_docker_raw(["rm", "-f", self._name], timeout=_RM_TIMEOUT_S)
            return "absent"
        return "running" if state.strip() == "running" else "stopped"

    def _network_args(self) -> list[str]:
        """`--network`, когда бэкенд в контейнере; публикацию порта НЕ заменяет."""
        args = self._siblings.publish_args(0, self._container_port)
        return args if args[:1] == ["--network"] else []

    def _internal_url(self) -> str:
        """Адрес для запросов бэкенда; до первого refresh — публичный."""
        return self._internal_base_url or self._base_url or ""

    async def _refresh_internal_url(self) -> None:
        """Куда бэкенду стучаться самому: имя в общей сети либо публичный адрес."""
        by_name = await self._siblings.resolve_url(self._name, self._container_port)
        self._internal_base_url = by_name or self._base_url

    async def _published_base_url(self) -> str | None:
        template = f'{{{{(index (index .NetworkSettings.Ports "{self._container_port}/tcp") 0).HostPort}}}}'
        rc, out, _err = await self._run_docker_raw(
            ["inspect", "--format", template, self._name], timeout=_INSPECT_TIMEOUT_S
        )
        port = out.strip()
        if rc != 0 or not port.isdigit():
            return None
        return f"http://127.0.0.1:{port}"

    async def _docker_available(self) -> bool:
        rc, _out, _err = await self._run_docker_raw(
            ["version", "--format", "{{.Server.Version}}"], timeout=_VERSION_TIMEOUT_S
        )
        return rc == 0

    async def _image_present(self, image: str) -> bool:
        rc, _out, _err = await self._run_docker_raw(["image", "inspect", image], timeout=_INSPECT_TIMEOUT_S)
        return rc == 0

    async def _probe(self, base_url: str) -> bool:
        return await asyncio.to_thread(self._probe_sync, base_url)

    def _probe_sync(self, base_url: str) -> bool:
        try:
            resp = self._client.get(f"{base_url}{self._health_path}", timeout=self._health_timeout_s)
        except Exception as exc:  # noqa: BLE001 — health probe must never raise
            logger.debug("office-editor: health probe failed", exc=str(exc))
            return False
        # DS /healthcheck отвечает буквальным "true" когда все сервисы живы.
        return resp.status_code == 200 and "true" in resp.text.lower()

    @staticmethod
    def _free_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", 0))
            return int(s.getsockname()[1])

    async def _run_docker_raw(
        self, args: list[str], timeout: float, stdin: bytes | None = None
    ) -> tuple[int | None, str, str]:
        try:
            proc = await asyncio.create_subprocess_exec(
                docker_binary(),
                *args,
                stdin=asubprocess.PIPE if stdin is not None else None,
                stdout=asubprocess.PIPE,
                stderr=asubprocess.PIPE,
            )
        except OSError as exc:
            return None, "", f"docker CLI not found: {exc}"
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(input=stdin), timeout=timeout)
        except asyncio.TimeoutError:
            if proc.returncode is None:
                with suppress(ProcessLookupError):
                    proc.kill()
            return None, "", "docker command timed out"
        return (
            proc.returncode,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )
