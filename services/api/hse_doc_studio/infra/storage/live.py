"""Источник живых блобов, пока очереди задач нет."""

from __future__ import annotations


class NoLiveBlobs:
    async def live_blobs(self) -> set[str]:
        return set()
