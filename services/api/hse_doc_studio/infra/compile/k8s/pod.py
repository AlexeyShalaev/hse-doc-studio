"""Манифест пода сборки: restricted по Pod Security, без сети и токенов, сценарий latexmk с маркерами."""

from __future__ import annotations

import secrets
import shlex
import uuid
from dataclasses import dataclass

from hse_doc_studio.infra.compile.k8s.config import KubernetesExecutorConfig
from hse_doc_studio.infra.compile.latexmk import (
    NONROOT_FORMAT_PREPARE,
    NONROOT_TEX_ENV,
    TEX_SEARCH_ENV,
    TexSource,
    latexmk_argv,
    texcount_command,
)

CONTAINER = "tex"
POD_NAME_PREFIX = "hds-build-"
READY_MARKER = "/tmp/.hds/ready"  # noqa: S108
CACHE_MOUNT = "/cache"

LABEL_MANAGED_BY = "app.kubernetes.io/managed-by"
MANAGED_BY = "hse-doc-studio-runner"
LABEL_COMPONENT = "hse-doc-studio/component"
COMPONENT_BUILD = "build"
LABEL_RUNNER = "hse-doc-studio/runner"
LABEL_JOB = "hse-doc-studio/job"


@dataclass(frozen=True)
class BuildPodSpec:
    name: str
    nonce: str
    image: str
    engine: str
    engine_flag: str
    max_iterations: int
    source: TexSource
    compile_id: uuid.UUID
    instance: str


def new_pod_name(compile_id: uuid.UUID) -> str:
    return f"{POD_NAME_PREFIX}{compile_id.hex[:8]}-{secrets.token_hex(4)}"


def build_selector(instance: str) -> str:
    return f"{LABEL_COMPONENT}={COMPONENT_BUILD},{LABEL_RUNNER}={instance}"


def marker(nonce: str, kind: str) -> str:
    return f"{nonce}:{kind}:"


def build_script(spec: BuildPodSpec) -> str:
    """POSIX sh: ждёт вход, собирает, печатает маркеры с nonce и спит до удаления пода (выход забирает exec)."""
    src = spec.source
    launcher = ["sh", "-c", NONROOT_FORMAT_PREPARE, spec.engine]
    latexmk = shlex.join([*launcher, *latexmk_argv(spec.engine_flag, spec.max_iterations, src)])
    words = texcount_command(src.basename, chars=False)
    chars = texcount_command(src.basename, chars=True)
    return "\n".join(
        [
            "set -u",
            'n="$HDS_NONCE"',
            f"while [ ! -f {READY_MARKER} ]; do sleep 0.2; done",
            f"cd {shlex.quote(src.workdir)} && {latexmk} 2>&1",
            "rc=$?",
            'echo "$n:exit:$rc"',
            'if [ "$rc" = 0 ]; then',
            f'  {words} | sed "s/^/$n:words:/"',
            f'  {chars} | sed "s/^/$n:chars:/"',
            "fi",
            'echo "$n:end:"',
            "while :; do sleep 3600; done",
        ]
    )


def upload_command(size: int) -> list[str]:
    """Вход tar-ом ровно `size` байт: в протоколе exec v4 stdin не закрыть отдельно от соединения."""
    marker_dir = READY_MARKER.rsplit("/", 1)[0]
    return [
        "sh",
        "-c",
        f"mkdir -p {marker_dir} && head -c {int(size)} | tar -x -f - -C /work && touch {READY_MARKER}",
    ]


def download_command(build_rel: str) -> list[str]:
    return ["tar", "-c", "-f", "-", "-C", "/work", build_rel]


def build_pod_manifest(spec: BuildPodSpec, cfg: KubernetesExecutorConfig, namespace: str) -> dict[str, object]:
    env = [{"name": name, "value": value} for name, value in (*TEX_SEARCH_ENV, *NONROOT_TEX_ENV)]
    env.append({"name": "HDS_NONCE", "value": spec.nonce})
    mounts: list[dict[str, object]] = [
        {"name": "work", "mountPath": "/work"},
        {"name": "tmp", "mountPath": "/tmp"},  # noqa: S108
    ]
    volumes: list[dict[str, object]] = [
        {"name": "work", "emptyDir": {"sizeLimit": cfg.work_size_limit}},
        {"name": "tmp", "emptyDir": {"sizeLimit": cfg.tmp_size_limit}},
    ]
    if cfg.tex_cache_claim:
        # Формат движка остаётся в /tmp: параллельные поды не пишут один файл формата.
        env += [
            {"name": "TEXMFCACHE", "value": f"{CACHE_MOUNT}/texmf-cache"},
            {"name": "XDG_CACHE_HOME", "value": f"{CACHE_MOUNT}/xdg"},
        ]
        mounts.append({"name": "tex-cache", "mountPath": CACHE_MOUNT})
        volumes.append({"name": "tex-cache", "persistentVolumeClaim": {"claimName": cfg.tex_cache_claim}})
    metadata: dict[str, object] = {
        "name": spec.name,
        "namespace": namespace,
        "labels": {
            LABEL_MANAGED_BY: MANAGED_BY,
            LABEL_COMPONENT: COMPONENT_BUILD,
            LABEL_RUNNER: spec.instance,
            LABEL_JOB: str(spec.compile_id),
        },
    }
    if cfg.owner_pod_name and cfg.owner_pod_uid:
        # Удалили под раннера: сборщик мусора Kubernetes удалит и его поды сборки.
        metadata["ownerReferences"] = [
            {"apiVersion": "v1", "kind": "Pod", "name": cfg.owner_pod_name, "uid": cfg.owner_pod_uid}
        ]
    pod_spec: dict[str, object] = {
        "restartPolicy": "Never",
        "activeDeadlineSeconds": cfg.active_deadline_s,
        "terminationGracePeriodSeconds": 0,
        "automountServiceAccountToken": False,
        "enableServiceLinks": False,
        "securityContext": {
            "runAsNonRoot": True,
            "runAsUser": cfg.run_as_user,
            "runAsGroup": cfg.run_as_group,
            "fsGroup": cfg.fs_group,
            "seccompProfile": {"type": "RuntimeDefault"},
        },
        "containers": [
            {
                "name": CONTAINER,
                "image": spec.image,
                "imagePullPolicy": cfg.image_pull_policy,
                "command": ["sh", "-c", build_script(spec)],
                "workingDir": "/work",
                "env": env,
                "resources": {
                    "requests": {"cpu": cfg.cpu_request, "memory": cfg.memory_request},
                    "limits": {"cpu": cfg.cpu_limit, "memory": cfg.memory_limit},
                },
                "securityContext": {
                    "allowPrivilegeEscalation": False,
                    "readOnlyRootFilesystem": True,
                    "runAsNonRoot": True,
                    "capabilities": {"drop": ["ALL"]},
                    "seccompProfile": {"type": "RuntimeDefault"},
                },
                "volumeMounts": mounts,
            }
        ],
        "volumes": volumes,
    }
    pod_spec.update(_placement(cfg))
    return {"apiVersion": "v1", "kind": "Pod", "metadata": metadata, "spec": pod_spec}


def _placement(cfg: KubernetesExecutorConfig) -> dict[str, object]:
    """Необязательные поля размещения и запуска: только заданные, чтобы не перекрыть умолчания кластера."""
    fields: dict[str, object] = {
        "nodeSelector": dict(cfg.node_selector),
        "tolerations": [dict(t) for t in cfg.tolerations],
        "priorityClassName": cfg.priority_class_name,
        "runtimeClassName": cfg.runtime_class_name,
        "imagePullSecrets": [{"name": name} for name in cfg.image_pull_secrets],
    }
    return {key: value for key, value in fields.items() if value}
