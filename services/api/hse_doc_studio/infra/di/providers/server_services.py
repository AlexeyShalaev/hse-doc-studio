"""Пулы сервисов серверного режима: LanguageTool за прокси с кэшем."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.egress import EgressPurpose, IEgressPolicy
from hse_doc_studio.infra.egress.http import egress_client
from hse_doc_studio.infra.services.languagetool import LanguageToolProxy
from hse_doc_studio.infra.services.pool import PoolLimits, ServicePool


class ServerServicesProvider(Provider):
    scope = Scope.APP

    @provide
    def get_languagetool_proxy(self, egress: IEgressPolicy) -> LanguageToolProxy:
        cfg = settings.languagetool
        pool = ServicePool(
            "languagetool",
            cfg.pool_replicas,
            PoolLimits(
                max_inflight_per_replica=cfg.pool_max_inflight,
                user_rate_per_s=cfg.pool_user_rate_per_s,
                user_burst=cfg.pool_user_burst,
                circuit_failures=cfg.pool_circuit_failures,
                circuit_open_s=cfg.pool_circuit_open_s,
            ),
        )
        # Адрес реплик задаёт администратор: разрешены частные сети, метаданные облака закрыты всегда.
        client = egress_client(egress, EgressPurpose.admin, timeout=cfg.request_timeout_s, follow_redirects=False)
        return LanguageToolProxy(
            pool, client, cache_entries=cfg.pool_cache_entries, max_text_chars=cfg.pool_max_text_chars
        )
