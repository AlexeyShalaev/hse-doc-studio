from __future__ import annotations

from datetime import datetime

from hse_doc_studio.core.quotas.kinds import QuotaKind, QuotaScope

QUOTA_EXCEEDED = "quota_exceeded"
OWNER_STORAGE_EXCEEDED = "owner_storage_exceeded"


class QuotaExceededError(Exception):
    """Запрос сверх предела вида. HTTP: 429 `quota_exceeded`; для места владельца 413 `owner_storage_exceeded`."""

    def __init__(
        self, kind: QuotaKind, scope: QuotaScope, used: int, limit: int, resets_at: datetime | None, owner_id: str = ""
    ) -> None:
        super().__init__(f"quota {kind.value}/{scope.value} exceeded: {used} of {limit}")
        self.kind = kind
        self.scope = scope
        self.used = used
        self.limit = limit
        self.resets_at = resets_at
        self.owner_id = owner_id
