"""Изоляция раннеров в кластере для экрана админки: выжимка Helm и право читать живое состояние."""

from __future__ import annotations

from pydantic import BaseModel, Field

from hse_doc_studio.core.runner_isolation.declared import DeclaredCluster


class RunnerClusterConfig(BaseModel):
    declared: DeclaredCluster | None = Field(
        default=None,
        description=(
            "Выжимка values Helm о раннерах (JSON): исполнитель, лимиты, сеть, квота, LimitRange. Её пишет чарт, "
            "руками не задаётся; пусто вне Helm."
        ),
    )
    read_live: bool = Field(
        default=False,
        description=(
            "Читать живое состояние кластера для экрана изоляции раннеров (NetworkPolicy, ResourceQuota, LimitRange, "
            "метки Pod Security у namespace). Включает чарт вместе с правами: runner.isolationInfo.readCluster."
        ),
    )
