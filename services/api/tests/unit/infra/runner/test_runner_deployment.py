"""Отчёт раннера о развёртывании: downward API, cgroup, /proc, исполнители docker и kubernetes, без секретов."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from hse_doc_studio.core.jobs.codec import encode
from hse_doc_studio.core.jobs.deployment import BuildExecutor, ResourceSource, RunnerPlatform
from hse_doc_studio.infra.compile.k8s.config import KubernetesExecutorConfig
from hse_doc_studio.infra.compile.k8s.pod import BuildPodSpec, build_isolation, build_pod_manifest
from hse_doc_studio.infra.compile.latexmk import tex_source
from hse_doc_studio.infra.runner.config import RunnerConfig, RunnerPodInfo
from hse_doc_studio.infra.runner.deployment import HostView, collect_deployment

_STATUS = "Name:\thse-doc-studio\nNoNewPrivs:\t1\nSeccomp:\t2\nCapBnd:\t0000000000000000\n"


def _view(tmp_path: Path, *, env: dict[str, str] | None = None, cgroup: dict[str, str] | None = None) -> HostView:
    proc = tmp_path / "status"
    proc.write_text(_STATUS, encoding="utf-8")
    cg = tmp_path / "cgroup"
    cg.mkdir()
    for name, value in (cgroup or {}).items():
        (cg / name).write_text(value, encoding="utf-8")
    sa = tmp_path / "sa"
    sa.mkdir()
    (sa / "namespace").write_text("studio\n", encoding="utf-8")
    (sa / "token").write_text("secret-sa-token", encoding="utf-8")
    return HostView(
        proc_status=proc,
        cgroup_root=cg,
        sa_dir=sa,
        container_markers=(tmp_path / "no-dockerenv",),
        env=env if env is not None else {},
        uid=1000,
        root=str(tmp_path),
    )


def test__kubernetes_pod__downward_api_resources_and_observed_security(tmp_path: Path) -> None:
    config = RunnerConfig(
        api_url="http://api",
        token="hsrt_secret",
        executor="kubernetes",
        k8s=KubernetesExecutorConfig(namespace="builds", memory_limit="6Gi"),
        pod=RunnerPodInfo(
            namespace="studio",
            name="rel-runner-7d9f8b6c5-x2k4q",
            service_account="rel-runner",
            cpu_request_m=100,
            cpu_limit_m=1000,
            memory_request_mi=256,
            memory_limit_mi=2048,
            ephemeral_request_mi=128,
            ephemeral_limit_mi=2048,
        ),
    )

    report = collect_deployment(config, _view(tmp_path, env={"KUBERNETES_SERVICE_HOST": "10.0.0.1"}))

    assert report.platform is RunnerPlatform.kubernetes
    assert report.executor is BuildExecutor.kubernetes
    assert (report.namespace, report.service_account) == ("studio", "rel-runner")
    assert report.resources is not None
    assert report.resources.source is ResourceSource.pod
    assert (report.resources.cpu_limit, report.resources.memory_limit) == ("1000m", "2048Mi")
    assert report.security is not None
    assert report.security.no_privilege_escalation is True
    assert report.security.seccomp is True
    assert report.security.capabilities_dropped is True
    assert report.security.automount_token is True
    assert report.build is not None
    assert report.build.namespace == "builds"
    assert report.build.resources is not None
    assert report.build.resources.memory_limit == "6Gi"
    text = json.dumps(encode(report))
    assert "secret" not in text
    assert "hsrt_" not in text


def test__old_manifest__namespace_from_service_account_and_limits_from_cgroup(tmp_path: Path) -> None:
    view = _view(
        tmp_path,
        env={"KUBERNETES_SERVICE_HOST": "10.0.0.1", "HOSTNAME": "old-runner-abc-def"},
        cgroup={"cpu.max": "200000 100000\n", "memory.max": "max\n"},
    )

    report = collect_deployment(RunnerConfig(api_url="http://api", executor="kubernetes"), view)

    assert report.namespace == "studio"
    assert report.pod_name == "old-runner-abc-def"
    assert report.service_account is None
    assert report.resources is not None
    assert report.resources.source is ResourceSource.cgroup
    assert report.resources.cpu_limit == "2000m"
    assert report.resources.memory_limit is None


def test__host_with_docker_executor__no_cluster_fields(tmp_path: Path) -> None:
    report = collect_deployment(RunnerConfig(api_url="http://api", build_memory="3g"), _view(tmp_path))

    assert report.platform is RunnerPlatform.host
    assert report.namespace is None
    assert report.resources is None
    assert report.security is not None
    assert report.security.automount_token is None
    assert report.build is not None
    assert report.build.network_disabled is True
    assert report.build.pids_limit == 512
    assert report.build.resources is not None
    assert report.build.resources.memory_limit == "3g"


def test__docker_without_isolation__says_so(tmp_path: Path) -> None:
    report = collect_deployment(RunnerConfig(api_url="http://api", isolation=False), _view(tmp_path))

    assert report.build is not None
    assert report.build.network_disabled is False
    assert report.build.resources is None


def test__build_isolation__matches_the_build_pod_manifest() -> None:
    cfg = KubernetesExecutorConfig(runtime_class_name="gvisor", run_as_user=2000)
    spec = BuildPodSpec(
        name="hds-build-x",
        nonce="n",
        image="tex:1",
        engine="xelatex",
        engine_flag="-xelatex",
        max_iterations=3,
        source=tex_source("main.tex", "doc"),
        compile_id=uuid.uuid4(),
        instance="i",
    )
    pod = build_pod_manifest(spec, cfg, "builds")["spec"]
    container = pod["containers"][0]  # type: ignore[index]
    facts = build_isolation(cfg, "builds", "tex:1")

    assert facts.resources is not None
    assert container["resources"]["limits"] == {  # type: ignore[index]
        "cpu": facts.resources.cpu_limit,
        "memory": facts.resources.memory_limit,
        "ephemeral-storage": facts.resources.ephemeral_limit,
    }
    assert facts.security is not None
    ctx = container["securityContext"]  # type: ignore[index]
    assert facts.security.read_only_root is ctx["readOnlyRootFilesystem"]
    assert facts.security.no_privilege_escalation is (ctx["allowPrivilegeEscalation"] is False)
    assert facts.security.capabilities_dropped is (ctx["capabilities"]["drop"] == ["ALL"])
    assert facts.security.automount_token is pod["automountServiceAccountToken"]  # type: ignore[index]
    assert facts.security.run_as_user == pod["securityContext"]["runAsUser"]  # type: ignore[index]
    assert facts.runtime_class == pod["runtimeClassName"]  # type: ignore[index]
    assert facts.active_deadline_s == pod["activeDeadlineSeconds"]  # type: ignore[index]
