"""Фейковое чтение живого состояния кластера для экрана изоляции раннеров."""

from __future__ import annotations

from hse_doc_studio.core.runner_isolation import ClusterTargets, DeploymentListing, LiveClusterState, LookupStatus


class FakeClusterReader:
    def __init__(self) -> None:
        self.state = LiveClusterState()
        self.listing = DeploymentListing(LookupStatus.not_applicable)
        self.asked: list[ClusterTargets] = []
        self.listed = 0

    async def cluster_state(self, targets: ClusterTargets) -> LiveClusterState:
        self.asked.append(targets)
        return self.state

    async def runner_deployments(self) -> DeploymentListing:
        self.listed += 1
        return self.listing
