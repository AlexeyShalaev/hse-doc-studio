"""Раннер Deployment-ом в кластере Студии: Secret с токеном, том данных и Deployment под отдельным ServiceAccount.

Права Студии на это (Role чарта, namespace релиза): Deployment create/list/update/delete, Secret и PVC create/delete.
`update` нужен только обновлению на месте и его откату: Deployment заменяется целиком, Secret и том не трогаются. Роль
раннера (поды сборки) создаёт чарт заранее, Студия её не выдаёт и поэтому не может расширить: права `escalate` и работа
с Role ей не нужны.
"""

from __future__ import annotations

import asyncio
import copy
import json
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from typing import Any
from urllib.parse import quote

from hse_doc_studio.core.identity.session_policy import utc_now
from hse_doc_studio.core.runner_install import (
    Capability,
    InstallError,
    InstallStepState,
    InstallTarget,
    InvalidResourcesError,
    LocalInstance,
    LocalRunnerSpec,
    PodResources,
    PreviousRelease,
    ProgressReporter,
    ResourceDefaults,
    ResourceOverrides,
    UnavailableReason,
    UpgradeError,
    UpgradeOutcome,
    resolve,
)
from hse_doc_studio.core.runner_install.resources import (
    BUILD_EPHEMERAL,
    RUNNER_EPHEMERAL,
    parse_cpu_millicores,
    parse_memory_bytes,
)
from hse_doc_studio.infra.compile.k8s.api import KubeApiError
from hse_doc_studio.infra.compile.k8s.client import KubernetesApiClient, TokenSource
from hse_doc_studio.infra.compile.k8s.config import SA_DIR, KubernetesExecutorConfig

INSTALL_LABEL = "hse-doc-studio/runner-install"
# Лимиты из формы установки (только заданные поля, JSON): обновление на месте берёт их отсюда, а не из умолчаний.
RESOURCES_ANNOTATION = "hse-doc-studio/runner-resources"
# Метка времени обновления в шаблоне пода: под пересоздаётся, даже если образ и манифест те же.
RESTARTED_ANNOTATION = "hse-doc-studio/restarted-at"
# Номер ревизии ведёт контроллер Deployment; при откате его не возвращаем, контроллер выставит свой.
_REVISION_ANNOTATION = "deployment.kubernetes.io/revision"
# PUT с resourceVersion живого объекта: контроллер меняет status и тем самым версию, поэтому конфликт повторяем.
_PUT_ATTEMPTS = 3
_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,40}[a-z0-9])?$")
_NOT_FOUND = 404
_FORBIDDEN = 403
_CONFLICT = 409

# Умолчания, если настройки не заданы (те же, что в values.yaml чарта).
DEFAULT_RESOURCES = ResourceDefaults(
    runner=PodResources(cpu_request="100m", cpu_limit="1", memory_request="256Mi", memory_limit="2Gi"),
    build=PodResources(cpu_request="500m", cpu_limit="2", memory_request="1Gi", memory_limit="4Gi"),
)
# /tmp раннера держит спул выгрузки (до 512 МиБ) и временные файлы; эфемерный диск в core (RUNNER_EPHEMERAL).
_RUNNER_TMP_SIZE = "1Gi"
_RUNNER_EPHEMERAL = RUNNER_EPHEMERAL
_BUILD_EPHEMERAL = BUILD_EPHEMERAL
# Старый под сначала доделывает сборки (до terminationGracePeriodSeconds), новый тянет образ: ждём с запасом.
ROLLOUT_TIMEOUT_S = 900.0
ROLLOUT_POLL_S = 2.0
_UPGRADE_STEPS = ("image", "manifest", "rollout")


_POD_FIELDS = (
    ("HSE_RUNNER__POD__NAMESPACE", "metadata.namespace"),
    ("HSE_RUNNER__POD__NAME", "metadata.name"),
    ("HSE_RUNNER__POD__SERVICE_ACCOUNT", "spec.serviceAccountName"),
)
_POD_RESOURCES = (
    ("HSE_RUNNER__POD__CPU_REQUEST_M", "requests.cpu", "1m"),
    ("HSE_RUNNER__POD__CPU_LIMIT_M", "limits.cpu", "1m"),
    ("HSE_RUNNER__POD__MEMORY_REQUEST_MI", "requests.memory", "1Mi"),
    ("HSE_RUNNER__POD__MEMORY_LIMIT_MI", "limits.memory", "1Mi"),
    ("HSE_RUNNER__POD__EPHEMERAL_REQUEST_MI", "requests.ephemeral-storage", "1Mi"),
    ("HSE_RUNNER__POD__EPHEMERAL_LIMIT_MI", "limits.ephemeral-storage", "1Mi"),
)


def pod_info_env(container: str) -> list[dict[str, Any]]:
    """Переменные downward API о своём поде; те же пишет чарт (runner.yaml, runner-kubernetes.yaml)."""
    env: list[dict[str, Any]] = [
        {"name": name, "valueFrom": {"fieldRef": {"fieldPath": path}}} for name, path in _POD_FIELDS
    ]
    env += [
        {
            "name": name,
            "valueFrom": {"resourceFieldRef": {"containerName": container, "resource": resource, "divisor": divisor}},
        }
        for name, resource, divisor in _POD_RESOURCES
    ]
    return env


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
        rollout_timeout_s: float = ROLLOUT_TIMEOUT_S,
        rollout_poll_s: float = ROLLOUT_POLL_S,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self._resources = resources
        self._rollout_timeout_s = rollout_timeout_s
        self._rollout_poll_s = rollout_poll_s
        self._clock = clock
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
        try:
            for group, resource in (("apps", "deployments"), ("", "secrets"), ("", "persistentvolumeclaims")):
                if not await self._allowed(client, "create", group, resource):
                    return Capability.no(UnavailableReason.no_permission)
        except KubeApiError:
            return Capability.no(UnavailableReason.no_permission)
        finally:
            if self._injected is None:
                await client.aclose()
        return Capability.yes()

    async def _allowed(self, client: KubernetesApiClient, verb: str, group: str, resource: str) -> bool:
        review = await client.request_json(
            "POST",
            "/apis/authorization.k8s.io/v1/selfsubjectaccessreviews",
            body={
                "apiVersion": "authorization.k8s.io/v1",
                "kind": "SelfSubjectAccessReview",
                "spec": {
                    "resourceAttributes": {"namespace": self._ns(), "verb": verb, "group": group, "resource": resource}
                },
            },
        )
        status = review.get("status")
        return isinstance(status, dict) and status.get("allowed") is True

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
        return {"secret": secret, "volume": claim, "deployment": self.deployment_manifest(spec)}

    def deployment_manifest(self, spec: LocalRunnerSpec, *, restarted_at: str | None = None) -> dict[str, Any]:
        """Deployment раннера по текущим правилам; токен в нём только ссылкой на Secret `<имя>-token`."""
        name = spec.name
        labels = self._labels(name)
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
            # Свой под из downward API: раннер сообщает это в админку (как развёрнут), на работу не влияет.
            *pod_info_env("runner"),
        ]
        deployment: dict[str, Any] = {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": name,
                "labels": labels,
                "annotations": {RESOURCES_ANNOTATION: _overrides_json(spec.resources)},
            },
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
        if restarted_at is not None:
            deployment["spec"]["template"]["metadata"]["annotations"] = {RESTARTED_ANNOTATION: restarted_at}
        return deployment

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

    # ---- обновление на месте ----

    def upgrade_steps(self) -> tuple[str, ...]:
        return _UPGRADE_STEPS

    async def upgrade(self, name: str, image: str, report: ProgressReporter) -> UpgradeOutcome:
        """Новый образ и манифест по текущим правилам; Secret с токеном и том данных не трогаются.

        Deployment заменяется целиком (PUT с resourceVersion живого): так уходят и устаревшие поля, и чужие правки.
        Стратегия Recreate: старый под доделывает сборки и уходит раньше, чем новый смонтирует RWO-том. Прежний
        Deployment (метки, аннотации, spec целиком) запоминается до замены: если выкатка не удалась, `UpgradeError`
        несёт его для `rollback`.
        """
        if not _NAME_RE.fullmatch(name):
            raise InstallError("not_installed")
        client = self._client()
        try:
            await report("image", InstallStepState.running, image)
            live = await self._live_deployment(client, name)
            if live is None:
                raise InstallError("not_installed")
            if not await self._allowed(client, "update", "apps", "deployments"):
                raise InstallError("kube_forbidden", "deployments: update")
            current = read_installed(live, self._resources)
            previous = PreviousRelease(image=current.image, state=deployment_snapshot(live))
            await report("image", InstallStepState.done, f"{current.image} {image}".strip())

            await report("manifest", InstallStepState.running, "")
            spec = LocalRunnerSpec(
                name=name,
                image=image,
                api_url=current.api_url,
                data_dir=current.data_dir,
                concurrency=current.concurrency,
                token="",
                resources=current.resources,
            )
            body = self.deployment_manifest(spec, restarted_at=self._clock().isoformat())
            generation = await self._replace(client, name, body, current.resource_version)
            await report("manifest", InstallStepState.done, ", ".join(current.dropped))

            await report("rollout", InstallStepState.running, "")
            await self._wait_replaced(client, name, generation, previous)
            await report("rollout", InstallStepState.done, "")
        except KubeApiError as exc:
            raise self._failure(exc, "") from exc
        finally:
            if self._injected is None:
                await client.aclose()
        return UpgradeOutcome(old_image=current.image, new_image=image, previous=previous)

    async def _wait_replaced(
        self, client: KubernetesApiClient, name: str, generation: int, previous: PreviousRelease
    ) -> None:
        """Выкатка уже заменённого Deployment; любой сбой с этого места несёт прежний Deployment для отката."""
        try:
            await self._wait_rollout(client, name, generation)
        except InstallError as exc:
            raise UpgradeError(exc.code, exc.detail, previous=previous) from exc
        except KubeApiError as exc:
            failure = self._failure(exc, "")
            raise UpgradeError(failure.code, failure.detail, previous=previous) from exc

    async def rollback(self, name: str, previous: PreviousRelease) -> None:
        """Прежний Deployment тем же PUT с resourceVersion живого и ожидание его выкатки.

        Шаблон пода становится прежним, поэтому контроллер поднимает прежний ReplicaSet (как `kubectl rollout undo`),
        а Recreate сначала убирает неудачный под и освобождает том.
        """
        if not _NAME_RE.fullmatch(name) or not previous.state:
            raise InstallError("not_installed")
        client = self._client()
        try:
            body = restored_deployment(name, previous.state)
            generation = await self._replace(client, name, body, None)
            await self._wait_rollout(client, name, generation)
        except KubeApiError as exc:
            raise self._failure(exc, "") from exc
        finally:
            if self._injected is None:
                await client.aclose()

    async def _replace(
        self, client: KubernetesApiClient, name: str, body: dict[str, Any], resource_version: str | None
    ) -> int:
        """PUT Deployment с версией живого объекта; конфликт версий (контроллер обновил status) повторяется с новой.

        Возвращает поколение, выкатку которого надо ждать.
        """
        path = f"/apis/apps/v1/namespaces/{quote(self._ns())}/deployments/{quote(name)}"
        version = resource_version
        attempts = 0
        while True:
            if version is None:
                live = await self._live_deployment(client, name)
                if live is None:
                    raise InstallError("not_installed")
                version = str(_obj(live.get("metadata")).get("resourceVersion") or "")
            body["metadata"]["resourceVersion"] = version
            try:
                applied = await client.request_json("PUT", path, body=body)
            except KubeApiError as exc:
                attempts += 1
                if exc.status != _CONFLICT or attempts >= _PUT_ATTEMPTS:
                    raise
                version = None
                continue
            return _int(_obj(applied.get("metadata")).get("generation"))

    async def _live_deployment(self, client: KubernetesApiClient, name: str) -> dict[str, Any] | None:
        """Deployment установки по имени. Через list, а не get: у Студии на Deployment нет `get` (Role чарта)."""
        data = await client.request_json(
            "GET",
            f"/apis/apps/v1/namespaces/{quote(self._ns())}/deployments",
            params={"labelSelector": f"{INSTALL_LABEL}=true", "fieldSelector": f"metadata.name={name}"},
        )
        items = data.get("items")
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and _obj(item.get("metadata")).get("name") == name:
                return item
        return None

    async def _wait_rollout(self, client: KubernetesApiClient, name: str, generation: int) -> None:
        """Как `kubectl rollout status`: контроллер увидел новое поколение, новый под готов, старых не осталось."""
        waited = 0.0
        while True:
            live = await self._live_deployment(client, name)
            if live is None:
                raise InstallError("not_installed")
            state = rollout_state(live, generation)
            if state == "done":
                return
            if state == "failed":
                raise InstallError("rollout_failed", "ProgressDeadlineExceeded")
            if waited >= self._rollout_timeout_s:
                raise InstallError("rollout_timeout")
            await asyncio.sleep(self._rollout_poll_s)
            waited += self._rollout_poll_s

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
        """Secret и том, затем Deployment. Уже удалённое (404) пропускается: повтор после сбоя доделывает остальное.

        Deployment уходит последним: по нему строится список установок, поэтому недоудалённая установка остаётся видна
        в админке и её можно удалить снова. Том с защитой от удаления пропадёт, когда уйдёт под.
        """
        if not _NAME_RE.fullmatch(name):
            return False
        if name not in {i.name for i in await self.list_instances()}:
            return False
        client = self._client()
        ns = quote(self._ns())
        paths = (
            f"/api/v1/namespaces/{ns}/secrets/{quote(f'{name}-token')}",
            f"/api/v1/namespaces/{ns}/persistentvolumeclaims/{quote(f'{name}-data')}",
            f"/apis/apps/v1/namespaces/{ns}/deployments/{quote(name)}",
        )
        try:
            for path in paths:
                try:
                    await client.request_json("DELETE", path)
                except KubeApiError as exc:
                    if exc.status != _NOT_FOUND:
                        raise InstallError("remove_failed", str(exc)[-400:]) from exc
        finally:
            if self._injected is None:
                await client.aclose()
        return True


def _obj(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _int(value: object) -> int:
    return value if isinstance(value, int) else 0


def _overrides_json(overrides: ResourceOverrides | None) -> str:
    chosen = {k: v for k, v in asdict(overrides).items() if v} if overrides is not None else {}
    return json.dumps(chosen, sort_keys=True, separators=(",", ":"))


_OVERRIDE_FIELDS = tuple(f.name for f in fields(ResourceOverrides))


@dataclass(frozen=True, slots=True)
class InstalledDeployment:
    """Что обновление берёт из живого Deployment: всё, кроме образа и правил манифеста, остаётся как было."""

    image: str
    api_url: str
    data_dir: str
    concurrency: int
    resources: ResourceOverrides | None
    resource_version: str
    # Поля лимитов, которые вышли за нынешние границы Helm и поэтому заменены умолчанием.
    dropped: tuple[str, ...] = ()


def _same(value: str, default: str, parse: Callable[[str], int]) -> bool:
    try:
        return parse(value) == parse(default)
    except ValueError:
        return False


def _overrides_from_annotation(meta: Mapping[str, Any]) -> ResourceOverrides | None:
    raw = _obj(meta.get("annotations")).get(RESOURCES_ANNOTATION)
    if not isinstance(raw, str):
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    return ResourceOverrides(**{k: str(v) for k, v in data.items() if k in _OVERRIDE_FIELDS and v})


def _overrides_from_live(
    container: Mapping[str, Any], env: Mapping[str, str], defaults: ResourceDefaults
) -> ResourceOverrides:
    """Старые установки без аннотации: переопределением считается лимит, который отличается от нынешнего умолчания."""
    limits = {k: str(v) for k, v in _obj(_obj(container.get("resources")).get("limits")).items()}

    def pick(value: str | None, default: str, parse: Callable[[str], int]) -> str | None:
        return value if value and not _same(value, default, parse) else None

    return ResourceOverrides(
        runner_cpu=pick(limits.get("cpu"), defaults.runner.cpu_limit, parse_cpu_millicores),
        runner_memory=pick(limits.get("memory"), defaults.runner.memory_limit, parse_memory_bytes),
        build_cpu=pick(env.get("HSE_RUNNER__K8S__CPU_LIMIT"), defaults.build.cpu_limit, parse_cpu_millicores),
        build_memory=pick(env.get("HSE_RUNNER__K8S__MEMORY_LIMIT"), defaults.build.memory_limit, parse_memory_bytes),
    )


def _fit(overrides: ResourceOverrides, defaults: ResourceDefaults) -> tuple[ResourceOverrides, tuple[str, ...]]:
    """Переопределения в нынешних границах: поле, которое в них не влезает, уступает умолчанию."""
    values = asdict(overrides)
    dropped: list[str] = []
    for _ in _OVERRIDE_FIELDS:
        try:
            resolve(defaults, ResourceOverrides(**values))
        except InvalidResourcesError as exc:
            values[exc.field] = None
            dropped.append(exc.field)
            continue
        break
    return ResourceOverrides(**values), tuple(dropped)


def read_installed(item: Mapping[str, Any], defaults: ResourceDefaults) -> InstalledDeployment:
    """Настройки установки из живого Deployment. Нужные раннеру адрес и каталог данных обязательны: без них личность
    раннера на томе не узнать (`identity.json` привязан к адресу Студии)."""
    meta = _obj(item.get("metadata"))
    pod = _obj(_obj(_obj(item.get("spec")).get("template")).get("spec"))
    containers = pod.get("containers")
    container = _obj(containers[0]) if isinstance(containers, list) and containers else {}
    env = {
        str(e.get("name")): str(e["value"])
        for e in container.get("env") or []
        if isinstance(e, dict) and isinstance(e.get("value"), str)
    }
    api_url = env.get("HSE_RUNNER__API_URL", "")
    data_dir = env.get("HSE_RUNNER__DATA_DIR", "")
    if not api_url or not data_dir:
        raise InstallError("not_installed", "HSE_RUNNER__API_URL / HSE_RUNNER__DATA_DIR")
    try:
        concurrency = max(1, int(env.get("HSE_RUNNER__CONCURRENCY", "1")))
    except ValueError:
        concurrency = 1
    overrides = _overrides_from_annotation(meta) or _overrides_from_live(container, env, defaults)
    fitted, dropped = _fit(overrides, defaults)
    image = container.get("image")
    return InstalledDeployment(
        image=image if isinstance(image, str) else "",
        api_url=api_url,
        data_dir=data_dir,
        concurrency=concurrency,
        resources=None if fitted.is_empty() else fitted,
        resource_version=str(meta.get("resourceVersion") or ""),
        dropped=dropped,
    )


def deployment_snapshot(item: Mapping[str, Any]) -> dict[str, Any]:
    """Всё, что заменяет обновление: метки и аннотации Deployment и spec целиком (образ, env, ресурсы, шаблон)."""
    meta = _obj(item.get("metadata"))
    annotations = {k: v for k, v in _obj(meta.get("annotations")).items() if k != _REVISION_ANNOTATION}
    return {
        "labels": copy.deepcopy(_obj(meta.get("labels"))),
        "annotations": copy.deepcopy(annotations),
        "spec": copy.deepcopy(_obj(item.get("spec"))),
    }


def restored_deployment(name: str, snapshot: Mapping[str, Any]) -> dict[str, Any]:
    """Deployment из снимка `deployment_snapshot` для PUT; resourceVersion подставляет `_replace`."""
    metadata: dict[str, Any] = {"name": name, "labels": copy.deepcopy(_obj(snapshot.get("labels")))}
    annotations = _obj(snapshot.get("annotations"))
    if annotations:
        metadata["annotations"] = copy.deepcopy(annotations)
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": metadata,
        "spec": copy.deepcopy(_obj(snapshot.get("spec"))),
    }


def rollout_state(item: Mapping[str, Any], generation: int) -> str:
    """`done`, `failed` (истёк progressDeadlineSeconds) или `pending`."""
    meta, spec, status = _obj(item.get("metadata")), _obj(item.get("spec")), _obj(item.get("status"))
    wanted = generation or _int(meta.get("generation"))
    # До нового поколения условия ещё от прошлой выкатки: по ним об этой судить нельзя.
    if _int(status.get("observedGeneration")) < wanted:
        return "pending"
    for condition in status.get("conditions") or []:
        if isinstance(condition, dict) and condition.get("reason") == "ProgressDeadlineExceeded":
            return "failed"
    replicas = spec.get("replicas")
    replicas = replicas if isinstance(replicas, int) else 1
    updated = _int(status.get("updatedReplicas"))
    total = _int(status.get("replicas"))
    available = _int(status.get("availableReplicas"))
    if updated >= replicas and total <= updated and available >= replicas:
        return "done"
    return "pending"
