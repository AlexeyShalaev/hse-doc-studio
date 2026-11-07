"""Правила экрана изоляции раннеров: версии, «переустановить», откуда раннер, поиск его Deployment."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from hse_doc_studio.core.jobs.deployment import ResourceFigures, ResourceSource, RunnerPlatform
from hse_doc_studio.core.jobs.runners import Runner
from hse_doc_studio.core.runner_isolation import (
    LiveDeployment,
    ReinstallReason,
    RunnerOrigin,
    is_outdated,
    limits_supported,
    match_deployment,
    reinstall_reasons,
    runner_origin,
)

from tests.factories.runner_isolation import make_declared, make_report


def _runner(version: str = "0.14.0", name: str = "r1", **changes: object) -> Runner:
    base = Runner(
        id="r",
        name=name,
        token_hash="h",
        tags=frozenset(),
        concurrency=1,
        resource_class="standard",
        version=version,
        created_at=datetime.now(UTC),
    )
    return replace(base, **changes)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("version", "expected"),
    [("0.13.9", False), ("0.14.0", True), ("1.0.0", True), ("dev", None), ("0.14.0rc1", True)],
)
def test__limits_supported__by_version(version: str, expected: bool | None) -> None:
    assert limits_supported(version) is expected


def test__is_outdated__compares_numbers_and_ignores_unparsed() -> None:
    assert is_outdated("0.9.0", "0.14.0") is True
    assert is_outdated("0.14.0", "0.14.0") is False
    assert is_outdated("dev", "0.14.0") is False


def test__reinstall__old_version_without_report() -> None:
    assert reinstall_reasons(_runner("0.13.2"), None) == (ReinstallReason.before_limits,)


def test__reinstall__live_deployment_without_limits() -> None:
    live = LiveDeployment(name="r1", namespace="studio")
    assert reinstall_reasons(_runner(), live) == (ReinstallReason.no_pod_limits,)


def test__reinstall__reported_pod_without_limits_but_cgroup_on_a_host_is_fine() -> None:
    unlimited = ResourceFigures(source=ResourceSource.cgroup)
    in_pod = _runner(deployment=make_report(), deployment_at=None)
    in_pod = replace(in_pod, deployment=replace(in_pod.deployment, resources=unlimited))  # type: ignore[type-var]
    on_host = replace(in_pod, deployment=replace(in_pod.deployment, platform=RunnerPlatform.host))  # type: ignore[type-var]

    assert reinstall_reasons(in_pod, None) == (ReinstallReason.no_pod_limits,)
    assert reinstall_reasons(on_host, None) == ()
    assert reinstall_reasons(_runner(deployment=make_report()), None) == ()


def test__match_deployment__by_pod_name_then_by_runner_name() -> None:
    items = [LiveDeployment(name="builds-a", namespace="s"), LiveDeployment(name="r1", namespace="s")]
    reported = _runner(name="renamed", deployment=make_report(pod_name="builds-a-7d9f8b6c5-x2k4q"))

    assert match_deployment(reported, items) == items[0]
    assert match_deployment(_runner(name="r1"), items) == items[1]
    assert match_deployment(_runner(name="other"), items) is None
    # Префикс другого Deployment не путается: у пода ровно два хвоста после имени.
    assert match_deployment(_runner(name="x", deployment=make_report(pod_name="builds-a-b-7d9f-x2k4")), items) is None


def test__origin__chart_ui_other_and_unknown() -> None:
    declared = make_declared()
    chart = _runner(deployment=make_report(service_account="rel-runner"))
    by_pod = _runner(deployment=make_report(service_account=None, pod_name="rel-runner-7d9f8b6c5-x2k4q"))
    ui = _runner(deployment=make_report(service_account="rel-ui"))
    other = _runner(deployment=make_report(service_account="default", pod_name="custom-1"))

    assert runner_origin(chart, None, declared, "rel-ui") is RunnerOrigin.chart
    assert runner_origin(by_pod, None, declared, "rel-ui") is RunnerOrigin.chart
    assert runner_origin(ui, None, declared, "rel-ui") is RunnerOrigin.ui
    assert runner_origin(other, None, declared, "rel-ui") is RunnerOrigin.other
    assert runner_origin(_runner(), None, declared, "rel-ui") is None
    assert runner_origin(_runner(), LiveDeployment(name="r1", namespace="s"), None, "") is RunnerOrigin.ui
