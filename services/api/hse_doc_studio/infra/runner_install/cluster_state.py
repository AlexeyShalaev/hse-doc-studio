"""Чтение живого состояния кластера для экрана изоляции раннеров, только в пределах выданных Студии прав.

- Deployment раннеров из админки: право `list` на deployments уже есть у Студии с `runner.installFromUi.enabled`.
- NetworkPolicy, ResourceQuota, LimitRange (get, list) и `get` на свои namespace (метки Pod Security): только с опцией
  чарта `runner.isolationInfo.readCluster`, по умолчанию выключенной.

Из Deployment берутся образ, ServiceAccount, requests и limits, securityContext и значения лимитов подов сборки
(`HSE_RUNNER__K8S__*`); остальное окружение, ссылки на Secret и тома в ответ не попадают.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from hse_doc_studio.core.jobs.deployment import ResourceFigures, ResourceSource, SecurityFacts
from hse_doc_studio.core.runner_isolation import (
    ClusterTargets,
    DeploymentListing,
    LiveClusterState,
    LiveDeployment,
    LiveLimitRange,
    LiveQuota,
    LiveStatus,
    LookupStatus,
    NamespaceSecurity,
)
from hse_doc_studio.infra.compile.k8s.api import KubeApiError
from hse_doc_studio.infra.compile.k8s.client import KubernetesApiClient, TokenSource
from hse_doc_studio.infra.compile.k8s.config import SA_DIR, KubernetesExecutorConfig
from hse_doc_studio.infra.compile.k8s.pod import COMPONENT_BUILD, LABEL_COMPONENT, LABEL_MANAGED_BY, MANAGED_BY
from hse_doc_studio.infra.runner_install.kube_host import INSTALL_LABEL

_FORBIDDEN = 403
_CACHE_TTL_S = 30.0
_PSA_PREFIX = "pod-security.kubernetes.io/"
_BUILD_LABELS = {LABEL_MANAGED_BY: MANAGED_BY, LABEL_COMPONENT: COMPONENT_BUILD}
_BUILD_ENV = {
    "HSE_RUNNER__K8S__CPU_REQUEST": "cpu_request",
    "HSE_RUNNER__K8S__CPU_LIMIT": "cpu_limit",
    "HSE_RUNNER__K8S__MEMORY_REQUEST": "memory_request",
    "HSE_RUNNER__K8S__MEMORY_LIMIT": "memory_limit",
    "HSE_RUNNER__K8S__EPHEMERAL_STORAGE_REQUEST": "ephemeral_request",
    "HSE_RUNNER__K8S__EPHEMERAL_STORAGE_LIMIT": "ephemeral_limit",
}
_QUANTITY_MAX = 32

ClientFactory = Callable[[], KubernetesApiClient]


def _obj(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _items(data: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    items = data.get("items")
    return [_obj(item) for item in items] if isinstance(items, list) else []


def _strings(value: object) -> dict[str, str]:
    return {str(k): str(v) for k, v in _obj(value).items() if isinstance(v, str | int | float)}


def _quantity(value: object) -> str | None:
    text = str(value) if isinstance(value, str | int | float) else ""
    return text if 0 < len(text) <= _QUANTITY_MAX else None


def resources_of(container: Mapping[str, Any]) -> ResourceFigures | None:
    spec = _obj(container.get("resources"))
    requests, limits = _obj(spec.get("requests")), _obj(spec.get("limits"))
    if not requests and not limits:
        return None
    return ResourceFigures(
        cpu_request=_quantity(requests.get("cpu")),
        cpu_limit=_quantity(limits.get("cpu")),
        memory_request=_quantity(requests.get("memory")),
        memory_limit=_quantity(limits.get("memory")),
        ephemeral_request=_quantity(requests.get("ephemeral-storage")),
        ephemeral_limit=_quantity(limits.get("ephemeral-storage")),
        source=ResourceSource.cluster,
    )


def _build_resources(container: Mapping[str, Any]) -> ResourceFigures | None:
    """Лимиты подов сборки из явных значений env; ссылки (`valueFrom`) не читаются."""
    values: dict[str, str] = {}
    env = container.get("env")
    for item in env if isinstance(env, list) else []:
        entry = _obj(item)
        field = _BUILD_ENV.get(str(entry.get("name", "")))
        value = _quantity(entry.get("value"))
        if field is not None and value is not None:
            values[field] = value
    return ResourceFigures(**values, source=ResourceSource.cluster) if values else None


def security_of(pod: Mapping[str, Any], container: Mapping[str, Any]) -> SecurityFacts:
    """Контекст контейнера поверх контекста пода, как его применяет kubelet."""
    pod_ctx, ctx = _obj(pod.get("securityContext")), _obj(container.get("securityContext"))

    def pick(key: str) -> object:
        return ctx.get(key, pod_ctx.get(key))

    seccomp = _obj(pick("seccompProfile")).get("type")
    drop = _obj(ctx.get("capabilities")).get("drop")
    user = pick("runAsUser")
    non_root = pick("runAsNonRoot")
    automount = pod.get("automountServiceAccountToken")
    return SecurityFacts(
        run_as_non_root=non_root if isinstance(non_root, bool) else None,
        run_as_user=user if isinstance(user, int) and not isinstance(user, bool) and user >= 0 else None,
        read_only_root=ctx.get("readOnlyRootFilesystem") is True,
        no_privilege_escalation=ctx.get("allowPrivilegeEscalation") is False,
        seccomp=seccomp in ("RuntimeDefault", "Localhost") if seccomp is not None else False,
        capabilities_dropped=isinstance(drop, list) and "ALL" in drop,
        automount_token=automount if isinstance(automount, bool) else None,
    )


def deployment_of(item: Mapping[str, Any], namespace: str) -> LiveDeployment | None:
    meta = _obj(item.get("metadata"))
    name = meta.get("name")
    if not isinstance(name, str) or not name:
        return None
    pod = _obj(_obj(_obj(item.get("spec")).get("template")).get("spec"))
    containers = pod.get("containers")
    container = _obj(containers[0]) if isinstance(containers, list) and containers else {}
    image = container.get("image")
    account = pod.get("serviceAccountName")
    ready = _obj(item.get("status")).get("readyReplicas")
    return LiveDeployment(
        name=name,
        namespace=str(meta.get("namespace") or namespace),
        image=image if isinstance(image, str) and image else None,
        service_account=account if isinstance(account, str) and account else None,
        ready=isinstance(ready, int) and ready > 0,
        resources=resources_of(container),
        build_resources=_build_resources(container),
        security=security_of(pod, container),
    )


def _selects(policy: Mapping[str, Any], labels: Mapping[str, str]) -> bool:
    """Политика выбирает поды с такими метками: matchLabels подмножество меток, без matchExpressions."""
    selector = _obj(_obj(policy.get("spec")).get("podSelector"))
    if selector.get("matchExpressions"):
        return False
    wanted = _strings(selector.get("matchLabels"))
    return all(labels.get(key) == value for key, value in wanted.items())


def denies_all(policies: list[Mapping[str, Any]], labels: Mapping[str, str]) -> bool:
    """Есть политика без правил на вход и выход для подов с этими метками."""
    for policy in policies:
        spec = _obj(policy.get("spec"))
        types = spec.get("policyTypes")
        kinds = set(types) if isinstance(types, list) else set()
        closed = {"Ingress", "Egress"} <= kinds and not spec.get("ingress") and not spec.get("egress")
        if closed and _selects(policy, labels):
            return True
    return False


def limits_runner_egress(policies: list[Mapping[str, Any]]) -> bool:
    """Есть egress-политика раннеров чарта (component=runner) или раннеров из админки (метка установки)."""
    for policy in policies:
        spec = _obj(policy.get("spec"))
        types = spec.get("policyTypes")
        if not (isinstance(types, list) and "Egress" in types):
            continue
        labels = _strings(_obj(spec.get("podSelector")).get("matchLabels"))
        if labels.get("app.kubernetes.io/component") == "runner" or labels.get(INSTALL_LABEL) == "true":
            return True
    return False


def _pick_named(items: list[Mapping[str, Any]]) -> Mapping[str, Any] | None:
    """Объект чарта (`*-builds`), иначе первый."""
    for item in items:
        name = _obj(item.get("metadata")).get("name")
        if isinstance(name, str) and name.endswith("-builds"):
            return item
    return items[0] if items else None


def quota_of(item: Mapping[str, Any]) -> LiveQuota:
    return LiveQuota(
        name=str(_obj(item.get("metadata")).get("name", "")),
        hard=_strings(_obj(item.get("spec")).get("hard")),
        used=_strings(_obj(item.get("status")).get("used")),
    )


def limit_range_of(item: Mapping[str, Any]) -> LiveLimitRange:
    limits = _obj(item.get("spec")).get("limits")
    container: Mapping[str, Any] = {}
    for entry in limits if isinstance(limits, list) else []:
        if _obj(entry).get("type") == "Container":
            container = _obj(entry)
            break
    return LiveLimitRange(
        name=str(_obj(item.get("metadata")).get("name", "")),
        default=_strings(container.get("default")),
        default_request=_strings(container.get("defaultRequest")),
        max=_strings(container.get("max")),
    )


def namespace_security(name: str, item: Mapping[str, Any]) -> NamespaceSecurity:
    labels = _strings(_obj(item.get("metadata")).get("labels"))

    def label(key: str) -> str | None:
        return labels.get(_PSA_PREFIX + key) or None

    return NamespaceSecurity(
        namespace=name,
        enforce=label("enforce"),
        enforce_version=label("enforce-version"),
        warn=label("warn"),
        audit=label("audit"),
    )


class _Reads:
    """Счётчик удачных и запрещённых чтений: из него получается общий статус."""

    def __init__(self) -> None:
        self.ok = 0
        self.forbidden = 0
        self.failed = 0

    def status(self) -> LiveStatus:
        if self.ok and not (self.forbidden or self.failed):
            return LiveStatus.ok
        if self.ok:
            return LiveStatus.partial
        return LiveStatus.forbidden if self.forbidden and not self.failed else LiveStatus.unavailable


def _default_client() -> KubernetesApiClient:
    cfg = KubernetesExecutorConfig()
    return KubernetesApiClient(cfg.resolved_api_url(), TokenSource(cfg.token_file), cfg.ca_file)


def _in_cluster() -> bool:
    return bool(os.environ.get("KUBERNETES_SERVICE_HOST")) and (SA_DIR / "token").exists()


class KubeClusterStateReader:
    def __init__(
        self,
        *,
        read_live: bool,
        install_enabled: bool,
        namespace: str | None = None,
        client_factory: ClientFactory | None = None,
        in_cluster: Callable[[], bool] = _in_cluster,
        cache_ttl_s: float = _CACHE_TTL_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._read_live = read_live
        self._install_enabled = install_enabled
        self._namespace = namespace
        self._factory = client_factory or _default_client
        self._in_cluster = in_cluster
        self._ttl = cache_ttl_s
        self._clock = clock
        self._lock = asyncio.Lock()
        self._state: tuple[float, ClusterTargets, LiveClusterState] | None = None
        self._deployments: tuple[float, DeploymentListing] | None = None

    def _ns(self) -> str:
        return self._namespace or KubernetesExecutorConfig().resolved_namespace()

    async def cluster_state(self, targets: ClusterTargets) -> LiveClusterState:
        if not self._read_live:
            return LiveClusterState()
        async with self._lock:
            cached = self._state
            if cached is not None and cached[1] == targets and self._clock() - cached[0] < self._ttl:
                return cached[2]
            state = await self._read_state(targets) if self._in_cluster() else LiveClusterState(LiveStatus.unavailable)
            self._state = (self._clock(), targets, state)
            return state

    async def _read_state(self, targets: ClusterTargets) -> LiveClusterState:
        reads = _Reads()
        try:
            client = self._factory()
        except KubeApiError:
            return LiveClusterState(LiveStatus.unavailable, checked_at=datetime.now(UTC))
        try:

            async def get(path: str) -> Mapping[str, Any] | None:
                try:
                    data = await client.request_json("GET", path)
                except KubeApiError as exc:
                    if exc.status == _FORBIDDEN:
                        reads.forbidden += 1
                    else:
                        reads.failed += 1
                    return None
                reads.ok += 1
                return _obj(data)

            release, build = quote(targets.release_namespace), quote(targets.build_namespace)
            policies_path = "/apis/networking.k8s.io/v1/namespaces/{}/networkpolicies"
            build_policies = await get(policies_path.format(build))
            release_policies = build_policies if build == release else await get(policies_path.format(release))
            quotas = await get(f"/api/v1/namespaces/{build}/resourcequotas")
            ranges = await get(f"/api/v1/namespaces/{build}/limitranges")
            names = list(dict.fromkeys((targets.release_namespace, targets.build_namespace)))
            namespaces: list[NamespaceSecurity] = []
            for name in names:
                found = await get(f"/api/v1/namespaces/{quote(name)}")
                if found is not None:
                    namespaces.append(namespace_security(name, found))
        finally:
            await client.aclose()
        quota_item = _pick_named(_items(quotas)) if quotas is not None else None
        range_item = _pick_named(_items(ranges)) if ranges is not None else None
        return LiveClusterState(
            status=reads.status(),
            checked_at=datetime.now(UTC),
            build_deny_all=denies_all(_items(build_policies), _BUILD_LABELS) if build_policies is not None else None,
            ui_build_deny_all=(
                denies_all(_items(release_policies), _BUILD_LABELS) if release_policies is not None else None
            ),
            runner_egress=limits_runner_egress(_items(release_policies)) if release_policies is not None else None,
            quota_checked=quotas is not None,
            quota=quota_of(quota_item) if quota_item is not None else None,
            limit_range_checked=ranges is not None,
            limit_range=limit_range_of(range_item) if range_item is not None else None,
            namespaces=tuple(namespaces) if namespaces else None,
        )

    async def runner_deployments(self) -> DeploymentListing:
        if not self._install_enabled:
            return DeploymentListing(LookupStatus.not_applicable)
        if not self._in_cluster():
            return DeploymentListing(LookupStatus.unavailable)
        async with self._lock:
            cached = self._deployments
            if cached is not None and self._clock() - cached[0] < self._ttl:
                return cached[1]
            listing = await self._list_deployments()
            self._deployments = (self._clock(), listing)
            return listing

    async def _list_deployments(self) -> DeploymentListing:
        ns = self._ns()
        try:
            client = self._factory()
        except KubeApiError:
            return DeploymentListing(LookupStatus.unavailable)
        try:
            data = await client.request_json(
                "GET",
                f"/apis/apps/v1/namespaces/{quote(ns)}/deployments",
                params={"labelSelector": f"{INSTALL_LABEL}=true"},
            )
        except KubeApiError as exc:
            return DeploymentListing(LookupStatus.forbidden if exc.status == _FORBIDDEN else LookupStatus.unavailable)
        finally:
            await client.aclose()
        found = (deployment_of(item, ns) for item in _items(_obj(data)))
        return DeploymentListing(LookupStatus.ok, tuple(d for d in found if d is not None))
