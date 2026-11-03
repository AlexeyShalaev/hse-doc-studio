"""Исполнитель обновления: снимок базы -> образ -> проверка -> остановка -> миграции -> запуск -> здоровье, с откатом.

Порядок и причины в docs/design/auto-update.md. Деление на две зоны:

- до остановки (`stop`) ничего необратимого не произошло; любой отказ это `AbortError`, запуск отменяется;
- с остановки любой отказ ведёт в `_revert`: старые образы, а если миграции изменили ревизию базы, то сначала
  восстановление снимка (старый образ не запустится на схеме новее себя: защита db-ahead).

Все побочные эффекты идут через `IDocker`, `IApi`, `http_get` и часы, поэтому весь сценарий гоняется на фейках.
"""

from __future__ import annotations

import os
import re
import shutil
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from hse_doc_studio.infra.update.server_updater import plan
from hse_doc_studio.infra.update.server_updater.client import IApi
from hse_doc_studio.infra.update.server_updater.config import UpdaterConfig
from hse_doc_studio.infra.update.server_updater.docker import IDocker, Result, inspect
from hse_doc_studio.infra.update.server_updater.journal import Journal
from hse_doc_studio.infra.update.server_updater.reporter import Reporter

HttpGet = Callable[[str, dict[str, str], float], tuple[int, str]]
SNAP_DIR = "snapshots"
_IMAGE_ID = re.compile(r"^(sha256:.+|[0-9a-f]{12,64})$")


class AbortError(Exception):
    """Отказ до остановки сервисов: система не тронута, запуск отменяется."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class _StepError(Exception):
    """Отказ после остановки: нужен откат."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def published_digest(http_get: HttpGet, spec: dict[str, Any]) -> str:
    """Дайджест образа из `image-digest.json` релиза; нет файла или он чужой версии: запуск отменяется."""
    url = str(spec.get("digests_url") or "")
    if not url.startswith("https://"):
        raise AbortError(
            "digest_missing", "the release publishes no image digest; set verification to off to install anyway"
        )
    try:
        code, body = http_get(url, {}, 20.0)
    except OSError as exc:
        raise AbortError("digest_unreachable", f"cannot fetch the release digest: {exc}") from exc
    digest = plan.parse_digest_doc(body, version=spec["to_version"]) if code == 200 else None  # noqa: PLR2004
    if digest is None:
        raise AbortError("digest_missing", "the release digest file is unreadable or for another version")
    return digest


@dataclass
class _Svc:
    service: str
    name: str
    container: dict[str, Any]
    image_id: str
    image_ref: str


class Engine(Reporter):
    def __init__(
        self,
        config: UpdaterConfig,
        docker: IDocker,
        api: IApi,
        journal: Journal,
        *,
        http_get: HttpGet,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(api, journal, now=now)
        self._c = config
        self._d = docker
        self._get = http_get
        self._sleep = sleep
        self._mono = monotonic

    # ---- docker ----

    def _discover(self) -> dict[str, _Svc]:
        found: dict[str, _Svc] = {}
        project = self._c.project
        if not project:
            probe = self._d.run(["ps", "-aq", "--filter", "label=com.docker.compose.service=api"])
            ids = probe.out.split()
            info = inspect(self._d, ids[0]) if ids else None
            project = ((info or {}).get("Config") or {}).get("Labels", {}).get("com.docker.compose.project", "")
        if not project:
            raise AbortError("no_project", "cannot find the compose project (set HSE_UPDATER__PROJECT)")
        for service in self._c.services:
            res = self._d.run(
                [
                    "ps",
                    "-aq",
                    "--filter",
                    f"label=com.docker.compose.project={project}",
                    "--filter",
                    f"label=com.docker.compose.service={service}",
                ]
            )
            ids = res.out.split()
            if not ids:
                if service == "api":
                    raise AbortError("no_api", "the api container is not found")
                continue
            info = inspect(self._d, ids[0])
            if info is None:
                raise AbortError("inspect_failed", f"cannot inspect {service}")
            found[service] = _Svc(
                service=service,
                name=str(info.get("Name", "")).lstrip("/"),
                container=info,
                image_id=str(info.get("Image", "")),
                image_ref=self._named_ref(str(info.get("Image", "")), str((info.get("Config") or {}).get("Image", ""))),
            )
        return found

    def _named_ref(self, image_id: str, ref: str) -> str:
        """Имя образа с репозиторием. Контейнер, созданный из идентификатора (после отката), несёт `sha256:..` вместо
        имени: репозиторий для pull и тег `rollback-prev` из такого значения не получить, поэтому берём тег образа."""
        if not _IMAGE_ID.match(ref):
            return ref
        tags = [str(t) for t in (inspect(self._d, image_id) or {}).get("RepoTags") or [] if t]
        # тег отката годится, если другого нет: репозиторий у него тот же
        tags.sort(key=lambda t: t.endswith(f":{plan.ROLLBACK_TAG}"))
        return tags[0] if tags else ref

    def _pinned(self, entry: dict[str, Any], fallback_id: str) -> str:
        """Чем пересоздавать контейнер из прежнего образа: именем, если тег всё ещё указывает на тот же образ, иначе
        идентификатором. Контейнер из идентификатора теряет имя, и следующее обновление не знает репозитория."""
        image_id = str(entry.get("id") or fallback_id)
        ref = str(entry.get("ref") or "")
        if ref and not _IMAGE_ID.match(ref) and (inspect(self._d, ref) or {}).get("Id") == image_id:
            return ref
        return image_id

    def _env_file(self, api: _Svc) -> Path:
        path = self._c.data_dir / "run.env"
        self._c.data_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(plan.env_file_text((api.container.get("Config") or {}).get("Env") or []), encoding="utf-8")
        path.chmod(0o600)
        return path

    def _network(self, api: _Svc) -> str:
        return str((api.container.get("HostConfig") or {}).get("NetworkMode") or "bridge")

    def _volume(self) -> str:
        if self._c.snapshot_volume:
            return self._c.snapshot_volume
        own = inspect(self._d, os.environ.get("HOSTNAME", "")) or {}
        for mount in own.get("Mounts") or []:
            if mount.get("Destination") == str(self._c.data_dir) and mount.get("Name"):
                return str(mount["Name"])
        raise AbortError("no_snapshot_volume", "cannot find the updater data volume (set HSE_UPDATER__SNAPSHOT_VOLUME)")

    def _oneshot(self, image: str, command: list[str], api: _Svc, env_file: Path, *, timeout: float) -> Result:
        args = plan.oneshot_command(
            image, command, network=self._network(api), env_file=str(env_file), snapshot_volume=self._volume()
        )
        return self._d.run(args, timeout)

    def _db_current(self, image: str, api: _Svc, env_file: Path) -> tuple[str | None, str | None]:
        res = self._oneshot(image, ["hse-doc-studio", "db", "current"], api, env_file, timeout=120.0)
        if not res.ok:
            raise AbortError("db_unreachable", f"cannot read the database revision: {res.err.strip()[-300:]}")
        return plan.parse_db_current(res.out)

    # ---- публичный вход ----

    def execute(self, spec: dict[str, Any]) -> None:
        run = {
            "id": spec["run_id"],
            "kind": spec["kind"],
            "to_version": spec["to_version"],
            "from_version": spec["from_version"],
            "phase": "preflight",
            "seq": 0,
            "stopped": False,
            "migrating": False,
            "from_rev": None,
            "to_rev": None,
            "snapshot": None,
            "old": {},
        }
        self._j.start_run(run)
        title = f"{spec['kind']} {spec['from_version']} -> {spec['to_version']} started"
        self.emit("preflight", title, status="running")
        try:
            if spec["kind"] == "rollback":
                self._manual_rollback(spec)
            else:
                self._update(spec)
        except AbortError as exc:
            self.emit("finish", exc.message, level="error", status="cancelled", error_code=exc.code)
            self._j.finish_run()
        except Exception as exc:  # непредвиденное: если сервисы уже остановлены, лучше откатить, чем оставить так
            self._unexpected(exc)

    def _unexpected(self, exc: Exception) -> None:
        run = self._j.run or {}
        if run.get("stopped"):
            self.recover(reason=f"unexpected error: {exc}")
        else:
            self.emit("finish", f"unexpected error: {exc}", level="error", status="cancelled", error_code="internal")
            self._j.finish_run()

    # ---- обновление ----

    def _update(self, spec: dict[str, Any]) -> None:
        svcs = self._discover()
        api = svcs["api"]
        self._preflight(svcs)
        env_file = self._env_file(api)
        repo, _ = plan.split_image(api.image_ref)
        target = plan.target_ref(api.image_ref, spec["to_version"])
        if not plan.is_version(spec["to_version"]):
            raise AbortError("bad_version", f"unsupported version string: {spec['to_version']}")
        old = {s.service: {"id": s.image_id, "ref": s.image_ref, "name": s.name} for s in svcs.values()}
        self._j.update_run(old=old, repo=repo, order=list(svcs))
        try:
            self._snapshot(spec, api, env_file)
            self._pull_and_verify(spec, repo, target)
            self._swap(spec, svcs, api, env_file, target)
        finally:
            env_file.unlink(missing_ok=True)

    def _preflight(self, svcs: dict[str, _Svc]) -> None:
        for svc in svcs.values():
            bad = plan.unsupported_options(svc.container)
            if bad:
                raise AbortError(
                    "unsupported_container_options",
                    f"{svc.service} uses options the updater cannot recreate ({', '.join(bad)}); update by hand",
                )
        self._c.data_dir.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(self._c.data_dir).free
        if free < self._c.min_free_bytes:
            have, need = free // 2**20, self._c.min_free_bytes // 2**20
            raise AbortError("no_disk_space", f"only {have} MiB free for the snapshot, need {need}")

    def _snapshot(self, spec: dict[str, Any], api: _Svc, env_file: Path) -> None:
        self.emit("snapshot", "reading the current database revision and taking a snapshot")
        old_image = api.image_id
        current, _head = self._db_current(old_image, api, env_file)
        self._j.update_run(from_rev=current)
        (self._c.data_dir / SNAP_DIR).mkdir(parents=True, exist_ok=True)
        (self._c.data_dir / SNAP_DIR).chmod(0o777)
        name = f"{spec['run_id']}.pgdump"
        res = self._oneshot(
            old_image,
            ["hse-doc-studio", "db", "snapshot", "--out", f"/snap/{SNAP_DIR}/{name}"],
            api,
            env_file,
            timeout=self._c.migrate_timeout_s,
        )
        if not res.ok:
            raise AbortError("snapshot_failed", f"database snapshot failed: {(res.err or res.out).strip()[-400:]}")
        self._j.update_run(snapshot=name)
        ref = plan.rollback_ref(api.image_ref)
        tag = self._d.run(["tag", old_image, ref])
        if not tag.ok:
            raise AbortError("tag_failed", f"cannot keep the previous image: {tag.err.strip()[-300:]}")
        self.emit("snapshot", f"snapshot {name} taken (revision {current or 'none'})", from_revision=current)

    def _pull_and_verify(self, spec: dict[str, Any], repo: str, target: str) -> None:
        self.emit("pull", f"pulling {target}")
        pull = self._d.run(["pull", target], self._c.pull_timeout_s)
        if not pull.ok:
            raise AbortError("pull_failed", f"pull failed, nothing changed: {pull.err.strip()[-300:]}")
        image = inspect(self._d, target)
        if image is None:
            raise AbortError("pull_failed", "the pulled image cannot be inspected")
        verify = spec.get("verify", "digest")
        if verify == "none":
            self.emit("verify", "image verification is off", level="warn")
            return
        self.emit("verify", f"verifying the image ({verify})")
        digest = self._published_digest(spec)
        if not plan.digest_matches(image, repo, digest):
            raise AbortError(
                "digest_mismatch", f"the pulled image does not match the digest published with the release ({digest})"
            )
        if verify == "cosign":
            res = self._d.run(plan.cosign_verify_command(repo, digest), 300.0)
            if not res.ok:
                raise AbortError("signature_invalid", f"cosign signature check failed: {res.err.strip()[-300:]}")
        self.emit("verify", f"image digest {digest[:19]} verified")

    def _published_digest(self, spec: dict[str, Any]) -> str:
        return published_digest(self._get, spec)

    def _swap(self, spec: dict[str, Any], svcs: dict[str, _Svc], api: _Svc, env_file: Path, target: str) -> None:
        """Точка невозврата: с остановки любой отказ откатывается."""
        new_inspect = inspect(self._d, target) or {}
        self._j.update_run(stopped=True)
        try:
            self.emit("stop", "stopping runner and api")
            for svc in reversed(list(svcs.values())):
                self._d.run(["stop", "--time", str(self._c.stop_timeout_s), svc.name], self._c.stop_timeout_s + 30)
            self._j.update_run(migrating=True)
            self.emit("migrate", "applying migrations on the new image")
            res = self._oneshot(
                target, ["hse-doc-studio", "db", "upgrade"], api, env_file, timeout=self._c.migrate_timeout_s
            )
            if not res.ok:
                raise _StepError("migration_failed", f"migrations failed: {(res.err or res.out).strip()[-400:]}")
            to_rev, _head = self._db_current(target, api, env_file)
            self._j.update_run(to_rev=to_rev)
            self.emit("migrate", f"database revision {to_rev}", to_revision=to_rev)
            self.emit("restart", "recreating the containers on the new image")
            for svc in svcs.values():
                self._recreate(svc, new_inspect, target)
            self.emit("health", "waiting for the new version to become healthy")
            self._wait_healthy(svcs)
        except _StepError as exc:
            self._revert(exc.code, exc.message, svcs, api, env_file)
            return
        self._succeed(spec, svcs, target)

    def _recreate(self, svc: _Svc, image_inspect: dict[str, Any], image_ref: str) -> None:
        self._d.run(["rm", "-f", svc.name], 60.0)
        args = plan.recreate_command(svc.container, image_inspect, image_ref)
        res = self._d.run(args, 120.0)
        if not res.ok:
            raise _StepError("recreate_failed", f"cannot start {svc.service}: {res.err.strip()[-300:]}")

    def _wait_healthy(self, svcs: dict[str, _Svc]) -> None:
        deadline = self._mono() + self._c.health_timeout_s
        stable_since: float | None = None
        baseline = {s.service: self._restarts(s.name) for s in svcs.values()}
        while self._mono() < deadline:
            self.flush()  # события migrate/restart ждали в очереди (api был остановлен), иначе страница висит на «stop»
            ok = self._healthy_once(svcs, baseline)
            if ok is None:
                raise _StepError("health_failed", "a container is crash-looping or exited")
            if ok:
                stable_since = stable_since if stable_since is not None else self._mono()
                if self._mono() - stable_since >= self._c.stable_s:
                    return
            else:
                stable_since = None
            self._sleep(2.0)
        raise _StepError("health_timeout", f"the new version is not healthy after {int(self._c.health_timeout_s)} s")

    def _restarts(self, name: str) -> int:
        return int(((inspect(self._d, name) or {}).get("RestartCount")) or 0)

    def _healthy_once(self, svcs: dict[str, _Svc], baseline: dict[str, int]) -> bool | None:
        """True здоров, False ещё нет, None безнадёжно (упал или перезапускается по кругу)."""
        for svc in svcs.values():
            info = inspect(self._d, svc.name) or {}
            state = info.get("State") or {}
            if not state.get("Running"):
                return None if state.get("Status") in {"exited", "dead"} else False
            if int(info.get("RestartCount") or 0) > baseline.get(svc.service, 0):
                return None
            health = (state.get("Health") or {}).get("Status")
            if health == "unhealthy":
                return False
            if health == "starting":
                return False
        headers = {"Authorization": f"Bearer {self._c.health_token}"} if self._c.health_token else {}
        try:
            code, _body = self._get(self._c.health_url, headers, 10.0)
        except OSError:
            return False
        return code == 200  # noqa: PLR2004

    def _succeed(self, spec: dict[str, Any], svcs: dict[str, _Svc], target: str) -> None:
        run = self._j.run or {}
        self._write_env_tag(spec["to_version"])
        self._prune_snapshots(keep=run.get("snapshot"))
        last_ok = {
            "to_version": spec["to_version"],
            "from_version": spec["from_version"],
            "snapshot": run.get("snapshot"),
            "from_rev": run.get("from_rev"),
            "to_rev": run.get("to_rev"),
            "old": run.get("old"),
        }
        self.emit(
            "finish",
            f"updated to {spec['to_version']}",
            status="succeeded",
            from_revision=run.get("from_rev"),
            to_revision=run.get("to_rev"),
        )
        self._j.finish_run(keep_as_last_ok=last_ok)

    # ---- откат ----

    def _revert(self, code: str, message: str, svcs: dict[str, _Svc], api: _Svc, env_file: Path) -> None:
        run = self._j.run or {}
        self.emit("rollback", f"{message}. Rolling back to the previous version.", level="error", error_code=code)
        old = run.get("old") or {}
        for svc in reversed(list(svcs.values())):
            self._d.run(["rm", "-f", svc.name], 60.0)
        restore = False
        if run.get("migrating"):
            restore = self._schema_changed(run, api, env_file)
        if restore:
            self.emit("restore", "the schema changed: restoring the pre-update snapshot", level="warn")
            res = self._oneshot(
                old[api.service]["id"],
                ["hse-doc-studio", "db", "restore-snapshot", "--file", f"/snap/{SNAP_DIR}/{run.get('snapshot')}"],
                api,
                env_file,
                timeout=self._c.migrate_timeout_s,
            )
            if not res.ok:
                self.emit(
                    "finish",
                    f"snapshot restore FAILED, the stack is down. Snapshot: {SNAP_DIR}/{run.get('snapshot')} "
                    f"in the updater volume. {res.err.strip()[-300:]}",
                    level="error",
                    status="failed",
                    error_code="restore_failed",
                    db_restored=False,
                )
                self._j.finish_run()
                return
        try:
            for svc in svcs.values():
                target_id = old[svc.service]["id"]
                self._recreate(svc, inspect(self._d, target_id) or {}, self._pinned(old[svc.service], target_id))
            self._wait_healthy(svcs)
        except _StepError as exc:
            self.emit(
                "finish",
                f"ROLLBACK FAILED, run `docker compose up -d` by hand: {exc.message}",
                level="error",
                status="failed",
                error_code="rollback_failed",
                db_restored=restore,
            )
            self._j.finish_run()
            return
        self.emit(
            "finish",
            f"{message}. Rolled back to {run.get('from_version')}"
            + (", database restored from the snapshot" if restore else ""),
            level="warn",
            status="rolled_back",
            error_code=code,
            db_restored=restore,
            from_revision=run.get("from_rev"),
            to_revision=run.get("to_rev"),
        )
        self._j.finish_run()

    def _schema_changed(self, run: dict[str, Any], api: _Svc, env_file: Path) -> bool:
        """Изменили ли миграции ревизию базы. Не смогли узнать: считаем, что изменили (восстановление безопаснее)."""
        new_ref = plan.target_ref(api.image_ref, run["to_version"])
        try:
            current, _head = self._db_current(new_ref, api, env_file)
        except AbortError:
            return True
        return current != run.get("from_rev")

    def recover(self, reason: str = "the updater restarted in the middle of a run") -> None:
        """Старт после падения: незаконченный запуск, дошедший до остановки, откатывается по журналу."""
        run = self._j.run
        if run is None:
            return
        if not run.get("stopped"):
            self.emit("finish", reason, level="error", status="cancelled", error_code="updater_restarted")
            self._j.finish_run()
            return
        try:
            svcs = self._discover()
            api = svcs["api"]
            env_file = self._env_file(api)
        except AbortError as exc:
            self.emit("finish", f"cannot recover: {exc.message}", level="error", status="failed", error_code=exc.code)
            self._j.finish_run()
            return
        try:
            if run.get("kind") == "rollback":
                self._rollback_undo(svcs, reason)
            else:
                self._revert("updater_restarted", reason, svcs, api, env_file)
        finally:
            env_file.unlink(missing_ok=True)

    # ---- ручной откат ----

    def _manual_rollback(self, spec: dict[str, Any]) -> None:  # noqa: C901, PLR0912, PLR0915 — один линейный сценарий
        last = self._j.data.get("last_ok")
        if not last or last.get("to_version") != spec["from_version"]:
            raise AbortError("no_previous_version", "the updater has no record of the update to roll back")
        svcs = self._discover()
        api = svcs["api"]
        self._preflight(svcs)
        old = last.get("old") or {}
        for svc in svcs.values():
            if svc.service in old and inspect(self._d, old[svc.service]["id"]) is None:
                raise AbortError("previous_image_missing", f"the previous {svc.service} image is gone from this host")
        restore = bool(spec.get("restore_db"))
        snapshot = last.get("snapshot")
        if restore and not (snapshot and (self._c.data_dir / SNAP_DIR / snapshot).is_file()):
            raise AbortError("snapshot_missing", "the pre-update snapshot file is gone")
        env_file = self._env_file(api)
        try:
            if not restore:
                current, head = self._db_current(old[api.service]["id"], api, env_file)
                if current != head:
                    raise AbortError(
                        "schema_ahead", "the database is newer than the previous version: confirm the snapshot restore"
                    )
            self._j.update_run(
                stopped=True,
                old={s: {"id": svcs[s].image_id, "ref": svcs[s].image_ref, "name": svcs[s].name} for s in svcs},
            )
            self.emit("stop", "stopping runner and api")
            for svc in reversed(list(svcs.values())):
                self._d.run(["stop", "--time", str(self._c.stop_timeout_s), svc.name], self._c.stop_timeout_s + 30)
            if restore:
                self.emit("restore", "restoring the pre-update snapshot", level="warn")
                res = self._oneshot(
                    old[api.service]["id"],
                    ["hse-doc-studio", "db", "restore-snapshot", "--file", f"/snap/{SNAP_DIR}/{snapshot}"],
                    api,
                    env_file,
                    timeout=self._c.migrate_timeout_s,
                )
                if not res.ok:
                    self._rollback_undo(svcs, f"snapshot restore failed: {res.err.strip()[-300:]}")
                    return
            self.emit("restart", "recreating the containers on the previous images")
            try:
                for svc in svcs.values():
                    target_id = old.get(svc.service, {}).get("id", svc.image_id)
                    self._recreate(
                        svc, inspect(self._d, target_id) or {}, self._pinned(old.get(svc.service, {}), target_id)
                    )
                self._wait_healthy(svcs)
            except _StepError as exc:
                self._rollback_undo(svcs, exc.message, restored=restore)
                return
        finally:
            env_file.unlink(missing_ok=True)
        self._write_env_tag(spec["to_version"])
        self.emit("finish", f"rolled back to {spec['to_version']}", status="succeeded", db_restored=restore)
        self._j.finish_run(keep_as_last_ok=None)
        self._j.data["last_ok"] = None
        self._j.save()

    def _rollback_undo(self, svcs: dict[str, _Svc], reason: str, *, restored: bool = False) -> None:
        """Ручной откат не поднялся: возвращаем образы, что стояли до него."""
        run = self._j.run or {}
        before = run.get("old") or {}
        try:
            for svc in svcs.values():
                image_id = before.get(svc.service, {}).get("id", svc.image_id)
                self._recreate(
                    svc, inspect(self._d, image_id) or {}, self._pinned(before.get(svc.service, {}), image_id)
                )
            self._wait_healthy(svcs)
            state = "the previous state is back"
        except _StepError as exc:
            state = f"the stack is down: {exc.message}"
        self.emit(
            "finish",
            f"rollback failed ({reason}); {state}",
            level="error",
            status="failed",
            error_code="rollback_failed",
            db_restored=restored,
        )
        self._j.finish_run()

    # ---- служебное ----

    def _write_env_tag(self, version: str) -> None:
        path = self._c.env_file
        if path is None or not path.is_file():
            return
        try:
            path.write_text(plan.set_env_tag(path.read_text(encoding="utf-8"), version), encoding="utf-8")
        except OSError as exc:
            self.emit("finish", f".env was not updated (TAG={version}): {exc}", level="warn")

    def _prune_snapshots(self, keep: str | None) -> None:
        folder = self._c.data_dir / SNAP_DIR
        if not folder.is_dir():
            return
        files = sorted((p for p in folder.glob("*.pgdump")), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in files[self._c.keep_snapshots :]:
            if old.name != keep:
                old.unlink(missing_ok=True)
                old.with_suffix(old.suffix + ".sha256").unlink(missing_ok=True)
