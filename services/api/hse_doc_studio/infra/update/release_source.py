"""`IReleaseSource` поверх фида релизов (GitHub Releases по умолчанию)."""

from __future__ import annotations

from hse_doc_studio.core.server_update.entities import ReleaseInfo
from hse_doc_studio.core.server_update.protocols import FeedAnswer
from hse_doc_studio.infra.update.feed import GithubUpdateFeedGateway


class FeedReleaseSource:
    def __init__(self, gateway: GithubUpdateFeedGateway) -> None:
        self._gateway = gateway

    async def fetch(self) -> FeedAnswer:
        probe = await self._gateway.probe()
        if not probe.checked:
            return FeedAnswer(reason=str(probe.reason))
        return FeedAnswer(
            releases=tuple(
                ReleaseInfo(version=r.version, date=r.date, notes=r.notes, digests_url=r.digests_url)
                for r in probe.releases
            ),
            checked=True,
        )
