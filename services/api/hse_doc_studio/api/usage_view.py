"""Перевод оценок использования в тела ответов."""

from __future__ import annotations

from hse_doc_studio.api.schemas.quotas import OwnerUsageResponse, UsageLine
from hse_doc_studio.core.quotas.kinds import KIND_SPECS
from hse_doc_studio.core.quotas.policy import Assessment
from hse_doc_studio.use_cases.quotas.usage import OwnerUsage


def usage_line(item: Assessment) -> UsageLine:
    return UsageLine(
        kind=item.kind.value,
        scope=item.scope.value,
        unit=KIND_SPECS[item.kind].unit,
        used=item.used,
        limit=item.limit,
        percent=item.percent,
        state=item.state.value,
        source=item.source.value if item.source is not None else None,
        resets_at=item.resets_at,
    )


def owner_usage_view(usage: OwnerUsage) -> OwnerUsageResponse:
    return OwnerUsageResponse(
        owner_id=usage.owner_id, owner_name=usage.owner_name, lines=[usage_line(i) for i in usage.lines]
    )
