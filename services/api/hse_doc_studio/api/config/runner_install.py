"""Установка раннеров из админки (docs/design/runner-install.md): на этой же машине и по SSH."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from hse_doc_studio.core.egress import EgressAllowlist


class RunnerInstallConfig(BaseModel):
    docker_enabled: bool = Field(
        default=True,
        description="Разрешить установку раннера соседним контейнером через docker.sock Студии (если сокет доступен).",
    )
    kubernetes_enabled: bool = Field(
        default=False,
        description=(
            "Разрешить установку раннера Deployment-ом в кластере Студии. Включает чарт (runner.installFromUi.enabled) "
            "вместе с правами ServiceAccount Студии."
        ),
    )
    kubernetes_service_account: str = Field(
        default="",
        description=(
            "ServiceAccount установленных из админки раннеров: его создаёт чарт, права только на поды сборки."
        ),
    )
    kubernetes_studio_url: str = Field(
        default="",
        description="Адрес Студии для раннеров в кластере (внутренний Service); пусто значит публичный адрес.",
    )
    kubernetes_storage_class: str = Field(
        default="", description="StorageClass тома данных установленного раннера; пусто значит по умолчанию кластера."
    )
    kubernetes_storage_size: str = Field(default="5Gi", description="Размер тома данных установленного раннера.")
    kubernetes_runner_cpu_request: str = Field(default="100m", description="requests.cpu пода раннера.")
    kubernetes_runner_cpu_limit: str = Field(default="1", description="limits.cpu пода раннера.")
    kubernetes_runner_memory_request: str = Field(default="256Mi", description="requests.memory пода раннера.")
    kubernetes_runner_memory_limit: str = Field(default="2Gi", description="limits.memory пода раннера.")
    kubernetes_build_cpu_request: str = Field(default="500m", description="requests.cpu подов сборки.")
    kubernetes_build_cpu_limit: str = Field(default="2", description="limits.cpu подов сборки.")
    kubernetes_build_memory_request: str = Field(default="1Gi", description="requests.memory подов сборки.")
    kubernetes_build_memory_limit: str = Field(
        default="4Gi", description="limits.memory подов сборки: TeX на обычном документе укладывается в 1-2 ГиБ."
    )
    kubernetes_resource_max_cpu: str = Field(
        default="8", description="Верхняя граница CPU, которую админ может задать в форме установки."
    )
    kubernetes_resource_max_memory: str = Field(
        default="16Gi", description="Верхняя граница памяти, которую админ может задать в форме установки."
    )
    data_dir: str = Field(
        default="/var/lib/hse-runner", description="Каталог данных раннера на хосте (docker) и в поде (kubernetes)."
    )
    ssh_enabled: bool = Field(default=True, description="Разрешить установку раннеров по SSH из админки.")
    ssh_allowlist: list[str] = Field(
        default_factory=list,
        description=(
            "Внутренние узлы, на которые можно ставить раннер по SSH: имя (host.corp.local, *.corp.local), IP или "
            "CIDR. Без записи закрыты частные сети, loopback и адреса кластера; адреса метаданных облака и "
            "link-local закрыты всегда. Дополняет HSE_STUDIO__EGRESS__ALLOWLIST."
        ),
    )
    ssh_save_credentials: bool = Field(
        default=True,
        description="Разрешить сохранять SSH-доступы зашифрованно (нужен ключ шифрования секретов).",
    )

    @field_validator("ssh_allowlist")
    @classmethod
    def _valid_allowlist(cls, value: list[str]) -> list[str]:
        EgressAllowlist.parse(value)
        return value
