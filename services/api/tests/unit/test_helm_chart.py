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

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm не установлен")


def _helm(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["helm", *args], capture_output=True, text=True, check=False)  # noqa: S603, S607


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


def test_lint() -> None:
    result = _helm("lint", str(_CHART), "-f", str(_VALUES), "--strict")
    assert result.returncode == 0, result.stdout + result.stderr


def test_template_matches_golden() -> None:
    result = _helm("template", "rel", str(_CHART), "-f", str(_VALUES))
    assert result.returncode == 0, result.stderr
    if os.environ.get("UPDATE_GOLDEN"):
        _GOLDEN.write_text(result.stdout, encoding="utf-8")
    assert result.stdout == _GOLDEN.read_text(encoding="utf-8"), "обновите: UPDATE_GOLDEN=1 pytest"


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
    runner = next(d for d in _by_kind(docs, "Deployment") if d["metadata"]["name"].endswith("-runner"))
    renv = {e["name"] for e in runner["spec"]["template"]["spec"]["containers"][0]["env"]}
    fields = {name.upper() for name in RunnerConfig.model_fields}
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
    ["publicUrl=studio", "persistence.size=lots", "service.type=Bogus", "runner.concurrency=0", "unknownKey=1"],
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
