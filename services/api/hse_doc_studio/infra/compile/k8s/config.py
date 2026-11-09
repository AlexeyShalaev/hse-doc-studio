"""Настройки исполнителя kubernetes (HSE_RUNNER__K8S__*): где и с какими пределами идут поды сборки."""

from __future__ import annotations

import os
import re
from pathlib import Path

from pydantic import BaseModel, Field

SA_DIR = Path("/var/run/secrets/kubernetes.io/serviceaccount")
_MIB = 1024**2
_LABEL_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")


class KubernetesExecutorConfig(BaseModel):
    namespace: str = Field(
        default="", description="Namespace подов сборки; пусто значит namespace ServiceAccount раннера."
    )
    api_url: str = Field(
        default="", description="Адрес Kubernetes API; пусто значит внутрикластерный (KUBERNETES_SERVICE_HOST)."
    )
    token_file: Path = Field(default=SA_DIR / "token", description="Файл токена ServiceAccount.")
    ca_file: Path = Field(default=SA_DIR / "ca.crt", description="Сертификат CA Kubernetes API.")
    owner_pod_name: str = Field(default="", description="Имя пода раннера (downward API): владелец подов сборки.")
    owner_pod_uid: str = Field(
        default="", description="UID пода раннера (downward API): метка и владелец подов сборки."
    )
    owner_pod_namespace: str = Field(
        default="",
        description=(
            "Namespace пода раннера; пусто значит namespace его ServiceAccount. Владелец ставится подам сборки "
            "только в этом же namespace: ссылка на владельца из другого namespace недействительна, и сборщик "
            "мусора Kubernetes сразу удаляет такой под."
        ),
    )
    image: str = Field(default="", description="Образ TeX для подов; пусто значит HSE_RUNNER__TEX_IMAGE.")
    image_pull_policy: str = Field(default="IfNotPresent", pattern=r"^(Always|IfNotPresent|Never)$")
    image_pull_secrets: list[str] = Field(default_factory=list, description="Имена Secret для pull образа.")
    cpu_request: str = "500m"
    cpu_limit: str = "2"
    memory_request: str = "1Gi"
    memory_limit: str = "4Gi"
    ephemeral_storage_request: str = Field(default="1Gi", description="requests.ephemeral-storage пода сборки.")
    ephemeral_storage_limit: str = Field(
        default="4Gi", description="limits.ephemeral-storage пода сборки: /work + /tmp + логи с запасом."
    )
    work_size_limit: str = Field(default="2Gi", description="Предел emptyDir /work (исходники и .build).")
    tmp_size_limit: str = Field(default="1Gi", description="Предел emptyDir /tmp (форматы и кэш TeX).")
    active_deadline_s: int = Field(default=1800, ge=60, description="activeDeadlineSeconds пода сборки.")
    pod_start_timeout_s: float = Field(default=300.0, gt=0, description="Сколько ждать запуска пода (pull образа).")
    run_as_user: int = Field(default=1000, ge=1)
    run_as_group: int = Field(default=1000, ge=1)
    fs_group: int = Field(default=1000, ge=1)
    node_selector: dict[str, str] = Field(default_factory=dict, description="nodeSelector подов сборки (JSON).")
    tolerations: list[dict[str, str | int]] = Field(
        default_factory=list, description="tolerations подов сборки (JSON-список)."
    )
    priority_class_name: str = ""
    runtime_class_name: str = Field(default="", description="RuntimeClass подов сборки, например gvisor или kata.")
    tex_cache_claim: str = Field(default="", description="PVC с кэшем шрифтов TeX в /cache; пусто значит без кэша.")
    fonts_claim: str = Field(
        default="",
        description=(
            "PVC со шрифтами (.ttf, .otf, .ttc): монтируется в поды сборки только для чтения, чтобы XeLaTeX "
            "находил Times New Roman, Arial и Consolas по имени; пусто значит без своих шрифтов."
        ),
    )
    fonts_mount_target: str = Field(default="/usr/local/share/fonts/hse", description="Куда монтировать fonts_claim.")
    max_output_bytes: int = Field(default=512 * _MIB, gt=0, description="Предел выхода сборки (.build документа).")

    def resolved_namespace(self) -> str:
        if self.namespace:
            return self.namespace
        try:
            return (SA_DIR / "namespace").read_text(encoding="utf-8").strip() or "default"
        except OSError:
            return "default"

    def own_namespace(self) -> str:
        """Namespace пода раннера; пусто, если его не узнать (раннер вне кластера)."""
        if self.owner_pod_namespace:
            return self.owner_pod_namespace
        try:
            return (SA_DIR / "namespace").read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def owns_builds_in(self, namespace: str) -> bool:
        """Можно ли сделать под раннера владельцем подов сборки в namespace: только в его собственном."""
        return bool(self.owner_pod_name and self.owner_pod_uid) and self.own_namespace() == namespace

    def resolved_api_url(self) -> str:
        if self.api_url:
            return self.api_url.rstrip("/")
        host = os.environ.get("KUBERNETES_SERVICE_HOST", "")
        port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
        if not host:
            return ""
        if ":" in host:
            host = f"[{host}]"
        return f"https://{host}:{port}"


def instance_label(owner_pod_uid: str, runner_name: str) -> str:
    """Значение метки экземпляра раннера: uid его пода, а вне кластера имя раннера (до 63 символов)."""
    raw = owner_pod_uid or runner_name or "runner"
    value = _LABEL_UNSAFE.sub("-", raw)[:63].strip("-_.")
    return value or "runner"
