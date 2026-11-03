"""Чистая часть исполнителя kubernetes: манифесты Job, разбор Deployment, Job и подов. Без сети и часов."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from hse_doc_studio.infra.update.server_updater import plan

MANAGER = "hse-doc-studio-updater"
LABEL_RUN = "hse-doc-studio/update-run"
LABEL_STEP = "hse-doc-studio/update-step"
COMPONENT = "app.kubernetes.io/component"
ANNOTATION_RUN = "hse-doc-studio.io/updater-run"
ANNOTATION_LAST_OK = "hse-doc-studio.io/updater-last-ok"
COSIGN_UID = 65532

# Под не оправится сам: ждать здоровья дальше незачем.
_HOPELESS_WAITING = frozenset(
    {
        "CrashLoopBackOff",
        "ImagePullBackOff",
        "ErrImagePull",
        "InvalidImageName",
        "CreateContainerConfigError",
        "CreateContainerError",
        "RunContainerError",
    }
)
_POD_KEYS = (
    "imagePullSecrets",
    "securityContext",
    "nodeSelector",
    "tolerations",
    "affinity",
    "priorityClassName",
    "runtimeClassName",
    "serviceAccountName",
)
_CONTAINER_KEYS = ("imagePullPolicy", "env", "envFrom", "securityContext", "resources")
_SHARED_LABELS = frozenset({"app.kubernetes.io/name", "app.kubernetes.io/instance"})


def find_container(deployment: Mapping[str, Any], name: str) -> dict[str, Any] | None:
    spec = ((deployment.get("spec") or {}).get("template") or {}).get("spec") or {}
    for container in spec.get("containers") or []:
        if container.get("name") == name:
            return dict(container)
    return None


def deployment_image(deployment: Mapping[str, Any], container: str) -> str:
    found = find_container(deployment, container)
    return str((found or {}).get("image") or "")


def deployment_replicas(deployment: Mapping[str, Any]) -> int:
    value = (deployment.get("spec") or {}).get("replicas")
    return value if isinstance(value, int) else 1


def pod_selector(deployment: Mapping[str, Any]) -> str:
    labels = ((deployment.get("spec") or {}).get("selector") or {}).get("matchLabels") or {}
    return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))


def deployment_annotations(deployment: Mapping[str, Any]) -> dict[str, str]:
    return dict((deployment.get("metadata") or {}).get("annotations") or {})


def target_image(current: str, version: str, digest: str | None) -> str:
    """Тот же репозиторий и тег новой версии; с дайджестом kubelet тянет ровно проверенный образ."""
    ref = plan.target_ref(current, version)
    return f"{ref}@{digest}" if digest else ref


def scale_patch(replicas: int, *, container: str | None = None, image: str | None = None) -> dict[str, Any]:
    spec: dict[str, Any] = {"replicas": replicas}
    if container and image:
        spec["template"] = {"spec": {"containers": [{"name": container, "image": image}]}}
    return {"spec": spec}


def journal_patch(run: Mapping[str, Any] | None, last_ok: Mapping[str, Any] | None) -> dict[str, Any]:
    """Состояние запуска в аннотациях Deployment: пережить смерть пода апдейтера. `None` убирает аннотацию."""

    def dump(value: Mapping[str, Any] | None) -> str | None:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":")) if value else None

    return {"metadata": {"annotations": {ANNOTATION_RUN: dump(run), ANNOTATION_LAST_OK: dump(last_ok)}}}


def read_annotation(deployment: Mapping[str, Any], key: str) -> dict[str, Any] | None:
    raw = deployment_annotations(deployment).get(key)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def job_labels(run_id: str, step: str) -> dict[str, str]:
    return {"app.kubernetes.io/managed-by": MANAGER, LABEL_RUN: run_id, LABEL_STEP: step}


def managed_selector() -> str:
    return f"app.kubernetes.io/managed-by={MANAGER}"


def job_name(run_id: str, step: str) -> str:
    return f"hds-upd-{step}-{run_id.replace('-', '')[:8]}"[:63].rstrip("-")


def _pod_labels(deployment: Mapping[str, Any], run_id: str, step: str) -> dict[str, str]:
    template = (deployment.get("spec") or {}).get("template") or {}
    selector = ((deployment.get("spec") or {}).get("selector") or {}).get("matchLabels") or {}
    labels = {
        k: str(v)
        for k, v in ((template.get("metadata") or {}).get("labels") or {}).items()
        if k not in selector or k in _SHARED_LABELS
    }
    # метка выбора Service у api (`component: api`) здесь заменена, иначе под Job получал бы трафик
    return {**labels, **job_labels(run_id, step), COMPONENT: "update"}


def job_manifest(  # noqa: PLR0913
    deployment: Mapping[str, Any],
    container: str,
    *,
    run_id: str,
    step: str,
    image: str,
    command: Sequence[str],
    deadline_s: int,
    ttl_s: int,
) -> dict[str, Any]:
    """Job из шаблона пода api: то же окружение (DSN и ключи из Secret), securityContext, pull-секреты и узлы.

    Тома не переносятся: миграциям том проектов не нужен, а ReadWriteOnce том занят самим api. Токен ServiceAccount
    в под не монтируется.
    """
    src = find_container(deployment, container) or {}
    pod_spec = ((deployment.get("spec") or {}).get("template") or {}).get("spec") or {}
    body: dict[str, Any] = {k: src[k] for k in _CONTAINER_KEYS if k in src}
    body.update(name=step, image=image, command=list(command))
    pod: dict[str, Any] = {k: pod_spec[k] for k in _POD_KEYS if k in pod_spec}
    pod.update(restartPolicy="Never", automountServiceAccountToken=False, containers=[body])
    return _job(run_id, step, pod, _pod_labels(deployment, run_id, step), deadline_s, ttl_s)


def cosign_job_manifest(  # noqa: PLR0913
    deployment: Mapping[str, Any], *, run_id: str, repo: str, digest: str, deadline_s: int, ttl_s: int
) -> dict[str, Any]:
    """Проверка подписи cosign под restricted: образ cosign, `verify` по дайджесту, HOME на emptyDir."""
    args = plan.cosign_verify_command(repo, digest)
    verify = args[args.index("verify") :]
    pod_spec = ((deployment.get("spec") or {}).get("template") or {}).get("spec") or {}
    pod: dict[str, Any] = {k: pod_spec[k] for k in ("imagePullSecrets", "nodeSelector", "tolerations") if k in pod_spec}
    pod.update(
        restartPolicy="Never",
        automountServiceAccountToken=False,
        securityContext={
            "runAsNonRoot": True,
            "runAsUser": COSIGN_UID,
            "runAsGroup": COSIGN_UID,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        containers=[
            {
                "name": "cosign",
                "image": plan.COSIGN_IMAGE,
                "args": verify,
                "env": [{"name": "HOME", "value": "/tmp"}],  # noqa: S108 — emptyDir пода
                "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}},
                "volumeMounts": [{"name": "tmp", "mountPath": "/tmp"}],  # noqa: S108
            }
        ],
        volumes=[{"name": "tmp", "emptyDir": {}}],
    )
    return _job(run_id, "cosign", pod, _pod_labels(deployment, run_id, "cosign"), deadline_s, ttl_s)


def _job(
    run_id: str, step: str, pod: dict[str, Any], labels: dict[str, str], deadline_s: int, ttl_s: int
) -> dict[str, Any]:
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": job_name(run_id, step), "labels": job_labels(run_id, step)},
        "spec": {
            "backoffLimit": 0,
            "activeDeadlineSeconds": deadline_s,
            "ttlSecondsAfterFinished": ttl_s,
            "template": {"metadata": {"labels": labels}, "spec": pod},
        },
    }


def job_outcome(job: Mapping[str, Any]) -> str:
    """`succeeded`, `failed` или `running` по статусу Job."""
    status = job.get("status") or {}
    for cond in status.get("conditions") or []:
        if cond.get("status") == "True" and cond.get("type") == "Complete":
            return "succeeded"
        if cond.get("status") == "True" and cond.get("type") == "Failed":
            return "failed"
    if int(status.get("succeeded") or 0) > 0:
        return "succeeded"
    if int(status.get("failed") or 0) > 0:
        return "failed"
    return "running"


def job_pod_selector(name: str) -> str:
    return f"job-name={name}"


def pod_problem(pod: Mapping[str, Any]) -> str | None:
    """Почему под уже не оправится (пусто: ещё ждём или работает). Текст идёт в событие запуска."""
    status = pod.get("status") or {}
    if status.get("phase") == "Failed" and status.get("reason") != "Evicted":
        return str(status.get("message") or status.get("reason") or "pod failed")
    for item in (status.get("containerStatuses") or []) + (status.get("initContainerStatuses") or []):
        state = item.get("state") or {}
        waiting = state.get("waiting") or {}
        reason = str(waiting.get("reason") or "")
        if reason in _HOPELESS_WAITING:
            return f"{reason}: {waiting.get('message') or ''}".strip(": ")
        last = (item.get("lastState") or {}).get("terminated") or {}
        if last and int(item.get("restartCount") or 0) > 0:
            return f"the container restarted ({last.get('reason') or 'terminated'}, exit code {last.get('exitCode')})"
    return None


def pod_unschedulable(pod: Mapping[str, Any]) -> str | None:
    for cond in (pod.get("status") or {}).get("conditions") or []:
        if (
            cond.get("type") == "PodScheduled"
            and cond.get("status") == "False"
            and cond.get("reason") == "Unschedulable"
        ):
            return str(cond.get("message") or "Unschedulable")
    return None


def rollout_ready(deployment: Mapping[str, Any], replicas: int) -> bool:
    """Deployment применил последнюю версию спецификации и все нужные реплики готовы."""
    meta = deployment.get("metadata") or {}
    status = deployment.get("status") or {}
    if int(status.get("observedGeneration") or 0) < int(meta.get("generation") or 0):
        return False
    ready = int(status.get("readyReplicas") or 0)
    updated = int(status.get("updatedReplicas") or 0)
    total = int(status.get("replicas") or 0)
    return ready >= replicas and updated >= replicas and total == replicas


def instructions(  # noqa: PLR0913
    *, namespace: str, deployment: str, container: str, old_image: str, replicas: int, jobs: Sequence[str]
) -> list[str]:
    """Шаги оператору, когда миграции изменили схему и образ откатывать нельзя. Каждый пункт это отдельное событие."""
    ns = f"-n {namespace}"
    logs = "; ".join(f"kubectl {ns} logs job/{name}" for name in jobs)
    diagnose = (
        f"Diagnose: kubectl {ns} describe deployment/{deployment}; kubectl {ns} logs deployment/{deployment} --tail=100"
    )
    way_a = (
        "Way A, fix forward: remove the cause (configuration, Secret, resources, a broken migration). The Deployment "
        "retries by itself and the Studio comes back; for a half-applied migration run helm upgrade with the target "
        "image.tag, its pre-upgrade Job finishes the migrations."
    )
    way_b = (
        "Way B, return to the old version: restore the database from the backup taken before the update (Backups, "  # noqa: S608
        f"or your database tooling), then kubectl {ns} set image deployment/{deployment} {container}={old_image} and "
        f"kubectl {ns} scale deployment/{deployment} --replicas={replicas}."
    )
    return [diagnose + (f"; {logs}" if logs else ""), way_a, way_b]
