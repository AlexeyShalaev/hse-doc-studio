"""Helm-чарт (deploy/helm/hse-doc-studio): lint, golden-рендер, одна реплика Recreate, миграции pre-upgrade."""

import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

import pytest
import yaml
from hse_doc_studio.api.config import Settings
from hse_doc_studio.infra.runner.config import RunnerConfig
from pydantic import BaseModel

_CHART = Path(__file__).resolve().parents[4] / "deploy" / "helm" / "hse-doc-studio"
_VALUES = _CHART / "ci" / "values-test.yaml"
_GOLDEN = _CHART / "ci" / "rendered.golden.yaml"
_K8S_VALUES = _CHART / "ci" / "values-kubernetes.yaml"
_K8S_GOLDEN = _CHART / "ci" / "rendered-kubernetes.golden.yaml"

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm не установлен")


def _helm(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["helm", *args], capture_output=True, text=True, encoding="utf-8", check=False)  # noqa: S603, S607


def _render(*extra: str) -> list[dict[str, Any]]:
    result = _helm("template", "rel", str(_CHART), "-f", str(_VALUES), *extra)
    assert result.returncode == 0, result.stderr
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def _by_kind(docs: list[dict[str, Any]], kind: str) -> list[dict[str, Any]]:
    return [d for d in docs if d["kind"] == kind]


def _paths(model: type[BaseModel], prefix: str = "") -> set[str]:
    names: set[str] = set()
    for name, field in model.model_fields.items():
        names.add(f"{prefix}{name}".upper())
        inner = field.annotation
        for candidate in (inner, *getattr(inner, "__args__", ())):
            if isinstance(candidate, type) and issubclass(candidate, BaseModel):
                names |= _paths(candidate, f"{prefix}{name}__")
    return names


def _squeeze(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.strip()]


def test_lint() -> None:
    result = _helm("lint", str(_CHART), "-f", str(_VALUES), "--strict")
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("values", "golden_path"),
    [((_VALUES,), _GOLDEN), ((_VALUES, _K8S_VALUES), _K8S_GOLDEN)],
    ids=["docker", "kubernetes"],
)
def test_template_matches_golden(values: tuple[Path, ...], golden_path: Path) -> None:
    args = [arg for path in values for arg in ("-f", str(path))]
    result = _helm("template", "rel", str(_CHART), "--namespace", "studio", *args)
    assert result.returncode == 0, result.stderr
    if os.environ.get("UPDATE_GOLDEN"):
        golden_path.write_text(result.stdout, encoding="utf-8", newline="\n")
    # Пустые строки между документами и в конце зависят от версии helm (4.x их оставляет, 3.x нет).
    golden = golden_path.read_text(encoding="utf-8")
    assert _squeeze(result.stdout) == _squeeze(golden), "обновите: UPDATE_GOLDEN=1 pytest"


def test_api_single_replica_recreate() -> None:
    api = next(d for d in _by_kind(_render(), "Deployment") if d["metadata"]["name"].endswith("-api"))
    assert api["spec"]["replicas"] == 1
    assert api["spec"]["strategy"] == {"type": "Recreate"}


def test_migration_job_is_pre_upgrade_hook() -> None:
    (job,) = _by_kind(_render(), "Job")
    assert job["metadata"]["annotations"]["helm.sh/hook"] == "pre-upgrade"
    assert job["spec"]["template"]["spec"]["containers"][0]["command"] == ["hse-doc-studio", "db", "upgrade"]
    assert _by_kind(_render("--set", "migrations.enabled=false"), "Job") == []


def test_auto_migrate_only_on_install() -> None:
    def value(*extra: str) -> str:
        api = next(d for d in _by_kind(_render(*extra), "Deployment") if d["metadata"]["name"].endswith("-api"))
        env = api["spec"]["template"]["spec"]["containers"][0]["env"]
        return next(e["value"] for e in env if e["name"] == "HSE_STUDIO__DB__AUTO_MIGRATE")

    assert value() == "true"  # helm template трактуется как установка
    assert value("--is-upgrade") == "false"
    assert value("--is-upgrade", "--set", "migrations.enabled=false") == "true"


def test_env_names_exist_in_settings_and_runner_config() -> None:
    docs = _render()
    known = _paths(Settings)
    api = next(d for d in _by_kind(docs, "Deployment") if d["metadata"]["name"].endswith("-api"))
    env = {e["name"] for e in api["spec"]["template"]["spec"]["containers"][0]["env"]}
    assert [k for k in env if k.removeprefix("HSE_STUDIO__") not in known] == []
    fields = _paths(RunnerConfig)
    for runner_docs in (docs, _render("-f", str(_K8S_VALUES))):
        runner = next(d for d in _by_kind(runner_docs, "Deployment") if d["metadata"]["name"].endswith("-runner"))
        renv = {e["name"] for e in runner["spec"]["template"]["spec"]["containers"][0]["env"]}
        assert [k for k in renv if k.removeprefix("HSE_RUNNER__") not in fields] == []


def test_secrets_not_inline_in_workloads() -> None:
    docs = _render()
    for kind in ("Deployment", "Job"):
        for doc in _by_kind(docs, kind):
            for env in doc["spec"]["template"]["spec"]["containers"][0]["env"]:
                if any(s in env["name"] for s in ("DSN", "KEY", "TOKEN", "PASSWORD", "TOKEN")):
                    assert "valueFrom" in env, env["name"]


def test_docker_socket_only_in_runner() -> None:
    docs = _render()
    for dep in _by_kind(docs, "Deployment"):
        has = "docker.sock" in str(dep["spec"]["template"]["spec"]["volumes"])
        assert has == dep["metadata"]["name"].endswith("-runner")
    assert not any(
        d["metadata"]["name"].endswith("-runner")
        for d in _by_kind(_render("--set", "runner.enabled=false"), "Deployment")
    )


def test_ingress_keeps_long_poll_alive() -> None:
    (ingress,) = _by_kind(_render(), "Ingress")
    annotations = ingress["metadata"]["annotations"]
    assert int(annotations["nginx.ingress.kubernetes.io/proxy-read-timeout"]) >= 60
    assert annotations["nginx.ingress.kubernetes.io/proxy-buffering"] == "off"


def test_existing_secret_skips_chart_secret() -> None:
    docs = _render("--set", "secrets.existingSecret=mine")
    assert _by_kind(docs, "Secret") == []
    api = next(d for d in _by_kind(docs, "Deployment") if d["metadata"]["name"].endswith("-api"))
    env = api["spec"]["template"]["spec"]["containers"][0]["env"]
    assert {e["valueFrom"]["secretKeyRef"]["name"] for e in env if "valueFrom" in e} == {"mine"}


@pytest.mark.parametrize(
    "bad",
    [
        "publicUrl=studio",
        "persistence.size=lots",
        "service.type=Bogus",
        "runner.concurrency=0",
        "runner.replicas=2",
        "unknownKey=1",
    ],
)
def test_schema_rejects_invalid_values(bad: str) -> None:
    assert _helm("template", "rel", str(_CHART), "-f", str(_VALUES), "--set", bad).returncode != 0


def test_missing_required_values_fail() -> None:
    result = _helm("template", "rel", str(_CHART), "--set", "publicUrl=https://x.org")
    assert result.returncode != 0


def test_non_root_pods_have_numeric_uid_matching_fsgroup() -> None:
    docs = _render("--set", "runner.enabled=true")
    pods = [d["spec"]["template"]["spec"] for d in docs if d["kind"] in ("Deployment", "Job")]
    assert len(pods) >= 3
    for pod in pods:
        sec = pod["securityContext"]
        assert sec["runAsNonRoot"] is True
        assert isinstance(sec["runAsUser"], int)
        assert sec["runAsUser"] > 0
        assert isinstance(sec["runAsGroup"], int)
    api = next(p for p in pods if p["containers"][0]["name"] == "api")
    assert api["securityContext"]["fsGroup"] == api["securityContext"]["runAsGroup"]


def _api(docs: list[dict[str, Any]]) -> dict[str, Any]:
    return next(d for d in _by_kind(docs, "Deployment") if d["metadata"]["name"].endswith("-api"))


def _api_env(docs: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {e["name"]: e for e in _api(docs)["spec"]["template"]["spec"]["containers"][0]["env"]}


def test_backups_absent_by_default() -> None:
    docs = _render("--set", "backups.enabled=false")
    assert not any(d["metadata"]["name"].endswith("-backups") for d in _by_kind(docs, "PersistentVolumeClaim"))
    assert [n for n in _api_env(docs) if "BACKUPS" in n] == []
    assert "backups" not in str(_api(docs)["spec"]["template"]["spec"]["volumes"])
    secret = _by_kind(docs, "Secret")[0]["stringData"]
    assert not [k for k in secret if k.startswith("backup-")]


def test_backups_enabled_renders_volume_env_and_secrets() -> None:
    docs = _render()
    (pvc,) = [d for d in _by_kind(docs, "PersistentVolumeClaim") if d["metadata"]["name"].endswith("-backups")]
    assert pvc["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"
    assert pvc["spec"]["storageClassName"] == "slow"
    spec = _api(docs)["spec"]["template"]["spec"]
    assert {"name": "backups", "mountPath": "/backups"} in spec["containers"][0]["volumeMounts"]
    assert any(v["name"] == "backups" for v in spec["volumes"])
    env = _api_env(docs)
    assert env["HSE_STUDIO__BACKUPS__LOCAL_ROOT"]["value"] == "/backups"
    assert env["HSE_STUDIO__BACKUPS__PROVISION__DESTINATION_KIND"]["value"] == "s3"
    assert env["HSE_STUDIO__BACKUPS__PROVISION__CRON"]["value"] == "30 2 * * *"
    for name in ("ACCESS_KEY", "SECRET_KEY"):
        assert "valueFrom" in env[f"HSE_STUDIO__BACKUPS__PROVISION__{name}"]
    secret = _by_kind(docs, "Secret")[0]["stringData"]
    assert secret["backup-access-key"] == "AKIABACKUP"
    assert "backup-passphrase" in secret


def test_backups_not_in_migration_job() -> None:
    (job,) = _by_kind(_render(), "Job")
    assert [e["name"] for e in job["spec"]["template"]["spec"]["containers"][0]["env"] if "BACKUPS" in e["name"]] == []


def test_backups_existing_claim_and_no_local_volume() -> None:
    docs = _render("--set", "backups.local.persistence.existingClaim=mine")
    assert not [d for d in _by_kind(docs, "PersistentVolumeClaim") if d["metadata"]["name"].endswith("-backups")]
    assert any(
        v.get("persistentVolumeClaim", {}).get("claimName") == "mine"
        for v in _api(docs)["spec"]["template"]["spec"]["volumes"]
    )
    docs = _render("--set", "backups.local.enabled=false")
    assert "HSE_STUDIO__BACKUPS__LOCAL_ROOT" not in _api_env(docs)


def test_backups_passphrase_mode_wires_secret() -> None:
    env = _api_env(_render("--set", "backups.encryptionMode=passphrase"))
    assert env["HSE_STUDIO__BACKUPS__PROVISION__PASSPHRASE"]["valueFrom"]["secretKeyRef"]["key"] == "backup-passphrase"


def test_backups_s3_requires_bucket() -> None:
    assert (
        _helm("template", "rel", str(_CHART), "-f", str(_VALUES), "--set", "backups.destination.bucket=").returncode
        != 0
    )


def _k8s_runner(*extra: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    docs = _render("-f", str(_K8S_VALUES), *extra)
    runner = next(d for d in _by_kind(docs, "Deployment") if d["metadata"]["name"].endswith("-runner"))
    return docs, runner


def test_kubernetes_runner_passes_restricted_without_host_access() -> None:
    _, runner = _k8s_runner()
    pod = runner["spec"]["template"]["spec"]

    assert "hostPath" not in str(pod["volumes"])
    assert "docker.sock" not in str(pod)
    assert "initContainers" not in pod
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}
    container = pod["containers"][0]["securityContext"]
    assert container == {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "capabilities": {"drop": ["ALL"]},
    }
    assert pod["serviceAccountName"] == "rel-hse-doc-studio-runner"
    assert runner["spec"]["strategy"] == {"type": "Recreate"}


def test_kubernetes_runner_role_is_minimal_and_namespaced() -> None:
    docs, _ = _k8s_runner()

    (role,) = _by_kind(docs, "Role")
    assert role["metadata"]["namespace"] == "hds-builds"
    granted = {(res, verb) for rule in role["rules"] for res in rule["resources"] for verb in rule["verbs"]}
    assert {res for res, _ in granted} == {"pods", "pods/log", "pods/exec"}
    assert ("pods", "update") not in granted
    assert all(rule["apiGroups"] == [""] for rule in role["rules"])
    (binding,) = _by_kind(docs, "RoleBinding")
    assert binding["subjects"] == [
        {"kind": "ServiceAccount", "name": "rel-hse-doc-studio-runner", "namespace": "default"}
    ]
    assert _by_kind(docs, "ClusterRole") == []


def test_kubernetes_runner_network_policy_denies_build_pods() -> None:
    docs, _ = _k8s_runner()

    (policy,) = _by_kind(docs, "NetworkPolicy")
    assert policy["spec"]["policyTypes"] == ["Ingress", "Egress"]
    assert "ingress" not in policy["spec"]
    assert "egress" not in policy["spec"]
    assert policy["spec"]["podSelector"]["matchLabels"]["hse-doc-studio/component"] == "build"
    off, _ = _k8s_runner("--set", "runner.kubernetes.networkPolicy.enabled=false")
    assert _by_kind(off, "NetworkPolicy") == []


def test_kubernetes_runner_build_pod_settings_reach_the_runner() -> None:
    _, runner = _k8s_runner()
    env = {e["name"]: e.get("value") for e in runner["spec"]["template"]["spec"]["containers"][0]["env"]}

    assert env["HSE_RUNNER__EXECUTOR"] == "kubernetes"
    assert env["HSE_RUNNER__K8S__NAMESPACE"] == "hds-builds"
    assert env["HSE_RUNNER__K8S__IMAGE"] == "registry.example.org/texlive:TL2024"
    assert yaml.safe_load(env["HSE_RUNNER__K8S__TOLERATIONS"])[0]["key"] == "builds"
    assert yaml.safe_load(env["HSE_RUNNER__K8S__NODE_SELECTOR"]) == {"pool": "builds"}
    assert yaml.safe_load(env["HSE_RUNNER__K8S__IMAGE_PULL_SECRETS"]) == ["registry-pull"]
    config = RunnerConfig.model_validate(
        {"api_url": "http://api", "k8s": {"tolerations": yaml.safe_load(env["HSE_RUNNER__K8S__TOLERATIONS"])}}
    )
    assert config.k8s.tolerations[0]["effect"] == "NoSchedule"


def test_kubernetes_runner_data_volume_pvc_or_empty_dir() -> None:
    docs, runner = _k8s_runner()
    assert [p["metadata"]["name"] for p in _by_kind(docs, "PersistentVolumeClaim")].count(
        "rel-hse-doc-studio-runner-data"
    ) == 1
    volumes = {v["name"]: v for v in runner["spec"]["template"]["spec"]["volumes"]}
    assert volumes["runner-data"]["persistentVolumeClaim"]["claimName"] == "rel-hse-doc-studio-runner-data"

    docs, runner = _k8s_runner("--set", "runner.persistence.enabled=false")
    assert "rel-hse-doc-studio-runner-data" not in [
        p["metadata"]["name"] for p in _by_kind(docs, "PersistentVolumeClaim")
    ]
    volumes = {v["name"]: v for v in runner["spec"]["template"]["spec"]["volumes"]}
    assert volumes["runner-data"] == {"name": "runner-data", "emptyDir": {}}


def test_kubernetes_runner_default_build_namespace_is_release_namespace() -> None:
    result = _helm(
        "template",
        "rel",
        str(_CHART),
        "--namespace",
        "studio",
        "-f",
        str(_VALUES),
        "--set",
        "runner.executor=kubernetes",
    )
    assert result.returncode == 0, result.stderr
    docs = [doc for doc in yaml.safe_load_all(result.stdout) if doc]

    (role,) = _by_kind(docs, "Role")
    assert role["metadata"]["namespace"] == "studio"
    (binding,) = _by_kind(docs, "RoleBinding")
    assert binding["subjects"][0]["namespace"] == "studio"


def test_unknown_executor_rejected_by_schema() -> None:
    result = _helm("template", "rel", str(_CHART), "-f", str(_VALUES), "--set", "runner.executor=podman")
    assert result.returncode != 0
