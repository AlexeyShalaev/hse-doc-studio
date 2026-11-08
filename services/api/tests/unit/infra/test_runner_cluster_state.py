"""Чтение живого состояния кластера для экрана изоляции раннеров: права, разбор объектов, кэш, без секретов."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from hse_doc_studio.core.runner_isolation import ClusterTargets, LiveStatus, LookupStatus
from hse_doc_studio.infra.compile.k8s.api import KubeApiError
from hse_doc_studio.infra.runner_install.cluster_state import KubeClusterStateReader

_TARGETS = ClusterTargets(release_namespace="studio", build_namespace="builds")
_DENY_BUILDS = {
    "metadata": {"name": "rel-runner-builds-deny-all"},
    "spec": {
        "podSelector": {
            "matchLabels": {
                "app.kubernetes.io/managed-by": "hse-doc-studio-runner",
                "hse-doc-studio/component": "build",
            }
        },
        "policyTypes": ["Ingress", "Egress"],
    },
}
_RUNNER_EGRESS = {
    "metadata": {"name": "rel-runner-ui-egress"},
    "spec": {
        "podSelector": {"matchLabels": {"hse-doc-studio/runner-install": "true"}},
        "policyTypes": ["Egress"],
        "egress": [{"ports": [{"port": 53}]}],
    },
}


class _Client:
    def __init__(self, answers: Mapping[str, Any]) -> None:
        self.answers = answers
        self.paths: list[str] = []
        self.closed = 0

    async def request_json(self, method: str, path: str, *, params: Mapping[str, str] | None = None) -> Any:
        assert method == "GET"
        self.paths.append(path)
        answer = self.answers.get(path, KubeApiError("not found", status=404))
        if isinstance(answer, KubeApiError):
            raise answer
        return answer

    async def aclose(self) -> None:
        self.closed += 1


def _reader(client: _Client, *, read_live: bool = True, install: bool = True) -> KubeClusterStateReader:
    return KubeClusterStateReader(
        read_live=read_live,
        install_enabled=install,
        namespace="studio",
        client_factory=lambda: client,  # type: ignore[arg-type,return-value]
        in_cluster=lambda: True,
    )


def _full() -> dict[str, Any]:
    return {
        "/apis/networking.k8s.io/v1/namespaces/builds/networkpolicies": {"items": [_DENY_BUILDS]},
        "/apis/networking.k8s.io/v1/namespaces/studio/networkpolicies": {"items": [_RUNNER_EGRESS]},
        "/api/v1/namespaces/builds/resourcequotas": {
            "items": [
                {
                    "metadata": {"name": "rel-builds"},
                    "spec": {"hard": {"pods": "20", "limits.memory": "80Gi"}},
                    "status": {"used": {"pods": "2", "limits.memory": "8Gi"}},
                }
            ]
        },
        "/api/v1/namespaces/builds/limitranges": {"items": []},
        # Поды сборки раннеров из админки по умолчанию в namespace релиза: квоты там нет.
        "/api/v1/namespaces/studio/resourcequotas": {"items": []},
        "/api/v1/namespaces/studio/limitranges": {"items": []},
        "/api/v1/namespaces/studio": {"metadata": {"labels": {"pod-security.kubernetes.io/enforce": "restricted"}}},
        "/api/v1/namespaces/builds": {"metadata": {"labels": {"pod-security.kubernetes.io/warn": "restricted"}}},
    }


async def test__off_by_default__nothing_is_read() -> None:
    client = _Client(_full())
    state = await _reader(client, read_live=False).cluster_state(_TARGETS)

    assert state.status is LiveStatus.off
    assert client.paths == []


async def test__everything_readable__policies_quota_and_labels() -> None:
    client = _Client(_full())
    state = await _reader(client).cluster_state(_TARGETS)

    assert state.status is LiveStatus.ok
    assert state.build_deny_all is True
    assert state.ui_build_deny_all is False
    assert state.runner_egress is True
    assert state.quota is not None
    assert state.quota.used == {"pods": "2", "limits.memory": "8Gi"}
    assert state.limit_range_checked is True
    assert state.limit_range is None
    assert state.namespaces is not None
    assert [(n.namespace, n.enforce, n.warn) for n in state.namespaces] == [
        ("studio", "restricted", None),
        ("builds", None, "restricted"),
    ]
    assert client.closed == 1


async def test__ui_builds_in_their_own_namespace__policies_quota_and_labels_read_there() -> None:
    answers = _full()
    answers["/apis/networking.k8s.io/v1/namespaces/ui-builds/networkpolicies"] = {
        "items": [{**_DENY_BUILDS, "metadata": {"name": "rel-runner-ui-builds-deny-all"}}]
    }
    answers["/api/v1/namespaces/ui-builds/resourcequotas"] = {
        "items": [
            {"metadata": {"name": "rel-builds"}, "spec": {"hard": {"pods": "20"}}, "status": {"used": {"pods": "1"}}}
        ]
    }
    answers["/api/v1/namespaces/ui-builds/limitranges"] = {
        "items": [
            {"metadata": {"name": "rel-builds"}, "spec": {"limits": [{"type": "Container", "max": {"cpu": "8"}}]}}
        ]
    }
    answers["/api/v1/namespaces/ui-builds"] = {
        "metadata": {"labels": {"pod-security.kubernetes.io/enforce": "restricted"}}
    }
    client = _Client(answers)
    targets = ClusterTargets(release_namespace="studio", build_namespace="builds", ui_build_namespace="ui-builds")

    state = await _reader(client).cluster_state(targets)

    assert state.status is LiveStatus.ok
    assert state.ui_build_deny_all is True
    assert state.ui_quota is not None
    assert state.ui_quota.used == {"pods": "1"}
    assert state.ui_limit_range is not None
    assert state.ui_limit_range.max == {"cpu": "8"}
    assert state.quota is not None
    assert state.quota.hard["limits.memory"] == "80Gi"
    assert state.namespaces is not None
    assert [n.namespace for n in state.namespaces] == ["studio", "builds", "ui-builds"]
    assert len(client.paths) == len(set(client.paths))


async def test__shared_build_namespace__read_once() -> None:
    client = _Client(_full())
    targets = ClusterTargets(release_namespace="studio", build_namespace="builds", ui_build_namespace="builds")

    state = await _reader(client).cluster_state(targets)

    assert state.status is LiveStatus.ok
    assert state.ui_build_deny_all is True
    assert state.ui_quota == state.quota
    assert len(client.paths) == len(set(client.paths))
    assert [n.namespace for n in state.namespaces or ()] == ["studio", "builds"]


async def test__policy_with_rules_is_not_deny_all() -> None:
    answers = _full()
    leaky = {**_DENY_BUILDS, "spec": {**_DENY_BUILDS["spec"], "egress": [{}]}}
    answers["/apis/networking.k8s.io/v1/namespaces/builds/networkpolicies"] = {"items": [leaky]}

    state = await _reader(_Client(answers)).cluster_state(_TARGETS)

    assert state.build_deny_all is False


async def test__namespaces_forbidden__partial_and_not_checked() -> None:
    answers = _full()
    answers["/api/v1/namespaces/studio"] = KubeApiError("forbidden", status=403)
    answers["/api/v1/namespaces/builds"] = KubeApiError("forbidden", status=403)

    state = await _reader(_Client(answers)).cluster_state(_TARGETS)

    assert state.status is LiveStatus.partial
    assert state.namespaces is None
    assert state.build_deny_all is True


async def test__nothing_allowed__forbidden_and_nothing_claimed() -> None:
    forbidden = KubeApiError("forbidden", status=403)
    answers = dict.fromkeys(_full(), forbidden)

    state = await _reader(_Client(answers)).cluster_state(_TARGETS)

    assert state.status is LiveStatus.forbidden
    assert state.build_deny_all is None
    assert state.quota_checked is False


async def test__not_in_cluster__unavailable() -> None:
    reader = KubeClusterStateReader(read_live=True, install_enabled=True, in_cluster=lambda: False)

    assert (await reader.cluster_state(_TARGETS)).status is LiveStatus.unavailable
    assert (await reader.runner_deployments()).status is LookupStatus.unavailable


async def test__state_is_cached_for_a_while() -> None:
    client = _Client(_full())
    reader = _reader(client)

    await reader.cluster_state(_TARGETS)
    reads = len(client.paths)
    await reader.cluster_state(_TARGETS)

    assert len(client.paths) == reads


def _deployment(env: list[dict[str, Any]], resources: dict[str, Any] | None) -> dict[str, Any]:
    container: dict[str, Any] = {
        "name": "runner",
        "image": "ghcr.io/x/hds:0.14.0",
        "env": env,
        "securityContext": {
            "allowPrivilegeEscalation": False,
            "readOnlyRootFilesystem": True,
            "capabilities": {"drop": ["ALL"]},
        },
    }
    if resources is not None:
        container["resources"] = resources
    return {
        "metadata": {"name": "builds-a", "namespace": "studio"},
        "spec": {
            "template": {
                "spec": {
                    "serviceAccountName": "rel-runner-ui",
                    "automountServiceAccountToken": True,
                    "securityContext": {
                        "runAsNonRoot": True,
                        "runAsUser": 1000,
                        "seccompProfile": {"type": "RuntimeDefault"},
                    },
                    "containers": [container],
                }
            }
        },
        "status": {"readyReplicas": 1},
    }


async def test__runner_deployments__parsed_without_env_or_secrets() -> None:
    env = [
        {"name": "HSE_RUNNER__TOKEN", "valueFrom": {"secretKeyRef": {"name": "builds-a-token", "key": "token"}}},
        {"name": "HSE_RUNNER__API_URL", "value": "http://studio:8000"},
        {"name": "HSE_RUNNER__K8S__MEMORY_LIMIT", "value": "4Gi"},
        {"name": "HSE_RUNNER__K8S__CPU_LIMIT", "value": "2"},
    ]
    resources = {"requests": {"cpu": "100m", "memory": "256Mi"}, "limits": {"cpu": "1", "memory": "2Gi"}}
    client = _Client({"/apis/apps/v1/namespaces/studio/deployments": {"items": [_deployment(env, resources)]}})

    listing = await _reader(client, read_live=False).runner_deployments()

    assert listing.status is LookupStatus.ok
    (item,) = listing.items
    assert item.ready is True
    assert item.service_account == "rel-runner-ui"
    assert item.resources is not None
    assert item.resources.memory_limit == "2Gi"
    assert item.build_resources is not None
    assert (item.build_resources.cpu_limit, item.build_resources.memory_limit) == ("2", "4Gi")
    assert item.security is not None
    assert item.security.read_only_root is True
    assert item.security.seccomp is True
    assert item.security.run_as_user == 1000
    assert "builds-a-token" not in repr(item)
    assert "studio:8000" not in repr(item)


async def test__runner_deployments__old_install_has_no_limits_and_forbidden_is_reported() -> None:
    client = _Client({"/apis/apps/v1/namespaces/studio/deployments": {"items": [_deployment([], None)]}})
    (item,) = (await _reader(client).runner_deployments()).items

    assert item.resources is None
    assert item.build_resources is None
    forbidden = _Client({"/apis/apps/v1/namespaces/studio/deployments": KubeApiError("no", status=403)})
    assert (await _reader(forbidden).runner_deployments()).status is LookupStatus.forbidden
    assert (await _reader(forbidden, install=False).runner_deployments()).status is LookupStatus.not_applicable
