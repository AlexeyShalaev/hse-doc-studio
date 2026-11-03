"""Фейковый кластер с Deployment api: достаточно честный, чтобы прогнать сценарии исполнителя kubernetes.

Deployment принимает те же патчи, что шлёт движок (replicas и образ контейнера, аннотации журнала), поды появляются
по `replicas` и образу, Job выполняются мгновенно по своей команде (`db current`, `db upgrade`, cosign). Ручки-«поломки»
лежат в полях класса, журнал вызовов в `calls`.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from hse_doc_studio.infra.compile.k8s.api import KubeApiError
from hse_doc_studio.infra.update.server_updater.kube import MERGE

REPO = "ghcr.io/alexeyshalaev/hse-doc-studio"
NAMESPACE = "studio"
DEPLOYMENT = "rel-hse-doc-studio-api"
OLD_IMAGE = f"{REPO}:0.3.1"
NEW_DIGEST = "sha256:" + "a" * 64
NEW_IMAGE = f"{REPO}:0.4.0@{NEW_DIGEST}"
SELECTOR = {
    "app.kubernetes.io/name": "hse-doc-studio",
    "app.kubernetes.io/instance": "rel",
    "app.kubernetes.io/component": "api",
}


@dataclass
class FakeJob:
    manifest: dict[str, Any]
    outcome: str  # succeeded, failed, running
    log: str = ""
    waiting: str = ""  # причина ожидания пода (ErrImagePull)


@dataclass
class FakeKube:
    image: str = OLD_IMAGE
    replicas: int = 1
    db_rev: str = "r1"
    new_head: str = "r2"
    old_head: str = "r1"
    namespace: str = NAMESPACE
    generation: int = 1
    annotations: dict[str, str] = field(default_factory=dict)
    calls: list[tuple[str, Any]] = field(default_factory=list)
    jobs: dict[str, FakeJob] = field(default_factory=dict)
    # поломки
    broken_images: set[str] = field(default_factory=set)  # под уходит в CrashLoopBackOff
    pull_fail_images: set[str] = field(default_factory=set)  # Job не стартует: ErrImagePull
    migration_fails: bool = False
    migration_advances_rev: bool = False  # миграция упала, но часть ревизий уже применена
    cosign_ok: bool = True
    patch_status: int | None = None  # код ошибки на патч Deployment (403: нет прав)
    pods_linger: int = 0  # столько опросов старые поды ещё видны после replicas=0
    _lingering: int = 0

    def head_of(self, image: str) -> str:
        return self.new_head if ":0.4.0" in image else self.old_head

    # ---- Deployment ----

    def get_deployment(self) -> dict[str, Any]:
        ready = self.replicas if self._pods_ok() else 0
        return {
            "metadata": {"name": DEPLOYMENT, "generation": self.generation, "annotations": dict(self.annotations)},
            "spec": {
                "replicas": self.replicas,
                "selector": {"matchLabels": SELECTOR},
                "template": {
                    "metadata": {"labels": dict(SELECTOR)},
                    "spec": {
                        "securityContext": {"runAsNonRoot": True, "seccompProfile": {"type": "RuntimeDefault"}},
                        "imagePullSecrets": [{"name": "pull"}],
                        "volumes": [{"name": "data", "persistentVolumeClaim": {"claimName": "data"}}],
                        "containers": [
                            {
                                "name": "api",
                                "image": self.image,
                                "imagePullPolicy": "IfNotPresent",
                                "ports": [{"name": "http", "containerPort": 8000}],
                                "env": [
                                    {"name": "HSE_STUDIO__MODE", "value": "server"},
                                    {
                                        "name": "HSE_STUDIO__DB__DSN",
                                        "valueFrom": {"secretKeyRef": {"name": "s", "key": "dsn"}},
                                    },
                                ],
                                "volumeMounts": [{"name": "data", "mountPath": "/data"}],
                                "securityContext": {
                                    "allowPrivilegeEscalation": False,
                                    "capabilities": {"drop": ["ALL"]},
                                },
                                "resources": {"requests": {"cpu": "250m"}},
                            }
                        ],
                    },
                },
            },
            "status": {
                "observedGeneration": self.generation,
                "replicas": self.replicas,
                "updatedReplicas": self.replicas,
                "readyReplicas": ready,
            },
        }

    def _pods_ok(self) -> bool:
        return self.replicas > 0 and self.image not in self.broken_images

    def healthy(self) -> bool:
        return self._pods_ok()

    def patch_deployment(self, patch: dict[str, Any], *, content_type: str = "") -> dict[str, Any]:
        if self.patch_status:
            raise KubeApiError("deployments.apps is forbidden", status=self.patch_status)
        if content_type == MERGE:
            for key, value in patch["metadata"]["annotations"].items():
                if value is None:
                    self.annotations.pop(key, None)
                else:
                    self.annotations[key] = value
            self.calls.append(("annotate", sorted(patch["metadata"]["annotations"])))
            return self.get_deployment()
        spec = patch["spec"]
        self.replicas = spec["replicas"]
        for container in (spec.get("template") or {}).get("spec", {}).get("containers", []):
            self.image = container["image"]
        self.generation += 1
        if self.replicas == 0:
            self._lingering = self.pods_linger
        self.calls.append(("patch", (self.replicas, self.image)))
        return self.get_deployment()

    # ---- поды ----

    def list_pods(self, selector: str) -> list[dict[str, Any]]:
        if selector.startswith("job-name="):
            job = self.jobs.get(selector.removeprefix("job-name="))
            return [self._job_pod(selector.removeprefix("job-name="), job)] if job else []
        if self.replicas == 0:
            if self._lingering > 0:
                self._lingering -= 1
                return [self._pod(self.image, broken=False)]
            return []
        return [self._pod(self.image, broken=self.image in self.broken_images)]

    @staticmethod
    def _pod(image: str, *, broken: bool) -> dict[str, Any]:
        status: dict[str, Any] = {
            "phase": "Running",
            "containerStatuses": [{"state": {"running": {}}, "restartCount": 0}],
        }
        if broken:
            status["containerStatuses"] = [
                {
                    "state": {"waiting": {"reason": "CrashLoopBackOff", "message": "back-off"}},
                    "lastState": {"terminated": {"reason": "Error", "exitCode": 1}},
                    "restartCount": 3,
                }
            ]
        return {
            "metadata": {"name": "api-0"},
            "spec": {"containers": [{"name": "api", "image": image}]},
            "status": status,
        }

    @staticmethod
    def _job_pod(name: str, job: FakeJob) -> dict[str, Any]:
        if job.waiting:
            status: dict[str, Any] = {
                "phase": "Pending",
                "containerStatuses": [{"state": {"waiting": {"reason": job.waiting, "message": "pull failed"}}}],
            }
        else:
            phase = {"succeeded": "Succeeded", "failed": "Failed"}.get(job.outcome, "Running")
            status = {"phase": phase, "containerStatuses": [{"state": {"terminated": {"exitCode": 0}}}]}
        return {"metadata": {"name": f"{name}-x"}, "spec": {}, "status": status}

    def pod_log(self, name: str, container: str) -> str:
        job = self.jobs.get(name.removesuffix("-x"))
        return job.log if job else ""

    # ---- Job ----

    def create_job(self, manifest: dict[str, Any]) -> None:
        name = manifest["metadata"]["name"]
        if name in self.jobs:
            raise KubeApiError("already exists", status=409)
        container = manifest["spec"]["template"]["spec"]["containers"][0]
        image = container["image"]
        job = FakeJob(manifest, "succeeded")
        self.calls.append(("job", (container["name"], image)))
        if image in self.pull_fail_images:
            job.outcome, job.waiting = "running", "ErrImagePull"
        elif container["name"] == "cosign":
            job.outcome = "succeeded" if self.cosign_ok else "failed"
            job.log = "" if self.cosign_ok else "no matching signatures"
        else:
            self._run(job, container["command"], image)
        self.jobs[name] = job

    def _run(self, job: FakeJob, command: list[str], image: str) -> None:
        if command[-2:] == ["db", "current"]:
            job.log = f"current: {self.db_rev}\nhead: {self.head_of(image)}\n"
        elif command[-2:] == ["db", "upgrade"]:
            if self.migration_fails:
                if self.migration_advances_rev:
                    self.db_rev = self.head_of(image)
                job.outcome, job.log = "failed", "alembic: migration failed"
            else:
                self.db_rev = self.head_of(image)

    def get_job(self, name: str) -> dict[str, Any] | None:
        job = self.jobs.get(name)
        if job is None:
            return None
        status = {"succeeded": {"succeeded": 1}, "failed": {"failed": 1}}.get(job.outcome, {})
        return {"metadata": {"name": name}, "status": status}

    def list_jobs(self, selector: str) -> list[dict[str, Any]]:
        return [{"metadata": {"name": n}} for n in self.jobs]

    def delete_job(self, name: str) -> None:
        self.calls.append(("delete_job", name))
        self.jobs.pop(name, None)

    # ---- вспомогательное для тестов ----

    def journal(self) -> dict[str, Any] | None:
        raw = self.annotations.get("hse-doc-studio.io/updater-run")
        return json.loads(raw) if raw else None

    def last_ok(self) -> dict[str, Any] | None:
        raw = self.annotations.get("hse-doc-studio.io/updater-last-ok")
        return json.loads(raw) if raw else None

    def patches(self) -> list[tuple[int, str]]:
        return [args for kind, args in self.calls if kind == "patch"]
