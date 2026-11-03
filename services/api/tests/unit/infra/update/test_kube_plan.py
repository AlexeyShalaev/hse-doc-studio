"""Чистая часть исполнителя kubernetes: образ с дайджестом, манифесты Job, статусы Job и подов, журнал в аннотациях."""

from __future__ import annotations

from typing import Any

import pytest
from hse_doc_studio.infra.update.server_updater import kube_plan
from hse_doc_studio.infra.update.server_updater.config import UpdaterConfig

from tests.fakes.kube_stack import NEW_DIGEST, NEW_IMAGE, OLD_IMAGE, REPO, FakeKube

RUN = "0a1b2c3d-0000-4000-8000-000000000000"


def test__target_image__digest_is_pinned_next_to_the_tag() -> None:
    assert kube_plan.target_image(OLD_IMAGE, "0.4.0", NEW_DIGEST) == NEW_IMAGE
    assert kube_plan.target_image(f"{OLD_IMAGE}@sha256:{'b' * 64}", "0.4.0", None) == f"{REPO}:0.4.0"


def test__scale_patch__image_only_with_a_container() -> None:
    assert kube_plan.scale_patch(0) == {"spec": {"replicas": 0}}
    assert kube_plan.scale_patch(1, container="api", image="x:1")["spec"]["template"] == {
        "spec": {"containers": [{"name": "api", "image": "x:1"}]}
    }


def test__job_manifest__keeps_env_and_security_but_drops_volumes_and_the_service_label() -> None:
    dep = FakeKube().get_deployment()

    job = kube_plan.job_manifest(
        dep, "api", run_id=RUN, step="migrate", image="img:1", command=["a"], deadline_s=60, ttl_s=100
    )

    pod = job["spec"]["template"]["spec"]
    labels = job["spec"]["template"]["metadata"]["labels"]
    assert job["metadata"]["name"] == "hds-upd-migrate-0a1b2c3d"
    assert (job["spec"]["backoffLimit"], job["spec"]["activeDeadlineSeconds"]) == (0, 60)
    assert pod["imagePullSecrets"] == [{"name": "pull"}]
    assert pod["containers"][0]["securityContext"] == {
        "allowPrivilegeEscalation": False,
        "capabilities": {"drop": ["ALL"]},
    }
    assert "volumes" not in pod
    assert "ports" not in pod["containers"][0]
    assert labels["app.kubernetes.io/component"] == "update"
    assert labels["app.kubernetes.io/instance"] == "rel", "метки экземпляра остаются для NetworkPolicy оператора"
    assert labels[kube_plan.LABEL_RUN] == RUN


def test__job_manifest__selector_labels_of_a_helmless_install_are_not_inherited() -> None:
    dep = FakeKube().get_deployment()
    dep["spec"]["selector"]["matchLabels"] = {"app": "api"}
    dep["spec"]["template"]["metadata"]["labels"] = {"app": "api", "tier": "x"}

    job = kube_plan.job_manifest(dep, "api", run_id=RUN, step="precheck", image="i", command=[], deadline_s=1, ttl_s=1)

    labels = job["spec"]["template"]["metadata"]["labels"]
    assert "app" not in labels
    assert labels["tier"] == "x"


def test__cosign_job__runs_restricted_with_the_digest_and_no_token() -> None:
    job = kube_plan.cosign_job_manifest(
        FakeKube().get_deployment(), run_id=RUN, repo=REPO, digest=NEW_DIGEST, deadline_s=1, ttl_s=1
    )

    pod = job["spec"]["template"]["spec"]
    assert pod["containers"][0]["args"][0] == "verify"
    assert pod["containers"][0]["args"][-1] == f"{REPO}@{NEW_DIGEST}"
    assert pod["securityContext"]["runAsNonRoot"] is True
    assert pod["securityContext"]["runAsUser"] == 65532
    assert pod["automountServiceAccountToken"] is False
    assert pod["containers"][0]["securityContext"]["capabilities"] == {"drop": ["ALL"]}


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ({}, "running"),
        ({"succeeded": 1}, "succeeded"),
        ({"failed": 1}, "failed"),
        ({"conditions": [{"type": "Complete", "status": "True"}]}, "succeeded"),
        ({"conditions": [{"type": "Failed", "status": "True"}]}, "failed"),
        ({"conditions": [{"type": "Failed", "status": "False"}]}, "running"),
    ],
)
def test__job_outcome(status: dict[str, Any], expected: str) -> None:
    assert kube_plan.job_outcome({"status": status}) == expected


@pytest.mark.parametrize(
    ("pod", "expected"),
    [
        ({"status": {"phase": "Running", "containerStatuses": [{"state": {"running": {}}}]}}, None),
        (
            {
                "status": {
                    "phase": "Pending",
                    "containerStatuses": [{"state": {"waiting": {"reason": "ContainerCreating"}}}],
                }
            },
            None,
        ),
        ({"status": {"phase": "Failed", "reason": "Evicted"}}, None),
        ({"status": {"phase": "Failed", "message": "boom"}}, "boom"),
        (
            {
                "status": {
                    "containerStatuses": [{"state": {"waiting": {"reason": "ErrImagePull", "message": "denied"}}}]
                }
            },
            "ErrImagePull: denied",
        ),
        (
            {
                "status": {
                    "containerStatuses": [
                        {
                            "state": {"running": {}},
                            "restartCount": 2,
                            "lastState": {"terminated": {"reason": "OOMKilled", "exitCode": 137}},
                        }
                    ]
                }
            },
            "the container restarted (OOMKilled, exit code 137)",
        ),
    ],
)
def test__pod_problem(pod: dict[str, Any], expected: str | None) -> None:
    assert kube_plan.pod_problem(pod) == expected


def test__rollout_ready__needs_the_latest_generation_and_all_replicas() -> None:
    kube = FakeKube()
    dep = kube.get_deployment()
    assert kube_plan.rollout_ready(dep, 1)
    dep["status"]["observedGeneration"] = 0
    assert not kube_plan.rollout_ready(dep, 1)
    kube.replicas = 0
    assert not kube_plan.rollout_ready(kube.get_deployment(), 1)


def test__journal_patch__roundtrips_through_the_annotations_and_null_removes() -> None:
    patch = kube_plan.journal_patch({"id": "r", "stopped": True}, None)
    ann = patch["metadata"]["annotations"]
    assert ann[kube_plan.ANNOTATION_LAST_OK] is None
    dep = {"metadata": {"annotations": {kube_plan.ANNOTATION_RUN: ann[kube_plan.ANNOTATION_RUN]}}}
    assert kube_plan.read_annotation(dep, kube_plan.ANNOTATION_RUN) == {"id": "r", "stopped": True}
    assert (
        kube_plan.read_annotation(
            {"metadata": {"annotations": {kube_plan.ANNOTATION_RUN: "{bad"}}}, kube_plan.ANNOTATION_RUN
        )
        is None
    )


def test__pod_selector__sorted_labels() -> None:
    assert kube_plan.pod_selector(FakeKube().get_deployment()) == (
        "app.kubernetes.io/component=api,app.kubernetes.io/instance=rel,app.kubernetes.io/name=hse-doc-studio"
    )


def test__config_from_env__kubernetes_needs_a_deployment_name() -> None:
    env = {"HSE_UPDATER__TOKEN": "t", "HSE_UPDATER__EXECUTOR": "kubernetes"}
    with pytest.raises(ValueError, match="DEPLOYMENT"):
        UpdaterConfig.from_env(env)

    cfg = UpdaterConfig.from_env(
        {**env, "HSE_UPDATER__KUBE__DEPLOYMENT": "rel-api", "HSE_UPDATER__KUBE__CONTAINER": "web"}
    )

    assert cfg.kube is not None
    assert (cfg.kube.deployment, cfg.kube.container, cfg.kube.namespace) == ("rel-api", "web", "")
    assert UpdaterConfig.from_env({"HSE_UPDATER__TOKEN": "t"}).kube is None
