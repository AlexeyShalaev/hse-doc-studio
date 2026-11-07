"""Порт чтения живого состояния кластера для экрана изоляции раннеров."""

from __future__ import annotations

from typing import Protocol

from hse_doc_studio.core.runner_isolation.entities import ClusterTargets, DeploymentListing, LiveClusterState


class IClusterStateReader(Protocol):
    async def cluster_state(self, targets: ClusterTargets) -> LiveClusterState:
        """NetworkPolicy, ResourceQuota, LimitRange и метки Pod Security; без опции чтения статус `off`."""
        ...

    async def runner_deployments(self) -> DeploymentListing:
        """Deployment раннеров, поставленных из админки (по метке установки), в namespace релиза."""
        ...
