"""Пулы сервисов серверного режима: LanguageTool за прокси с кэшем и ONLYOFFICE с липкими репликами."""

from __future__ import annotations

from dishka import Provider, Scope, provide

from hse_doc_studio.api.config import settings
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.egress import EgressPurpose, IEgressPolicy
from hse_doc_studio.core.identity.protocols import IUserRepository
from hse_doc_studio.core.office import IBackendReachability, IOfficeEditorService
from hse_doc_studio.core.office_tokens import OFFICE_TOKEN_KEY_PURPOSE, OfficeTokenSigner
from hse_doc_studio.infra.egress.http import egress_client
from hse_doc_studio.infra.office.pooled_editor import ConfiguredReachability, PooledOfficeEditorService
from hse_doc_studio.infra.secrets.key_store import KeyFileStore
from hse_doc_studio.infra.services.languagetool import LanguageToolProxy
from hse_doc_studio.infra.services.pool import PoolLimits, ServicePool
from hse_doc_studio.use_cases.office_editor.access import IOfficeAccess, ServerOfficeAccess


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

    @provide(override=True)
    def get_office_editor(self, egress: IEgressPolicy, key_store: KeyFileStore) -> IOfficeEditorService:
        cfg = settings.office_editor
        pool = ServicePool("onlyoffice", cfg.pool_replicas)
        client = egress_client(egress, EgressPurpose.admin, timeout=cfg.health_timeout_s, follow_redirects=False)

        async def probe(url: str) -> bool:
            response = await client.get(f"{url}{cfg.health_path}")
            return response.is_success and "true" in response.text

        # Секрет общий с репликами: из окружения, иначе производный от связки ключей (реплики берут тот же).
        secret = cfg.jwt_secret or key_store.ensure_primary().derive("office-jwt").hex()
        return PooledOfficeEditorService(
            pool,
            secret,
            probe,
            max_sessions=cfg.pool_max_sessions,
            session_ttl_s=cfg.pool_session_ttl_s,
            probe_interval_s=cfg.pool_probe_interval_s,
        )

    @provide(override=True)
    def get_office_reachability(self) -> IBackendReachability:
        cfg = settings.office_editor
        return ConfiguredReachability(
            cfg.backend_internal_url or f"http://{cfg.backend_host_for_container}:{settings.server.port}"
        )

    @provide
    def get_office_token_signer(self, key_store: KeyFileStore) -> OfficeTokenSigner:
        return OfficeTokenSigner(key_store.ensure_primary().derive_all(OFFICE_TOKEN_KEY_PURPOSE))

    @provide(override=True, scope=Scope.REQUEST)
    def get_office_access(
        self, signer: OfficeTokenSigner, acl: IProjectAclRepository, users: IUserRepository
    ) -> IOfficeAccess:
        return ServerOfficeAccess(signer, acl, users, ttl_s=settings.office_editor.token_ttl_s)
