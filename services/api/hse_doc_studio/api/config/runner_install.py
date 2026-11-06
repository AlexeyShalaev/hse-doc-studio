"""Установка раннеров из админки (docs/design/runner-install.md): на этой же машине и по SSH."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
