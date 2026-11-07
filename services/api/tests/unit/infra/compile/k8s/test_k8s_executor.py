"""Исполнитель kubernetes на фейковом API: под restricted, вход и выход tar-ом, лог, сбои, отмена и уборка."""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from typing import Any, cast

import pytest
from hse_doc_studio.core.compile.errors import (
    BuildBackendUnavailableError,
    BuildOutOfMemoryError,
    BuildStorageExceededError,
    ImageMissingError,
)
from hse_doc_studio.infra.compile.k8s.api import KubeApiError, PodState
from hse_doc_studio.infra.compile.k8s.config import KubernetesExecutorConfig
from hse_doc_studio.infra.compile.k8s.executor import KubernetesTexExecutor, LogCursor
from hse_doc_studio.infra.compile.latexmk import SENTINEL_DONE, SENTINEL_FAILED, SENTINEL_PAGES, SENTINEL_WORDS

from tests.unit.infra.compile.k8s.fake_kube import FakeKubeApi, FakePod, failing_build

_COMPILE_ID = uuid.UUID("12345678-1234-5678-1234-567812345678")


def _config(**extra: Any) -> KubernetesExecutorConfig:
    return KubernetesExecutorConfig(namespace="builds", **extra)


def _executor(api: FakeKubeApi, *, idle: float = 5.0, **extra: Any) -> KubernetesTexExecutor:
    return KubernetesTexExecutor(
        api,
        _config(**extra),
        image="tex:TL2024",
        instance="runner-uid",
        idle_timeout_s=idle,
        poll_s=0.001,
        reconnect_s=0.001,
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "tz" / ".build" / "other").mkdir(parents=True)
    (root / "tz" / ".build" / "other" / "stale.aux").write_text("x", encoding="utf-8")
    (root / "tz" / "main.tex").write_text("\\documentclass{article}", encoding="utf-8")
    (root / "common").mkdir()
    (root / "common" / "meta.tex").write_text("meta", encoding="utf-8")
    return root


async def _run(executor: KubernetesTexExecutor, project: Path) -> list[str]:
    lines = await executor.run(
        project_folder=project,
        source_file="tz/main.tex",
        engine="xelatex",
        max_iterations=5,
        doc_id="tz",
        compile_id=_COMPILE_ID,
    )
    return [line async for line in lines]


async def test__run__success__pdf_next_to_source_pages_words_and_pod_deleted(tmp_path: Path, project: Path) -> None:
    api = FakeKubeApi(tmp_path / "cluster")

    lines = await _run(_executor(api), project)

    assert lines[-1] == SENTINEL_DONE
    assert f"{SENTINEL_PAGES}3" in lines
    assert f"{SENTINEL_WORDS}6:25" in lines
    assert "latexmk ok" in lines
    assert not any(api.only_pod().nonce in line for line in lines)
    assert (project / "tz" / "main.pdf").read_bytes() == b"%PDF-1.5 built"
    assert api.deleted == [api.only_pod().name]


async def test__run__upload__sends_sources_and_own_build_dir_only(tmp_path: Path, project: Path) -> None:
    api = FakeKubeApi(tmp_path / "cluster")

    await _run(_executor(api), project)

    work = api.only_pod().work
    assert (work / "tz" / "main.tex").is_file()
    assert (work / "common" / "meta.tex").is_file()
    assert not (work / "tz" / ".build" / "other").exists()
    assert api.execs[0][:2] == ["sh", "-c"]
    assert api.execs[1] == ["tar", "-c", "-f", "-", "-C", "/work", "tz/.build/tz"]


async def test__run__pod_manifest__restricted_without_network_identity_or_host_paths(
    tmp_path: Path, project: Path
) -> None:
    api = FakeKubeApi(tmp_path / "cluster")
    executor = _executor(
        api,
        node_selector={"pool": "builds"},
        tolerations=[{"key": "builds", "operator": "Exists", "effect": "NoSchedule"}],
        runtime_class_name="gvisor",
        owner_pod_name="runner-0",
        owner_pod_uid="uid-1",
        cpu_limit="3",
    )

    await _run(executor, project)

    manifest = api.only_pod().manifest
    spec = cast(dict[str, Any], manifest["spec"])
    container = spec["containers"][0]
    assert spec["automountServiceAccountToken"] is False
    assert spec["restartPolicy"] == "Never"
    assert spec["activeDeadlineSeconds"] == 1800
    assert spec["securityContext"]["runAsNonRoot"] is True
    assert spec["securityContext"]["seccompProfile"] == {"type": "RuntimeDefault"}
    assert container["securityContext"] == {
        "allowPrivilegeEscalation": False,
        "readOnlyRootFilesystem": True,
        "runAsNonRoot": True,
        "capabilities": {"drop": ["ALL"]},
        "seccompProfile": {"type": "RuntimeDefault"},
    }
    assert container["resources"]["limits"]["cpu"] == "3"
    assert container["image"] == "tex:TL2024"
    assert all("hostPath" not in volume for volume in spec["volumes"])
    assert spec["nodeSelector"] == {"pool": "builds"}
    assert spec["tolerations"][0]["key"] == "builds"
    assert spec["runtimeClassName"] == "gvisor"
    assert "priorityClassName" not in spec
    meta = cast(dict[str, Any], manifest["metadata"])
    assert meta["ownerReferences"] == [{"apiVersion": "v1", "kind": "Pod", "name": "runner-0", "uid": "uid-1"}]
    assert meta["labels"]["hse-doc-studio/runner"] == "runner-uid"
    assert meta["labels"]["hse-doc-studio/job"] == str(_COMPILE_ID)
    assert "$max_repeat=5;" in container["command"][2]


async def test__run__tex_cache_claim__mounted_with_font_cache_env(tmp_path: Path, project: Path) -> None:
    api = FakeKubeApi(tmp_path / "cluster")

    await _run(_executor(api, tex_cache_claim="tex-cache"), project)

    spec = cast(dict[str, Any], api.only_pod().manifest["spec"])
    assert {"name": "tex-cache", "persistentVolumeClaim": {"claimName": "tex-cache"}} in spec["volumes"]
    env = {e["name"]: e["value"] for e in spec["containers"][0]["env"]}
    assert env["TEXMFCACHE"].startswith("/cache/")
    assert env["TEXMFVAR"].startswith("/tmp/")


async def test__run__fonts_claim__mounted_read_only_where_fontconfig_scans(tmp_path: Path, project: Path) -> None:
    api = FakeKubeApi(tmp_path / "cluster")

    await _run(_executor(api, fonts_claim="studio-fonts"), project)

    spec = cast(dict[str, Any], api.only_pod().manifest["spec"])
    assert {"name": "fonts", "persistentVolumeClaim": {"claimName": "studio-fonts", "readOnly": True}} in spec[
        "volumes"
    ]
    assert {"name": "fonts", "mountPath": "/usr/local/share/fonts/hse", "readOnly": True} in spec["containers"][0][
        "volumeMounts"
    ]


async def test__run__no_fonts_claim__no_fonts_volume(tmp_path: Path, project: Path) -> None:
    api = FakeKubeApi(tmp_path / "cluster")

    await _run(_executor(api), project)

    spec = cast(dict[str, Any], api.only_pod().manifest["spec"])
    assert all(v["name"] != "fonts" for v in spec["volumes"])


async def test__run__latexmk_fails__failed_log_downloaded_and_latexmk_state_reset(
    tmp_path: Path, project: Path
) -> None:
    api = FakeKubeApi(tmp_path / "cluster", build=failing_build)

    lines = await _run(_executor(api), project)

    assert lines[-1] == SENTINEL_FAILED
    assert any("exited with code 12" in line for line in lines)
    build = project / "tz" / ".build" / "tz"
    assert (build / "main.log").read_text(encoding="utf-8") == "! boom\n"
    assert not (build / "main.fdb_latexmk").exists()
    assert not (project / "tz" / "main.pdf").exists()


async def test__run__image_pull_backoff__image_missing_and_pod_deleted(tmp_path: Path, project: Path) -> None:
    api = FakeKubeApi(
        tmp_path / "cluster",
        states=[
            PodState(phase="Pending", waiting_reason="ErrImagePull"),
            PodState(phase="Pending", waiting_reason="ImagePullBackOff"),
        ],
    )

    with pytest.raises(ImageMissingError) as caught:
        await _run(_executor(api), project)

    assert caught.value.image == "tex:TL2024"
    assert api.deleted == [api.only_pod().name]


async def test__run__create_forbidden__build_backend_unavailable(tmp_path: Path, project: Path) -> None:
    api = FakeKubeApi(tmp_path / "cluster", create_error=KubeApiError("pods is forbidden", status=403))

    with pytest.raises(BuildBackendUnavailableError, match="forbidden"):
        await _run(_executor(api), project)

    assert api.deleted == []


async def test__run__unschedulable_past_start_timeout__build_backend_unavailable(tmp_path: Path, project: Path) -> None:
    api = FakeKubeApi(tmp_path / "cluster", states=[PodState(phase="Pending", unschedulable="0/1 nodes available")])

    with pytest.raises(BuildBackendUnavailableError, match="0/1 nodes available"):
        await _run(_executor(api, pod_start_timeout_s=0.05), project)

    assert api.deleted == [api.only_pod().name]


async def test__run__silent_build__idle_timeout_kills_pod(tmp_path: Path, project: Path) -> None:
    async def silent(pod: FakePod) -> list[str]:
        return []

    api = FakeKubeApi(tmp_path / "cluster", build=silent)

    lines = await _run(_executor(api, idle=0.1), project)

    assert lines[-1] == SENTINEL_FAILED
    assert any("no output for" in line for line in lines)
    assert api.deleted == [api.only_pod().name]


async def test__run__pod_dies_before_end__reports_deadline(tmp_path: Path, project: Path) -> None:
    async def cut(pod: FakePod) -> list[str]:
        return ["started"]

    api = FakeKubeApi(
        tmp_path / "cluster",
        build=cut,
        hang_after_log=False,
        after_log_state=PodState(phase="Failed", reason="DeadlineExceeded"),
    )

    lines = await _run(_executor(api), project)

    assert lines[-1] == SENTINEL_FAILED
    assert any("activeDeadlineSeconds=1800 exceeded" in line for line in lines)


async def test__run__oom_killed__out_of_memory_error_not_a_generic_failure(tmp_path: Path, project: Path) -> None:
    async def cut(pod: FakePod) -> list[str]:
        return ["This is XeTeX"]

    api = FakeKubeApi(
        tmp_path / "cluster",
        build=cut,
        hang_after_log=False,
        after_log_state=PodState(phase="Failed", terminated_reason="OOMKilled", terminated_exit_code=137),
    )

    with pytest.raises(BuildOutOfMemoryError, match="OOMKilled.*memory limit 4Gi"):
        await _run(_executor(api), project)

    assert api.deleted == [api.only_pod().name]


async def test__run__latexmk_sigkill__out_of_memory_error(tmp_path: Path, project: Path) -> None:
    async def killed(pod: FakePod) -> list[str]:
        return ["Running xelatex", pod.mark("exit", "137"), pod.mark("end")]

    api = FakeKubeApi(tmp_path / "cluster", build=killed)

    with pytest.raises(BuildOutOfMemoryError, match="exit code 137"):
        await _run(_executor(api), project)

    assert api.deleted == [api.only_pod().name]


async def test__run__evicted_for_ephemeral_storage__storage_error(tmp_path: Path, project: Path) -> None:
    async def cut(pod: FakePod) -> list[str]:
        return ["started"]

    api = FakeKubeApi(
        tmp_path / "cluster",
        build=cut,
        hang_after_log=False,
        after_log_state=PodState(
            phase="Failed",
            reason="Evicted",
            message="Pod ephemeral local storage usage exceeds the total limit of containers 4Gi.",
        ),
    )

    with pytest.raises(BuildStorageExceededError, match="ephemeral"):
        await _run(_executor(api), project)


async def test__run__pod_manifest__requests_and_limits_for_cpu_memory_and_ephemeral_storage(
    tmp_path: Path, project: Path
) -> None:
    api = FakeKubeApi(tmp_path / "cluster")

    await _run(_executor(api), project)

    container = cast(dict[str, Any], api.only_pod().manifest["spec"])["containers"][0]
    assert container["resources"] == {
        "requests": {"cpu": "500m", "memory": "1Gi", "ephemeral-storage": "1Gi"},
        "limits": {"cpu": "2", "memory": "4Gi", "ephemeral-storage": "4Gi"},
    }


async def test__run__log_stream_reset__reconnects_without_duplicate_lines(tmp_path: Path, project: Path) -> None:
    async def chatty(pod: FakePod) -> list[str]:
        return ["one", "two", "three", "four", pod.mark("exit", "0"), pod.mark("end")]

    api = FakeKubeApi(tmp_path / "cluster", build=chatty, drop_log_after=3)

    lines = await _run(_executor(api), project)

    assert [line for line in lines if line in ("one", "two", "three", "four")] == ["one", "two", "three", "four"]
    assert api.log_requests[0] is None
    assert api.log_requests[1] is not None


async def test__run__output_over_limit__failed(tmp_path: Path, project: Path) -> None:
    api = FakeKubeApi(tmp_path / "cluster")

    lines = await _run(_executor(api, max_output_bytes=16), project)

    assert lines[-1] == SENTINEL_FAILED
    assert any("exceeds 16 bytes" in line for line in lines)


async def test__run__cancelled__pod_deleted(tmp_path: Path, project: Path) -> None:
    async def slow(pod: FakePod) -> list[str]:
        await asyncio.sleep(30)
        return []

    api = FakeKubeApi(tmp_path / "cluster", build=slow)
    task = asyncio.create_task(_run(_executor(api), project))
    for _ in range(400):
        if api.pods and api.only_pod().ready.is_set():
            break
        await asyncio.sleep(0.005)

    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert api.deleted == [api.only_pod().name]


async def test__run__unknown_engine__failed_without_pod(tmp_path: Path, project: Path) -> None:
    api = FakeKubeApi(tmp_path / "cluster")
    lines = await _executor(api).run(project, "tz/main.tex", "context", 5, "tz", _COMPILE_ID)

    assert [line async for line in lines][-1] == SENTINEL_FAILED
    assert api.pods == {}


async def test__sweep__deletes_only_own_build_pods(tmp_path: Path) -> None:
    api = FakeKubeApi(tmp_path / "cluster")
    own = {"hse-doc-studio/component": "build", "hse-doc-studio/runner": "runner-uid"}
    api.extra = {
        "hds-build-a": own,
        "hds-build-b": {**own, "hse-doc-studio/runner": "other"},
        "studio-api": {"app": "api"},
    }

    swept = await _executor(api).sweep()

    assert swept == 1
    assert api.deleted == ["hds-build-a"]


def test__log_cursor__replay_after_reconnect__skips_seen_lines_with_same_second() -> None:
    cursor = LogCursor()
    first = ["2026-11-03T10:00:00Z", "2026-11-03T10:00:00.5Z", "2026-11-03T10:00:00.5Z"]
    assert [cursor.accept(s) for s in first] == [True, True, True]
    assert cursor.since == "2026-11-03T10:00:00Z"

    cursor.reconnect()

    replay = [*first, "2026-11-03T10:00:00.5Z", "2026-11-03T10:00:01Z"]
    assert [cursor.accept(s) for s in replay] == [False, False, False, True, True]


def test__log_cursor__nanosecond_precision__compared_numerically() -> None:
    cursor = LogCursor()
    cursor.accept("2026-11-03T10:00:00.123456789Z")
    cursor.reconnect()

    assert cursor.accept("2026-11-03T10:00:00.12Z") is False
    assert cursor.accept("2026-11-03T10:00:00.9Z") is True
