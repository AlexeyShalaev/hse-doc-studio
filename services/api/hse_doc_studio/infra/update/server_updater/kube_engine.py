"""Исполнитель kubernetes: образ Deployment api, миграции Job-ом, здоровье, откат образа, пока схема не менялась.

Порядок и причины в docs/design/auto-update.md, раздел 5a. Отличия от compose, коротко:

- снимка базы нет: откат схемы не делаем. Перед остановкой запускается Job `db current` на новом образе (проверка,
  что образ тянется и база читается, и ревизия «до»); после остановки откат образа безопасен, только пока ревизия
  базы не изменилась. Изменилась и версия не поднялась: образ НЕ откатывается (старый не стартует на новой схеме),
  запуск завершается `failed` с кодом `needs_manual_action` и пошаговой инструкцией в событиях;
- «остановка» это replicas=0 у Deployment, «пересоздание» это патч образа и replicas, образ тянет kubelet, по дайджесту
  из `image-digest.json` релиза (ровно проверенный образ);
- состояние запуска дублируется в аннотациях Deployment (kube_journal), а не только в файле;
- опора на Deployment и Job, не на релиз Helm: работает и у установок без Helm-записи.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from hse_doc_studio.infra.compile.k8s.api import KubeApiError
from hse_doc_studio.infra.update.server_updater import kube_plan, plan
from hse_doc_studio.infra.update.server_updater.client import IApi
from hse_doc_studio.infra.update.server_updater.config import UpdaterConfig
from hse_doc_studio.infra.update.server_updater.engine import AbortError, HttpGet, published_digest
from hse_doc_studio.infra.update.server_updater.kube import IKube
from hse_doc_studio.infra.update.server_updater.kube_journal import KubeJournal
from hse_doc_studio.infra.update.server_updater.reporter import Reporter

NEEDS_HANDS = "needs_manual_action"
_FORBIDDEN = 403
_LOG_KEEP = 400


class _StepError(Exception):
    """Отказ после остановки api: нужен откат (или руки, если схема изменилась)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class _JobError(Exception):
    pass


class KubeEngine(Reporter):
    def __init__(  # noqa: PLR0913
        self,
        config: UpdaterConfig,
        kube: IKube,
        api: IApi,
        journal: KubeJournal,
        *,
        http_get: HttpGet,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        super().__init__(api, journal, now=now)
        assert config.kube is not None  # noqa: S101 — движок создаётся только для исполнителя kubernetes
        self._c = config
        self._s = config.kube
        self._k = kube
        self._kj = journal
        self._get = http_get
        self._sleep = sleep
        self._mono = monotonic

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
            "patched": False,
            "healthy": False,
            "from_rev": None,
            "to_rev": None,
            "old": {},
            "new_image": None,
            "jobs": [],
        }
        self._j.start_run(run)
        self.emit(
            "preflight", f"{spec['kind']} {spec['from_version']} -> {spec['to_version']} started", status="running"
        )
        try:
            self._check_journal()
            if spec["kind"] == "rollback":
                self._manual_rollback(spec)
            else:
                self._update(spec)
        except AbortError as exc:
            self.emit("finish", exc.message, level="error", status="cancelled", error_code=exc.code)
            self._j.finish_run()
        except Exception as exc:  # непредвиденное: если api уже остановлен, лучше откатить, чем оставить так
            self._unexpected(exc)

    def _check_journal(self) -> None:
        try:
            self._kj.mirror(strict=True)
        except KubeApiError as exc:
            raise AbortError(
                "kube_forbidden", f"cannot write to the api Deployment (check the updater Role): {exc}"
            ) from exc

    def _unexpected(self, exc: Exception) -> None:
        run = self._j.run or {}
        if run.get("stopped"):
            try:
                self.recover(reason=f"unexpected error: {exc}")
            except AbortError as abort:
                self.emit("finish", abort.message, level="error", status="failed", error_code=abort.code)
                self._j.finish_run()
        else:
            self.emit("finish", f"unexpected error: {exc}", level="error", status="cancelled", error_code="internal")
            self._j.finish_run()

    # ---- кластер ----

    def _deployment(self) -> dict[str, Any]:
        try:
            return self._k.get_deployment()
        except KubeApiError as exc:
            if exc.status == _FORBIDDEN:
                raise AbortError("kube_forbidden", f"the updater may not read the api Deployment: {exc}") from exc
            raise AbortError("kube_unavailable", f"cannot read the api Deployment: {exc}") from exc

    def _patch(self, replicas: int, image: str | None = None) -> None:
        patch = kube_plan.scale_patch(replicas, container=self._s.container, image=image)
        try:
            self._k.patch_deployment(patch)
        except KubeApiError as exc:
            raise _StepError("patch_failed", f"cannot patch the api Deployment: {exc}") from exc

    def _wait_stopped(self, selector: str) -> None:
        deadline = self._mono() + self._s.stop_timeout_s
        while self._mono() < deadline:
            try:
                if not self._k.list_pods(selector):
                    return
            except KubeApiError:
                pass
            self._sleep(self._s.poll_s)
        raise _StepError("stop_timeout", f"the api pods did not stop in {int(self._s.stop_timeout_s)} s")

    # ---- Job ----

    def _create_job(self, manifest: dict[str, Any]) -> None:
        try:
            self._k.create_job(manifest)
        except KubeApiError as exc:
            if exc.status != 409:  # noqa: PLR2004 — Job с таким именем остался от упавшего повтора: пересоздаём
                raise
            self._k.delete_job(manifest["metadata"]["name"])
            self._sleep(self._s.poll_s)
            self._k.create_job(manifest)

    def _run_job(self, manifest: dict[str, Any], *, timeout_s: float) -> str:
        """Ждёт Job до успеха и отдаёт лог его пода. Сбой, зависший старт пода или срок это `_JobError` с причиной."""
        name = manifest["metadata"]["name"]
        step = manifest["metadata"]["labels"][kube_plan.LABEL_STEP]
        try:
            self._create_job(manifest)
        except KubeApiError as exc:
            raise _JobError(f"cannot create the Job {name}: {exc}") from exc
        start_by = self._mono() + self._s.pod_start_timeout_s
        deadline = self._mono() + timeout_s
        started = False
        while True:
            job, pods = self._poll_job(name)
            started = started or any(_pod_started(p) for p in pods)
            outcome = kube_plan.job_outcome(job)
            if outcome == "succeeded":
                return self._logs(pods, step)
            if outcome == "failed":
                raise _JobError(f"the Job {name} failed: {self._logs(pods, step)[-_LOG_KEEP:].strip() or 'no log'}")
            self._check_job_pods(name, pods, started=started, start_by=start_by)
            if self._mono() > deadline:
                raise _JobError(f"the Job {name} did not finish in {int(timeout_s)} s")
            self._sleep(self._s.poll_s)

    def _poll_job(self, name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        try:
            job = self._k.get_job(name)
            if job is None:
                raise _JobError(f"the Job {name} disappeared")
            return job, self._k.list_pods(kube_plan.job_pod_selector(name))
        except KubeApiError as exc:
            if exc.status == _FORBIDDEN:
                raise _JobError(f"the updater may not read the Job {name}: {exc}") from exc
            return {}, []  # сбой связи с API: подождём

    def _check_job_pods(self, name: str, pods: list[dict[str, Any]], *, started: bool, start_by: float) -> None:
        problem = next((p for p in map(kube_plan.pod_problem, pods) if p), None)
        if problem:
            raise _JobError(f"the Job {name} cannot run: {problem}")
        if not started and self._mono() > start_by:
            why = next((w for w in map(kube_plan.pod_unschedulable, pods) if w), "the pod does not start")
            raise _JobError(f"the Job {name} did not start in {int(self._s.pod_start_timeout_s)} s: {why}")

    def _logs(self, pods: list[dict[str, Any]], container: str) -> str:
        for pod in pods:
            try:
                return self._k.pod_log(pod["metadata"]["name"], container)
            except KubeApiError:
                continue
        return ""

    def _job(self, dep: dict[str, Any], step: str, image: str, command: list[str], *, timeout_s: float) -> str:
        run = self._j.run or {}
        manifest = kube_plan.job_manifest(
            dep,
            self._s.container,
            run_id=run["id"],
            step=step,
            image=image,
            command=command,
            deadline_s=int(timeout_s) + 60,
            ttl_s=self._s.job_ttl_s,
        )
        self._j.update_run(jobs=[*run.get("jobs", []), manifest["metadata"]["name"]])
        return self._run_job(manifest, timeout_s=timeout_s)

    def _db_current(self, dep: dict[str, Any], image: str, step: str) -> str | None:
        out = self._job(dep, step, image, ["hse-doc-studio", "db", "current"], timeout_s=self._s.probe_job_timeout_s)
        current, head = plan.parse_db_current(out)
        if current is None and head is None:
            raise _JobError(f"cannot read the database revision from the Job output: {out[-200:]!r}")
        return current

    def _cleanup_jobs(self) -> None:
        try:
            for job in self._k.list_jobs(kube_plan.managed_selector()):
                self._k.delete_job(job["metadata"]["name"])
        except KubeApiError as exc:
            self.emit("preflight", f"old update Jobs were not cleaned up: {exc}", level="warn")

    # ---- обновление ----

    def _update(self, spec: dict[str, Any]) -> None:
        if not plan.is_version(spec["to_version"]):
            raise AbortError("bad_version", f"unsupported version string: {spec['to_version']}")
        dep = self._deployment()
        image = kube_plan.deployment_image(dep, self._s.container)
        if not image:
            raise AbortError("no_container", f"the Deployment has no container named {self._s.container}")
        replicas = kube_plan.deployment_replicas(dep)
        if replicas < 1:
            raise AbortError("api_scaled_down", "the api Deployment is scaled to zero: nothing to update")
        self._cleanup_jobs()
        digest = self._verify(spec, dep, plan.split_image(image)[0])
        new_image = kube_plan.target_image(image, spec["to_version"], digest)
        self._j.update_run(old={"image": image, "replicas": replicas}, new_image=new_image)
        self.emit("preflight", f"checking the new image and reading the database revision ({new_image})")
        try:
            from_rev = self._db_current(dep, new_image, "precheck")
        except _JobError as exc:
            raise AbortError("precheck_failed", f"nothing changed: {exc}") from exc
        self._j.update_run(from_rev=from_rev)
        self.emit("preflight", f"database revision {from_rev or 'none'}", from_revision=from_rev)
        self._swap(spec, dep, new_image)

    def _verify(self, spec: dict[str, Any], dep: dict[str, Any], repo: str) -> str | None:
        verify = spec.get("verify", "digest")
        if verify == "none":
            self.emit("verify", "image verification is off", level="warn")
            return None
        self.emit("verify", f"verifying the release image ({verify})")
        digest = published_digest(self._get, spec)
        if verify == "cosign":
            run = self._j.run or {}
            manifest = kube_plan.cosign_job_manifest(
                dep,
                run_id=run["id"],
                repo=repo,
                digest=digest,
                deadline_s=int(self._s.probe_job_timeout_s) + 60,
                ttl_s=self._s.job_ttl_s,
            )
            try:
                self._run_job(manifest, timeout_s=self._s.probe_job_timeout_s)
            except _JobError as exc:
                raise AbortError("signature_invalid", f"cosign signature check failed: {exc}") from exc
        self.emit("verify", f"image digest {digest[:19]} will be pinned in the Deployment")
        return digest

    def _swap(self, spec: dict[str, Any], dep: dict[str, Any], new_image: str) -> None:
        """Точка невозврата: с остановки любой отказ ведёт к откату образа или, если схема изменилась, к рукам."""
        run = self._j.run or {}
        replicas = run["old"]["replicas"]
        self._j.update_run(stopped=True)
        try:
            self.emit("stop", "scaling the api to zero")
            self._patch(0)
            self._wait_stopped(kube_plan.pod_selector(dep))
            self._j.update_run(migrating=True)
            self.emit("migrate", "applying migrations in a Job on the new image")
            try:
                self._job(
                    dep, "migrate", new_image, ["hse-doc-studio", "db", "upgrade"], timeout_s=self._s.migrate_timeout_s
                )
                to_rev = self._db_current(dep, new_image, "after")
            except _JobError as exc:
                raise _StepError("migration_failed", f"migrations failed: {exc}") from exc
            self._j.update_run(to_rev=to_rev)
            self.emit("migrate", f"database revision {to_rev}", to_revision=to_rev)
            self.emit("restart", "starting the api on the new image")
            self._patch(replicas, new_image)
            self._j.update_run(patched=True)
            self.emit("health", "waiting for the new version to become healthy")
            self._wait_healthy(dep, replicas, new_image)
        except _StepError as exc:
            self._revert(exc.code, exc.message, dep)
            return
        self._j.update_run(healthy=True)
        self._succeed(spec)

    def _wait_healthy(self, dep: dict[str, Any], replicas: int, image: str) -> None:
        deadline = self._mono() + self._c.health_timeout_s
        selector = kube_plan.pod_selector(dep)
        stable_since: float | None = None
        while self._mono() < deadline:
            self.flush()  # события migrate/restart ждали в очереди (api был остановлен)
            if self._healthy_once(selector, replicas, image):
                stable_since = stable_since if stable_since is not None else self._mono()
                if self._mono() - stable_since >= self._c.stable_s:
                    return
            else:
                stable_since = None
            self._sleep(self._s.poll_s)
        raise _StepError("health_timeout", f"the api is not healthy after {int(self._c.health_timeout_s)} s")

    def _healthy_once(self, selector: str, replicas: int, image: str) -> bool:
        """True здоров, None ещё нет; безнадёжный отказ (под не стартует) это исключение `_StepError`."""
        try:
            dep = self._k.get_deployment()
            pods = [p for p in self._k.list_pods(selector) if _pod_image(p, self._s.container) == image]
        except KubeApiError:
            return False
        for pod in pods:
            problem = kube_plan.pod_problem(pod)
            if problem:
                raise _StepError("health_failed", f"the api pod cannot start: {problem}")
        if not kube_plan.rollout_ready(dep, replicas):
            return False
        headers = {"Authorization": f"Bearer {self._c.health_token}"} if self._c.health_token else {}
        try:
            code, _body = self._get(self._c.health_url, headers, 10.0)
        except OSError:
            return False
        return code == 200  # noqa: PLR2004

    def _succeed(self, spec: dict[str, Any]) -> None:
        run = self._j.run or {}
        old = run.get("old") or {}
        last_ok = {
            "to_version": spec["to_version"],
            "from_version": spec["from_version"],
            "from_rev": run.get("from_rev"),
            "to_rev": run.get("to_rev"),
            "old_image": old.get("image"),
            "new_image": run.get("new_image"),
            "replicas": old.get("replicas"),
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

    def _revert(self, code: str, message: str, dep: dict[str, Any]) -> None:
        run = self._j.run or {}
        old = run.get("old") or {}
        self.emit(
            "rollback", f"{message}. Checking whether the database schema changed.", level="error", error_code=code
        )
        changed, to_rev = self._schema_changed(run, dep)
        if changed:
            self._needs_hands(code, message, run, to_rev)
            return
        try:
            self.emit("rollback", "the schema is unchanged: returning the previous image", level="warn")
            self._patch(old["replicas"], old["image"])
            self._wait_healthy(dep, old["replicas"], old["image"])
        except _StepError as exc:
            self.emit(
                "finish",
                f"ROLLBACK FAILED: {exc.message}. Restore by hand: kubectl -n {self._k.namespace} set image "
                f"deployment/{self._s.deployment} {self._s.container}={old['image']} and scale it to "
                f"{old['replicas']}.",
                level="error",
                status="failed",
                error_code="rollback_failed",
                db_restored=False,
            )
            self._j.finish_run()
            return
        self.emit(
            "finish",
            f"{message}. Rolled back to {run.get('from_version')}",
            level="warn",
            status="rolled_back",
            error_code=code,
            db_restored=False,
            from_revision=run.get("from_rev"),
            to_revision=run.get("to_rev"),
        )
        self._j.finish_run()

    def _schema_changed(self, run: dict[str, Any], dep: dict[str, Any]) -> tuple[bool, str | None]:
        """Изменили ли миграции ревизию базы. Не смогли узнать: считаем, что изменили (образ не трогаем)."""
        if not run.get("migrating"):
            return False, None
        try:
            current = self._db_current(dep, run["new_image"], "check")
        except _JobError:
            return True, None
        return current != run.get("from_rev"), current

    def _needs_hands(self, code: str, message: str, run: dict[str, Any], to_rev: str | None) -> None:
        old = run.get("old") or {}
        live = run.get("new_image") if run.get("patched") else old.get("image")
        replicas = old.get("replicas", 1) if run.get("patched") else 0
        jobs = [j for j in run.get("jobs", []) if "migrate" in j]
        self.emit(
            "rollback",
            f"the database schema moved ({run.get('from_rev') or 'none'} -> "
            f"{to_rev or run.get('to_rev') or 'unknown'}) "
            f"and the previous image cannot start on it, so the image is NOT rolled back. "
            f"The Deployment stays as it is: image {live}, replicas {replicas}.",
            level="error",
            from_revision=run.get("from_rev"),
            to_revision=to_rev or run.get("to_rev"),
        )
        steps = kube_plan.instructions(
            namespace=self._k.namespace,
            deployment=self._s.deployment,
            container=self._s.container,
            old_image=str(old.get("image")),
            replicas=int(old.get("replicas", 1)),
            jobs=jobs,
        )
        for step in steps:
            self.emit("rollback", step, level="warn")
        self.emit(
            "finish",
            f"{message}. Manual action is needed: the schema changed, so the previous version cannot be started "
            f"as is. Steps are in the run events (diagnose, fix forward, or restore the pre-update backup).",
            level="error",
            status="failed",
            error_code=NEEDS_HANDS,
            db_restored=False,
            from_revision=run.get("from_rev"),
            to_revision=to_rev or run.get("to_rev"),
        )
        self._j.finish_run()

    def recover(self, reason: str = "the updater restarted in the middle of a run") -> None:
        """Старт после падения пода: незаконченный запуск, дошедший до остановки api, откатывается по журналу."""
        dep = self._deployment()
        self._kj.adopt(dep)
        run = self._j.run
        if run is None:
            return
        if not run.get("stopped"):
            self.emit("finish", reason, level="error", status="cancelled", error_code="updater_restarted")
            self._j.finish_run()
            return
        if run.get("healthy") and run.get("kind") != "rollback":
            self._succeed({"to_version": run["to_version"], "from_version": run["from_version"]})
            return
        if run.get("kind") == "rollback":
            self._rollback_undo(dep, reason)
        else:
            self._revert("updater_restarted", reason, dep)

    # ---- ручной откат ----

    def _manual_rollback(self, spec: dict[str, Any]) -> None:
        last = self._j.data.get("last_ok")
        if not last or last.get("to_version") != spec["from_version"] or not last.get("old_image"):
            raise AbortError("no_previous_version", "the updater has no record of the update to roll back")
        if not last.get("from_rev") or last.get("from_rev") != last.get("to_rev"):
            raise AbortError(
                "schema_changed",
                "the update changed the database schema and there is no snapshot to restore: the previous "
                "version cannot start on it",
            )
        dep = self._deployment()
        current = kube_plan.deployment_image(dep, self._s.container)
        replicas = max(kube_plan.deployment_replicas(dep), 1)
        old_image = str(last["old_image"])
        self._cleanup_jobs()
        try:
            live = self._db_current(dep, old_image, "rbcheck")
        except _JobError as exc:
            raise AbortError("precheck_failed", f"nothing changed: {exc}") from exc
        if live != last.get("to_rev"):
            raise AbortError("schema_ahead", f"the database revision is {live}, newer than the previous version")
        self._j.update_run(old={"image": current, "replicas": replicas}, new_image=old_image, from_rev=live)
        self._j.update_run(stopped=True)
        try:
            self.emit("stop", "scaling the api to zero")
            self._patch(0)
            self._wait_stopped(kube_plan.pod_selector(dep))
            self.emit("restart", "starting the api on the previous image")
            self._patch(replicas, old_image)
            self._wait_healthy(dep, replicas, old_image)
        except _StepError as exc:
            self._rollback_undo(dep, exc.message)
            return
        self.emit("finish", f"rolled back to {spec['to_version']}", status="succeeded", db_restored=False)
        self._j.finish_run(keep_as_last_ok=None)
        self._j.data["last_ok"] = None
        self._j.save()

    def _rollback_undo(self, dep: dict[str, Any], reason: str) -> None:
        """Ручной откат не поднялся: возвращаем образ, что стоял до него."""
        before = (self._j.run or {}).get("old") or {}
        try:
            self._patch(before["replicas"], before["image"])
            self._wait_healthy(dep, before["replicas"], before["image"])
            state = "the previous state is back"
        except _StepError as exc:
            state = (
                f"the api is down: {exc.message}. Restore by hand: kubectl -n {self._k.namespace} set image "
                f"deployment/{self._s.deployment} {self._s.container}={before.get('image')}"
            )
        self.emit(
            "finish",
            f"rollback failed ({reason}); {state}",
            level="error",
            status="failed",
            error_code="rollback_failed",
            db_restored=False,
        )
        self._j.finish_run()


def _pod_started(pod: dict[str, Any]) -> bool:
    status = pod.get("status") or {}
    if status.get("phase") in {"Running", "Succeeded", "Failed"}:
        return True
    return any(
        "running" in (s.get("state") or {}) or "terminated" in (s.get("state") or {})
        for s in status.get("containerStatuses") or []
    )


def _pod_image(pod: dict[str, Any], container: str) -> str:
    for item in (pod.get("spec") or {}).get("containers") or []:
        if item.get("name") == container:
            return str(item.get("image") or "")
    return ""
