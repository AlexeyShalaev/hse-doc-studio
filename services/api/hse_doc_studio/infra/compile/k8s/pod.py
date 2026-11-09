"""Манифест пода сборки: restricted по Pod Security, без сети и токенов, сценарий latexmk с маркерами."""

from __future__ import annotations

import secrets
import shlex
import uuid
from dataclasses import dataclass

from hse_doc_studio.core.jobs.deployment import BuildIsolation, ResourceFigures, ResourceSource, SecurityFacts
from hse_doc_studio.infra.compile.k8s.config import KubernetesExecutorConfig
from hse_doc_studio.infra.compile.latexmk import (
    NONROOT_FORMAT_PREPARE,
    NONROOT_TEX_ENV,
    REPRODUCIBLE_TEX_ENV,
    TEX_SEARCH_ENV,
    TexSource,
    latexmk_argv,
    texcount_command,
)

CONTAINER = "tex"
POD_NAME_PREFIX = "hds-build-"
STATE_DIR = "/tmp/.hds"  # noqa: S108
READY_MARKER = f"{STATE_DIR}/ready"
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


def build_script(spec: BuildPodSpec) -> str:
    """POSIX sh: ждёт вход, собирает, печатает маркеры с nonce и спит до удаления пода (выход забирает exec).

    Итог (код latexmk и вывод texcount) пишется ещё и в файлы `STATE_DIR`: если поток лога замолчит, исполнитель
    прочитает их через exec (`probe_command`). Строки texcount идут через awk: тот завершает каждую строку
    переводом строки, даже если texcount его не напечатал (при ошибках разбора он кончает вывод на
    « (errors:N)» без перевода строки, и следующий маркер прилипал к этой строке).
    """
    src = spec.source
    launcher = ["sh", "-c", NONROOT_FORMAT_PREPARE, spec.engine]
    latexmk = shlex.join([*launcher, *latexmk_argv(spec.engine_flag, spec.max_iterations, src)])
    words = texcount_command(src.basename, chars=False)
    chars = texcount_command(src.basename, chars=True)
    return "\n".join(
        [
            "set -u",
            'n="$HDS_NONCE"',
            f"d={STATE_DIR}",
            f"while [ ! -f {READY_MARKER} ]; do sleep 0.2; done",
            f"cd {shlex.quote(src.workdir)} && {latexmk} 2>&1",
            "rc=$?",
            'echo "$rc" > "$d/rc"',
            'echo "$n:exit:$rc"',
            'if [ "$rc" = 0 ]; then',
            f'  {words} > "$d/words"',
            '  awk -v p="$n:words:" \'{ print p $0 }\' "$d/words"',
            f'  {chars} > "$d/chars"',
            '  awk -v p="$n:chars:" \'{ print p $0 }\' "$d/chars"',
            "fi",
            'touch "$d/end"',
            'echo "$n:end:"',
            "while :; do sleep 3600; done",
        ]
    )


def probe_command() -> list[str]:
    """Итог сборки из файлов `STATE_DIR`: `rc:<код>`, после конца ещё `end`, `words:…` и `chars:…` построчно."""
    return [
        "sh",
        "-c",
        (
            f"cd {STATE_DIR} || exit 0; "
            '[ -f rc ] && echo "rc:$(cat rc)"; '
            "[ -f end ] || exit 0; "
            "echo end; "
            "[ -f words ] && awk '{ print \"words:\" $0 }' words; "
            "[ -f chars ] && awk '{ print \"chars:\" $0 }' chars; "
            "exit 0"
        ),
    ]


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
    env = [{"name": name, "value": value} for name, value in (*TEX_SEARCH_ENV, *REPRODUCIBLE_TEX_ENV, *NONROOT_TEX_ENV)]
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
    if cfg.fonts_claim:
        mounts.append({"name": "fonts", "mountPath": cfg.fonts_mount_target, "readOnly": True})
        volumes.append({"name": "fonts", "persistentVolumeClaim": {"claimName": cfg.fonts_claim, "readOnly": True}})
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
    if cfg.owns_builds_in(namespace):
        # Удалили под раннера: сборщик мусора Kubernetes удалит и его поды сборки. В чужом namespace владельца
        # не ставим: такую ссылку Kubernetes считает недействительной и сразу удаляет под; там поды без
        # раннера убирает его же уборка при старте (sweep) и activeDeadlineSeconds.
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
                    "requests": {
                        "cpu": cfg.cpu_request,
                        "memory": cfg.memory_request,
                        "ephemeral-storage": cfg.ephemeral_storage_request,
                    },
                    "limits": {
                        "cpu": cfg.cpu_limit,
                        "memory": cfg.memory_limit,
                        "ephemeral-storage": cfg.ephemeral_storage_limit,
                    },
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


def build_isolation(cfg: KubernetesExecutorConfig, namespace: str, image: str) -> BuildIsolation:
    """Что получат поды сборки по `build_pod_manifest`: для отчёта раннера в админку (тест сверяет с манифестом)."""
    return BuildIsolation(
        namespace=namespace,
        image=image or None,
        resources=ResourceFigures(
            cpu_request=cfg.cpu_request,
            cpu_limit=cfg.cpu_limit,
            memory_request=cfg.memory_request,
            memory_limit=cfg.memory_limit,
            ephemeral_request=cfg.ephemeral_storage_request,
            ephemeral_limit=cfg.ephemeral_storage_limit,
            source=ResourceSource.config,
        ),
        work_size_limit=cfg.work_size_limit,
        tmp_size_limit=cfg.tmp_size_limit,
        active_deadline_s=cfg.active_deadline_s,
        runtime_class=cfg.runtime_class_name or None,
        security=SecurityFacts(
            run_as_non_root=True,
            run_as_user=cfg.run_as_user,
            read_only_root=True,
            no_privilege_escalation=True,
            seccomp=True,
            capabilities_dropped=True,
            automount_token=False,
        ),
    )
