"""Исполнитель kubernetes на фейковом кластере: успех, отмена до остановки, откат образа и «нужны руки» при смене схемы.

Часть сценариев идёт через настоящий `UpdateService` (транспорт без HTTP), как у compose: проверяется вся цепочка
«решение api -> исполнитель -> события -> итог в журнале запусков».
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from hse_doc_studio.core.server_update.entities import ReleaseInfo, RunStatus
from hse_doc_studio.infra.update.server_updater import kube_plan
from hse_doc_studio.infra.update.server_updater.config import KubeSettings, UpdaterConfig
from hse_doc_studio.infra.update.server_updater.kube_engine import NEEDS_HANDS, KubeEngine
from hse_doc_studio.infra.update.server_updater.kube_journal import KubeJournal
from hse_doc_studio.use_cases.server_update.service import PollReport

from tests.fakes.docker_stack import digest_doc
from tests.fakes.kube_stack import DEPLOYMENT, NEW_DIGEST, NEW_IMAGE, OLD_IMAGE, REPO, FakeJob, FakeKube
from tests.unit.infra.update.test_server_updater_scenarios import ServiceApi
from tests.unit.use_cases.server_update.test_update_service import Env, configure, make

DIGEST_URL = "https://github.com/x/releases/download/v0.4.0/image-digest.json"


class Rig:
    def __init__(self, tmp: Path, kube: FakeKube, *, verify: str = "digest") -> None:
        self.env: Env = make(current="0.3.1", kind="kubernetes")
        self.kube = kube
        self.api = ServiceApi(self.env.service)
        self.clock = 0.0
        self.pages: dict[str, tuple[int, str]] = {DIGEST_URL: (200, digest_doc())}
        self.verify = verify
        self.config = UpdaterConfig(
            api_url="http://api:8000",
            token="t",
            data_dir=tmp / "updater",
            health_url="http://api:8000/health/ready",
            health_timeout_s=60,
            stable_s=4,
            kube=KubeSettings(deployment=DEPLOYMENT, poll_s=1.0, stop_timeout_s=10, pod_start_timeout_s=20),
        )
        self.journal = KubeJournal(self.config.data_dir / "journal.json", kube)  # type: ignore[arg-type]
        self.engine = self._engine()

    def _engine(self) -> KubeEngine:
        def sleep(s: float) -> None:
            self.clock += s

        return KubeEngine(
            self.config,
            self.kube,  # type: ignore[arg-type]
            self.api,  # type: ignore[arg-type]
            self.journal,
            http_get=self._get,
            sleep=sleep,
            monotonic=lambda: self.clock,
        )

    def restart(self, *, keep_file: bool) -> None:
        """Под апдейтера пересоздан: том (emptyDir) потерян, остались только аннотации Deployment."""
        if not keep_file:
            (self.config.data_dir / "journal.json").unlink(missing_ok=True)
        self.journal = KubeJournal(self.config.data_dir / "journal.json", self.kube)  # type: ignore[arg-type]
        self.engine = self._engine()

    def _get(self, url: str, headers: dict[str, str], timeout: float) -> tuple[int, str]:
        if url in self.pages:
            return self.pages[url]
        return (200, "{}") if self.kube.healthy() else (503, "")

    async def request(self, *, accept_risk: bool = True) -> dict[str, Any]:
        env = self.env
        await configure(env)
        env.source.answer = type(env.source.answer)(
            releases=(ReleaseInfo("0.4.0", digests_url=DIGEST_URL), ReleaseInfo("0.3.1")), checked=True
        )
        await env.service.check_now("boss")
        await env.service.poll(PollReport(updater_version="t", busy=True))
        await env.service.request_update("boss", "0.4.0", accept_risk=accept_risk)
        spec = await env.service.poll(PollReport())
        assert spec is not None
        return {
            "run_id": spec.run_id,
            "kind": spec.kind.value,
            "from_version": spec.from_version,
            "to_version": spec.to_version,
            "verify": self.verify,
            "digests_url": spec.digests_url,
            "restore_db": spec.restore_db,
        }

    async def final(self, spec: dict[str, Any]) -> Any:
        pending, self.api.pending = self.api.pending, []
        for run_id, report in pending:
            await self.env.service.report(run_id, report)
        run = await self.env.runs.get(spec["run_id"])
        assert run is not None
        return run


@pytest.fixture
def kube() -> FakeKube:
    return FakeKube()


def _rig(tmp_path: Path, kube: FakeKube, *, verify: str = "digest") -> Rig:
    return Rig(tmp_path, kube, verify=verify)


async def test__success__pins_the_verified_digest_and_reports_revisions(tmp_path: Path, kube: FakeKube) -> None:
    rig = _rig(tmp_path, kube)
    spec = await rig.request()

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.succeeded
    assert (run.from_revision, run.to_revision) == ("r1", "r2")
    assert kube.image == NEW_IMAGE
    assert kube.patches() == [(0, OLD_IMAGE), (1, NEW_IMAGE)]
    assert kube.db_rev == "r2"
    phases = [e["phase"] for e in rig.api.events]
    assert phases.index("verify") < phases.index("stop") < phases.index("migrate") < phases.index("restart")
    assert phases.index("restart") < phases.index("health") < phases.index("finish")
    assert rig.journal.run is None
    last = kube.last_ok()
    assert last is not None
    assert (last["old_image"], last["new_image"], last["from_rev"], last["to_rev"]) == (
        OLD_IMAGE,
        NEW_IMAGE,
        "r1",
        "r2",
    )
    assert kube.journal() is None, "запуск закончен: аннотация запуска убрана"


async def test__success__migration_jobs_clone_the_api_pod_without_volumes(tmp_path: Path, kube: FakeKube) -> None:
    rig = _rig(tmp_path, kube)
    spec = await rig.request()

    rig.engine.execute(spec)

    manifests = [j.manifest for j in kube.jobs.values()]
    steps = {m["metadata"]["labels"][kube_plan.LABEL_STEP]: m for m in manifests}
    assert set(steps) == {"precheck", "migrate", "after"}
    migrate = steps["migrate"]["spec"]["template"]
    pod = migrate["spec"]
    assert pod["containers"][0]["command"] == ["hse-doc-studio", "db", "upgrade"]
    assert pod["containers"][0]["image"] == NEW_IMAGE
    assert pod["containers"][0]["env"][1]["valueFrom"]["secretKeyRef"]["key"] == "dsn", "DSN из Secret, не значением"
    assert "volumes" not in pod
    assert "volumeMounts" not in pod["containers"][0]
    assert pod["automountServiceAccountToken"] is False
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert migrate["metadata"]["labels"]["app.kubernetes.io/component"] == "update", "не попадает в Service api"
    assert steps["migrate"]["spec"]["backoffLimit"] == 0


async def test__missing_digest__cancelled_and_nothing_touched(tmp_path: Path, kube: FakeKube) -> None:
    rig = _rig(tmp_path, kube)
    rig.pages.clear()
    spec = await rig.request()

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.cancelled
    assert run.error_code == "digest_missing"
    assert kube.patches() == []
    assert kube.image == OLD_IMAGE


async def test__verify_none__installs_by_tag_without_digest(tmp_path: Path, kube: FakeKube) -> None:
    rig = _rig(tmp_path, kube, verify="none")
    rig.pages.clear()
    spec = await rig.request()

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.succeeded
    assert kube.image == f"{REPO}:0.4.0"


async def test__cosign__verified_in_a_job_before_anything_changes(tmp_path: Path, kube: FakeKube) -> None:
    kube.cosign_ok = False
    rig = _rig(tmp_path, kube, verify="cosign")
    spec = await rig.request()

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.cancelled
    assert run.error_code == "signature_invalid"
    cosign = next(
        j.manifest for j in kube.jobs.values() if j.manifest["metadata"]["labels"][kube_plan.LABEL_STEP] == "cosign"
    )
    container = cosign["spec"]["template"]["spec"]["containers"][0]
    assert container["args"][-1] == f"{REPO}@{NEW_DIGEST}"
    assert cosign["spec"]["template"]["spec"]["securityContext"]["runAsNonRoot"] is True
    assert kube.patches() == []


async def test__cosign__valid_signature_continues(tmp_path: Path, kube: FakeKube) -> None:
    rig = _rig(tmp_path, kube, verify="cosign")
    spec = await rig.request()

    rig.engine.execute(spec)

    assert (await rig.final(spec)).status is RunStatus.succeeded


async def test__precheck_cannot_pull_the_image__cancelled_before_stop(tmp_path: Path, kube: FakeKube) -> None:
    kube.pull_fail_images.add(NEW_IMAGE)
    rig = _rig(tmp_path, kube)
    spec = await rig.request()

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.cancelled
    assert run.error_code == "precheck_failed"
    assert "ErrImagePull" in (run.error or "")
    assert kube.patches() == [], "api не останавливали"
    assert kube.replicas == 1


async def test__forbidden__cancelled_with_a_clear_code(tmp_path: Path, kube: FakeKube) -> None:
    kube.patch_status = 403
    rig = _rig(tmp_path, kube)
    spec = await rig.request()

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.cancelled
    assert run.error_code == "kube_forbidden"


async def test__unhealthy_new_version_without_schema_change__image_is_rolled_back(
    tmp_path: Path, kube: FakeKube
) -> None:
    kube.new_head = "r1"  # миграций в релизе нет
    kube.broken_images.add(NEW_IMAGE)
    rig = _rig(tmp_path, kube)
    spec = await rig.request()

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.rolled_back
    assert run.error_code == "health_failed"
    assert (kube.image, kube.replicas) == (OLD_IMAGE, 1)
    assert run.db_restored is False
    assert kube.healthy()


async def test__migration_fails_with_the_schema_untouched__image_and_replicas_are_restored(
    tmp_path: Path, kube: FakeKube
) -> None:
    kube.migration_fails = True
    rig = _rig(tmp_path, kube)
    spec = await rig.request()

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.rolled_back
    assert run.error_code == "migration_failed"
    assert kube.patches() == [(0, OLD_IMAGE), (1, OLD_IMAGE)]
    assert kube.db_rev == "r1"


async def test__unhealthy_after_schema_change__needs_hands_and_the_image_is_not_rolled_back(
    tmp_path: Path, kube: FakeKube
) -> None:
    kube.broken_images.add(NEW_IMAGE)
    rig = _rig(tmp_path, kube)
    spec = await rig.request()

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.failed
    assert run.error_code == NEEDS_HANDS
    assert run.db_restored is False
    assert (run.from_revision, run.to_revision) == ("r1", "r2")
    assert kube.image == NEW_IMAGE, "старый образ не стартует на новой схеме: молчаливого отката нет"
    assert kube.patches() == [(0, OLD_IMAGE), (1, NEW_IMAGE)]
    texts = [e.message for e in run.events]
    assert any("NOT rolled back" in t for t in texts)
    assert any(f"set image deployment/{DEPLOYMENT} api={OLD_IMAGE}" in t for t in texts), "инструкция вернуть образ"
    assert any("Way A" in t for t in texts)
    assert any("kubectl -n studio logs job/hds-upd-migrate" in t for t in texts)
    assert rig.journal.run is None


async def test__migration_fails_after_the_schema_moved__needs_hands_and_the_api_stays_down(
    tmp_path: Path, kube: FakeKube
) -> None:
    kube.migration_fails = True
    kube.migration_advances_rev = True
    rig = _rig(tmp_path, kube)
    spec = await rig.request()

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.failed
    assert run.error_code == NEEDS_HANDS
    assert (kube.image, kube.replicas) == (OLD_IMAGE, 0), "ничего не трогаем: оператор сам решает"
    assert any("replicas 0" in e.message for e in run.events)


async def test__rollback_of_the_image_fails__failed_with_a_manual_command(tmp_path: Path, kube: FakeKube) -> None:
    kube.new_head = "r1"
    kube.broken_images.update({NEW_IMAGE, OLD_IMAGE})
    rig = _rig(tmp_path, kube)
    spec = await rig.request()

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.failed
    assert run.error_code == "rollback_failed"
    assert f"set image deployment/{DEPLOYMENT} api={OLD_IMAGE}" in (run.error or "")


async def test__api_pods_linger_after_scale_down__waits_for_them(tmp_path: Path, kube: FakeKube) -> None:
    kube.pods_linger = 3
    rig = _rig(tmp_path, kube)
    spec = await rig.request()

    rig.engine.execute(spec)

    assert (await rig.final(spec)).status is RunStatus.succeeded


async def test__api_pods_never_stop__reverted_and_cancelled_nothing_is_lost(tmp_path: Path, kube: FakeKube) -> None:
    kube.pods_linger = 10_000
    rig = _rig(tmp_path, kube)
    spec = await rig.request()

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.rolled_back
    assert run.error_code == "stop_timeout"
    assert kube.patches()[-1] == (1, OLD_IMAGE)


async def test__old_update_jobs_are_cleaned_up_at_the_start(tmp_path: Path, kube: FakeKube) -> None:
    rig = _rig(tmp_path, kube)
    kube.jobs["hds-upd-migrate-dead0000"] = FakeJob({}, "failed")
    spec = await rig.request()

    rig.engine.execute(spec)

    assert ("delete_job", "hds-upd-migrate-dead0000") in kube.calls
    assert "hds-upd-migrate-dead0000" not in kube.jobs


# ---- ручной откат ----


async def _updated(tmp_path: Path, kube: FakeKube) -> tuple[Rig, dict[str, Any]]:
    rig = _rig(tmp_path, kube)
    spec = await rig.request()
    rig.engine.execute(spec)
    await rig.final(spec)
    kube.calls.clear()
    return rig, spec


async def _rollback_spec(rig: Rig) -> dict[str, Any]:
    env = rig.env
    env.service._options = replace(env.service._options, current_version="0.4.0")  # noqa: SLF001
    await env.service.poll(PollReport(updater_version="t", busy=True))
    await env.service.request_rollback("boss", restore_db=False)
    spec = await env.service.poll(PollReport())
    assert spec is not None
    return {
        "run_id": spec.run_id,
        "kind": spec.kind.value,
        "from_version": spec.from_version,
        "to_version": spec.to_version,
        "verify": "none",
        "digests_url": "",
        "restore_db": False,
    }


async def test__manual_rollback__schema_unchanged__returns_the_previous_image(tmp_path: Path, kube: FakeKube) -> None:
    kube.new_head = "r1"
    rig, _ = await _updated(tmp_path, kube)
    spec = await _rollback_spec(rig)

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.succeeded
    assert (kube.image, kube.replicas) == (OLD_IMAGE, 1)
    assert rig.journal.data["last_ok"] is None
    assert kube.last_ok() is None


async def test__manual_rollback__schema_changed__refused_before_any_change(tmp_path: Path, kube: FakeKube) -> None:
    rig, _ = await _updated(tmp_path, kube)  # r1 -> r2
    spec = {"run_id": "r-1", "kind": "rollback", "from_version": "0.4.0", "to_version": "0.3.1", "restore_db": False}

    rig.engine.execute(spec)

    final = rig.api.events[-1]
    assert (final["status"], final["error_code"]) == ("cancelled", "schema_changed")
    assert kube.patches() == []


async def test__manual_rollback__someone_migrated_further__schema_ahead(tmp_path: Path, kube: FakeKube) -> None:
    kube.new_head = "r1"
    rig, _ = await _updated(tmp_path, kube)
    kube.db_rev = "r9"
    spec = await _rollback_spec(rig)

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.cancelled
    assert run.error_code == "schema_ahead"
    assert kube.patches() == []


async def test__manual_rollback__previous_image_does_not_start__the_current_one_is_put_back(
    tmp_path: Path, kube: FakeKube
) -> None:
    kube.new_head = "r1"
    rig, _ = await _updated(tmp_path, kube)
    kube.broken_images.add(OLD_IMAGE)
    spec = await _rollback_spec(rig)

    rig.engine.execute(spec)
    run = await rig.final(spec)

    assert run.status is RunStatus.failed
    assert run.error_code == "rollback_failed"
    assert (kube.image, kube.replicas) == (NEW_IMAGE, 1)
    assert kube.healthy()


# ---- смерть пода апдейтера ----


async def test__recover__run_in_annotations_after_the_pod_was_recreated__reverts_the_image(
    tmp_path: Path, kube: FakeKube
) -> None:
    kube.new_head = "r1"
    rig = _rig(tmp_path, kube)
    spec = await rig.request()
    # апдейтер умер сразу после патча образа: аннотация осталась, файла на новом томе нет
    rig.journal.start_run(
        {
            "id": spec["run_id"],
            "kind": "update",
            "to_version": "0.4.0",
            "from_version": "0.3.1",
            "phase": "restart",
            "seq": 3,
            "stopped": True,
            "migrating": False,
            "patched": True,
            "healthy": False,
            "from_rev": "r1",
            "to_rev": "r1",
            "old": {"image": OLD_IMAGE, "replicas": 1},
            "new_image": NEW_IMAGE,
            "jobs": [],
        }
    )
    kube.image, kube.replicas = NEW_IMAGE, 1
    kube.broken_images.add(NEW_IMAGE)
    rig.restart(keep_file=False)

    rig.engine.recover()
    run = await rig.final(spec)

    assert (kube.image, kube.replicas) == (OLD_IMAGE, 1)
    assert run.status is RunStatus.rolled_back
    assert run.error_code == "updater_restarted"
    assert kube.journal() is None


async def test__recover__run_that_was_already_healthy__is_finished_as_a_success(tmp_path: Path, kube: FakeKube) -> None:
    rig = _rig(tmp_path, kube)
    spec = await rig.request()
    rig.journal.start_run(
        {
            "id": spec["run_id"],
            "kind": "update",
            "to_version": "0.4.0",
            "from_version": "0.3.1",
            "phase": "health",
            "seq": 5,
            "stopped": True,
            "migrating": True,
            "patched": True,
            "healthy": True,
            "from_rev": "r1",
            "to_rev": "r2",
            "old": {"image": OLD_IMAGE, "replicas": 1},
            "new_image": NEW_IMAGE,
            "jobs": [],
        }
    )
    kube.image = NEW_IMAGE
    rig.restart(keep_file=False)

    rig.engine.recover()
    run = await rig.final(spec)

    assert run.status is RunStatus.succeeded
    assert kube.image == NEW_IMAGE
    assert json.loads(kube.annotations["hse-doc-studio.io/updater-last-ok"])["old_image"] == OLD_IMAGE


async def test__recover__run_that_never_stopped_the_api__is_cancelled(tmp_path: Path, kube: FakeKube) -> None:
    rig = _rig(tmp_path, kube)
    spec = await rig.request()
    rig.journal.start_run(
        {
            "id": spec["run_id"],
            "kind": "update",
            "to_version": "0.4.0",
            "from_version": "0.3.1",
            "seq": 1,
            "stopped": False,
        }
    )
    rig.restart(keep_file=False)

    rig.engine.recover()
    run = await rig.final(spec)

    assert run.status is RunStatus.cancelled
    assert run.error_code == "updater_restarted"
    assert kube.patches() == []
