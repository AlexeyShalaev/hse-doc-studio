"""Раннер Deployment-ом в кластере Студии: Secret с токеном, том данных и Deployment под отдельным ServiceAccount.

Права Студии на это ровно create/get/list/delete для Deployment, Secret и PVC в своём namespace (Role чарта). Роль
самого раннера (поды сборки) создаёт чарт заранее, Студия её не выдаёт и поэтому не может расширить: права
`escalate` и работа с Role ей не нужны.
"""

from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote

from hse_doc_studio.core.runner_install import (
    Capability,
    InstallError,
    InstallStepState,
    InstallTarget,
    LocalInstance,
    LocalRunnerSpec,
    PodResources,
    ProgressReporter,
    ResourceDefaults,
    ResourceOverrides,
    UnavailableReason,
    resolve,
)
from hse_doc_studio.infra.compile.k8s.api import KubeApiError
from hse_doc_studio.infra.compile.k8s.client import KubernetesApiClient, TokenSource
from hse_doc_studio.infra.compile.k8s.config import SA_DIR, KubernetesExecutorConfig

INSTALL_LABEL = "hse-doc-studio/runner-install"
_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,40}[a-z0-9])?$")
_NOT_FOUND = 404
_FORBIDDEN = 403
_CONFLICT = 409

# Умолчания, если настройки не заданы (те же, что в values.yaml чарта).
DEFAULT_RESOURCES = ResourceDefaults(
    runner=PodResources(cpu_request="100m", cpu_limit="1", memory_request="256Mi", memory_limit="2Gi"),
    build=PodResources(cpu_request="500m", cpu_limit="2", memory_request="1Gi", memory_limit="4Gi"),
)
# Эфемерное хранилище: том данных на PVC, а /tmp раннера держит спул выгрузки (до 512 МиБ) и временные файлы.
_RUNNER_TMP_SIZE = "1Gi"
_RUNNER_EPHEMERAL = ("128Mi", "2Gi")
_BUILD_EPHEMERAL = ("1Gi", "4Gi")


class KubeLocalHost:
    target = InstallTarget.kubernetes

    def __init__(
        self,
        *,
        enabled: bool,
        service_account: str,
        storage_class: str = "",
        storage_size: str = "5Gi",
        client: KubernetesApiClient | None = None,
        namespace: str | None = None,
        resources: ResourceDefaults = DEFAULT_RESOURCES,
    ) -> None:
        self._resources = resources
        self._enabled = enabled
        self._service_account = service_account
        self._storage_class = storage_class
        self._storage_size = storage_size
        self._injected = client
        self._cfg = KubernetesExecutorConfig()
        self._namespace = namespace

    def _ns(self) -> str:
        return self._namespace or self._cfg.resolved_namespace()

    def _client(self) -> KubernetesApiClient:
        if self._injected is not None:
            return self._injected
        return KubernetesApiClient(self._cfg.resolved_api_url(), TokenSource(self._cfg.token_file), self._cfg.ca_file)

    async def capability(self) -> Capability:
        if not self._enabled or not self._service_account:
            return Capability.no(UnavailableReason.disabled)
        if self._injected is None and not (os.environ.get("KUBERNETES_SERVICE_HOST") and (SA_DIR / "token").exists()):
            return Capability.no(UnavailableReason.not_in_cluster)
        client = self._client()
        ns = self._ns()
        try:
            for group, resource in (("apps", "deployments"), ("", "secrets"), ("", "persistentvolumeclaims")):
                review = await client.request_json(
                    "POST",
                    "/apis/authorization.k8s.io/v1/selfsubjectaccessreviews",
                    body={
                        "apiVersion": "authorization.k8s.io/v1",
                        "kind": "SelfSubjectAccessReview",
                        "spec": {
                            "resourceAttributes": {
                                "namespace": ns,
                                "verb": "create",
                                "group": group,
                                "resource": resource,
                            }
                        },
                    },
                )
                status = review.get("status")
                if not (isinstance(status, dict) and status.get("allowed") is True):
                    return Capability.no(UnavailableReason.no_permission)
        except KubeApiError:
            return Capability.no(UnavailableReason.no_permission)
        finally:
            if self._injected is None:
                await client.aclose()
        return Capability.yes()

    def check_resources(self, overrides: ResourceOverrides | None) -> None:
        resolve(self._resources, overrides)

    def steps(self) -> tuple[str, ...]:
        return ("secret", "volume", "deployment")

    def _labels(self, name: str) -> dict[str, str]:
        return {
            INSTALL_LABEL: "true",
            "app.kubernetes.io/name": "hse-doc-studio-runner",
            "app.kubernetes.io/instance": name,
            "app.kubernetes.io/component": "runner",
        }

    def manifests(self, spec: LocalRunnerSpec) -> dict[str, dict[str, Any]]:
        name = spec.name
        labels = self._labels(name)
        secret = {
            "apiVersion": "v1",
            "kind": "Secret",
            "metadata": {"name": f"{name}-token", "labels": labels},
            "type": "Opaque",
            "stringData": {"token": spec.token},
        }
        claim: dict[str, Any] = {
            "apiVersion": "v1",
            "kind": "PersistentVolumeClaim",
            "metadata": {"name": f"{name}-data", "labels": labels},
            "spec": {"accessModes": ["ReadWriteOnce"], "resources": {"requests": {"storage": self._storage_size}}},
        }
        if self._storage_class:
            claim["spec"]["storageClassName"] = self._storage_class
        ns = self._ns()
        runner_res, build_res = resolve(self._resources, spec.resources)
        env = [
            {"name": "HSE_RUNNER__API_URL", "value": spec.api_url},
            {"name": "HSE_RUNNER__DATA_DIR", "value": spec.data_dir},
            {"name": "HSE_RUNNER__CONCURRENCY", "value": str(spec.concurrency)},
            {"name": "HSE_RUNNER__NAME", "value": name},
            {"name": "HSE_RUNNER__TOKEN", "valueFrom": {"secretKeyRef": {"name": f"{name}-token", "key": "token"}}},
            {"name": "HSE_RUNNER__EXECUTOR", "value": "kubernetes"},
            {"name": "HSE_RUNNER__K8S__NAMESPACE", "value": ns},
            {"name": "HSE_RUNNER__K8S__OWNER_POD_NAME", "valueFrom": {"fieldRef": {"fieldPath": "metadata.name"}}},
            {"name": "HSE_RUNNER__K8S__OWNER_POD_UID", "valueFrom": {"fieldRef": {"fieldPath": "metadata.uid"}}},
            # Лимиты подов сборки, которые этот раннер создаёт сам.
            {"name": "HSE_RUNNER__K8S__CPU_REQUEST", "value": build_res.cpu_request},
            {"name": "HSE_RUNNER__K8S__CPU_LIMIT", "value": build_res.cpu_limit},
            {"name": "HSE_RUNNER__K8S__MEMORY_REQUEST", "value": build_res.memory_request},
            {"name": "HSE_RUNNER__K8S__MEMORY_LIMIT", "value": build_res.memory_limit},
            {"name": "HSE_RUNNER__K8S__EPHEMERAL_STORAGE_REQUEST", "value": _BUILD_EPHEMERAL[0]},
            {"name": "HSE_RUNNER__K8S__EPHEMERAL_STORAGE_LIMIT", "value": _BUILD_EPHEMERAL[1]},
        ]
        deployment = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {"name": name, "labels": labels},
            "spec": {
                "replicas": 1,
                "strategy": {"type": "Recreate"},
                "selector": {"matchLabels": {"app.kubernetes.io/instance": name, INSTALL_LABEL: "true"}},
                "template": {
                    "metadata": {"labels": labels},
                    "spec": {
                        "serviceAccountName": self._service_account,
                        "terminationGracePeriodSeconds": 600,
                        # Токен ServiceAccount нужен раннеру: через него он создаёт поды сборки. Его права: только
                        # поды сборки в этом namespace (Role чарта).
                        "automountServiceAccountToken": True,
                        "enableServiceLinks": False,
                        "securityContext": {
                            "runAsNonRoot": True,
                            "runAsUser": 1000,
                            "runAsGroup": 1000,
                            "fsGroup": 1000,
                            "seccompProfile": {"type": "RuntimeDefault"},
                        },
                        "containers": [
                            {
                                "name": "runner",
                                "image": spec.image,
                                "command": ["hse-doc-studio", "runner"],
                                "env": env,
                                "resources": runner_res.as_manifest(
                                    {"ephemeral-storage": _RUNNER_EPHEMERAL[0]},
                                    {"ephemeral-storage": _RUNNER_EPHEMERAL[1]},
                                ),
                                "securityContext": {
                                    "allowPrivilegeEscalation": False,
                                    "readOnlyRootFilesystem": True,
                                    "capabilities": {"drop": ["ALL"]},
                                },
                                "volumeMounts": [
                                    {"name": "runner-data", "mountPath": spec.data_dir},
                                    {"name": "tmp", "mountPath": "/tmp"},  # noqa: S108
                                ],
                            }
                        ],
                        "volumes": [
                            {"name": "runner-data", "persistentVolumeClaim": {"claimName": f"{name}-data"}},
                            {"name": "tmp", "emptyDir": {"sizeLimit": _RUNNER_TMP_SIZE}},
                        ],
                    },
                },
            },
        }
        return {"secret": secret, "volume": claim, "deployment": deployment}

    async def install(self, spec: LocalRunnerSpec, report: ProgressReporter) -> None:
        if not _NAME_RE.fullmatch(spec.name):
            raise InstallError("invalid_name")
        client = self._client()
        ns = quote(self._ns())
        paths = {
            "secret": f"/api/v1/namespaces/{ns}/secrets",
            "volume": f"/api/v1/namespaces/{ns}/persistentvolumeclaims",
            "deployment": f"/apis/apps/v1/namespaces/{ns}/deployments",
        }
        manifests = self.manifests(spec)
        try:
            for key in self.steps():
                await report(key, InstallStepState.running, "")
                await self._create(client, paths[key], manifests[key], replace=key != "volume", token=spec.token)
                await report(key, InstallStepState.done, "")
        finally:
            if self._injected is None:
                await client.aclose()

    async def _create(
        self, client: KubernetesApiClient, path: str, body: dict[str, Any], *, replace: bool, token: str
    ) -> None:
        name = quote(str(body["metadata"]["name"]))
        try:
            await client.request_json("POST", path, body=body)
        except KubeApiError as exc:
            if exc.status == _CONFLICT:
                # Повторная установка с тем же именем: Secret и Deployment заменяем, том с личностью раннера оставляем.
                if not replace:
                    return
                await client.request_json("DELETE", f"{path}/{name}")
                try:
                    await client.request_json("POST", path, body=body)
                except KubeApiError as again:
                    raise self._failure(again, token) from again
                return
            raise self._failure(exc, token) from exc

    @staticmethod
    def _failure(exc: KubeApiError, token: str) -> InstallError:
        code = "kube_forbidden" if exc.status == _FORBIDDEN else "kube_failed"
        text = str(exc).replace(token, "***") if token else str(exc)
        return InstallError(code, text[-400:])

    async def list_instances(self) -> list[LocalInstance]:
        client = self._client()
        ns = quote(self._ns())
        try:
            data = await client.request_json(
                "GET", f"/apis/apps/v1/namespaces/{ns}/deployments", params={"labelSelector": f"{INSTALL_LABEL}=true"}
            )
        except KubeApiError:
            return []
        finally:
            if self._injected is None:
                await client.aclose()
        items = data.get("items")
        found: list[LocalInstance] = []
        for item in items if isinstance(items, list) else []:
            meta = item.get("metadata", {}) if isinstance(item, dict) else {}
            status = item.get("status", {}) if isinstance(item, dict) else {}
            containers = item.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [{}])
            ready = int(status.get("readyReplicas") or 0) if isinstance(status, dict) else 0
            created = meta.get("creationTimestamp")
            found.append(
                LocalInstance(
                    target=self.target,
                    name=str(meta.get("name", "")),
                    image=str(containers[0].get("image", "")),
                    state="running" if ready else "pending",
                    created_at=datetime.fromisoformat(created.replace("Z", "+00:00"))
                    if isinstance(created, str)
                    else None,
                )
            )
        return found

    async def remove(self, name: str) -> bool:
        if not _NAME_RE.fullmatch(name):
            return False
        if name not in {i.name for i in await self.list_instances()}:
            return False
        client = self._client()
        ns = quote(self._ns())
        try:
            await client.request_json("DELETE", f"/apis/apps/v1/namespaces/{ns}/deployments/{quote(name)}")
            await client.request_json("DELETE", f"/api/v1/namespaces/{ns}/secrets/{quote(f'{name}-token')}")
            await client.request_json(
                "DELETE", f"/api/v1/namespaces/{ns}/persistentvolumeclaims/{quote(f'{name}-data')}"
            )
        except KubeApiError as exc:
            if exc.status != _NOT_FOUND:
                return False
        finally:
            if self._injected is None:
                await client.aclose()
        return True
