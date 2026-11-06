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
