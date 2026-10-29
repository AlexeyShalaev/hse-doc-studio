"""Настройки git-серверов и проверка сохранённого токена.

Настройки хоста: выбор типа сервера человеком, свой CA, закреплённый сертификат. Доверие к сертификату выдаётся
только отпечатку, который человек видел: сервер читает сертификат заново и сохраняет его, лишь если отпечаток тот же.
Это тот же приём, что у ключей ssh (TrustHostUC): между показом и подтверждением хост мог предъявить другой.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from uuid import UUID

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.credentials import normalize_credential_host, normalize_port
from hse_doc_studio.core.git_sync.entities import GitCredential, GitCredentialKind, TokenState
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.host_keys import is_fingerprint
from hse_doc_studio.core.git_sync.host_settings import GitHostSettings, host_settings_key
from hse_doc_studio.core.git_sync.protocols import (
    ICertificateService,
    IGitCredentialRepository,
    IGitCredentialUsage,
    IGitHostSettingsRepository,
)
from hse_doc_studio.core.git_sync.providers import GitProvider, ProviderInfo, api_base, web_base
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.use_cases.git_sync.credentials import CredentialView
from hse_doc_studio.use_cases.git_sync.provider_resolver import ProviderResolver, ResolvedProvider
from hse_doc_studio.use_cases.git_sync.token_check import TokenCheck, TokenChecker

FIELD_PROVIDER_OVERRIDE = "provider_override"
FIELD_CA_PEM = "ca_pem"
FIELD_PINNED_FINGERPRINT = "pinned_fingerprint"


@dataclass(frozen=True)
class HostSettingsView:
    settings: GitHostSettings
    provider: ProviderInfo


class ListHostSettingsUC:
    """Серверы с настройками и серверы, для которых сохранён доступ: человеку нужен один список."""

    def __init__(
        self, settings: IGitHostSettingsRepository, credentials: IGitCredentialRepository, resolver: ProviderResolver
    ) -> None:
        self._settings = settings
        self._credentials = credentials
        self._resolver = resolver

    async def execute(self) -> list[HostSettingsView]:
        items = {item.key: item for item in self._settings.list()}
        for credential in await self._credentials.list():
            items.setdefault(host_settings_key(credential.host, None), GitHostSettings(credential.host))
        return [HostSettingsView(item, self._resolver.known(item.host, item.port)) for item in items.values()]


@dataclass
class UpdateHostSettingsInput:
    host: str
    port: int | None = None
    provider_override: str | None = None
    ca_pem: str | None = None
    pinned_fingerprint: str | None = None
    # Какие поля пришли в запросе: отсутствующее остаётся как есть, пришедшее null сбрасывается.
    given: frozenset[str] = frozenset()


def _provider(value: str) -> GitProvider:
    try:
        return GitProvider(value)
    except ValueError:
        raise git_error(GitErrorCode.provider_unknown) from None


class UpdateHostSettingsUC:
    def __init__(
        self,
        settings: IGitHostSettingsRepository,
        certificates: ICertificateService,
        resolver: ProviderResolver,
    ) -> None:
        self._settings = settings
        self._certificates = certificates
        self._resolver = resolver

    async def execute(self, inp: UpdateHostSettingsInput) -> HostSettingsView:
        host = normalize_credential_host(inp.host)
        port = normalize_port(inp.port)
        current = self._settings.get(host, port) or GitHostSettings(host, port)
        updated = current
        if FIELD_PROVIDER_OVERRIDE in inp.given:
            override = None if inp.provider_override is None else _provider(inp.provider_override)
            updated = replace(updated, provider_override=override)
        if FIELD_CA_PEM in inp.given:
            ca_pem = None if inp.ca_pem is None else self._certificates.normalize_ca_pem(inp.ca_pem)
            updated = replace(updated, ca_pem=ca_pem)
        if FIELD_PINNED_FINGERPRINT in inp.given:
            updated = await self._pin(updated, inp.pinned_fingerprint)
        self._settings.save(updated)
        return HostSettingsView(updated, self._resolver.known(host, port))

    async def _pin(self, settings: GitHostSettings, fingerprint: str | None) -> GitHostSettings:
        if fingerprint is None:
            return replace(settings, pinned_fingerprint=None, pinned_pem=None)
        confirmed = fingerprint.strip()
        if not is_fingerprint(confirmed):
            raise GitSyncError(
                GitErrorCode.host_settings_invalid,
                localized_error(
                    "Отпечаток сертификата: SHA256: и 43 символа base64",
                    "The certificate fingerprint must be SHA256: followed by 43 base64 characters",
                ),
            )
        presented = await self._certificates.fetch(settings.host, settings.port)
        if presented.fingerprint_sha256 != confirmed:
            raise git_error(GitErrorCode.tls_pin_mismatch, expected=confirmed, actual=presented.fingerprint_sha256)
        return replace(settings, pinned_fingerprint=confirmed, pinned_pem=presented.pem)


@dataclass(frozen=True)
class CredentialCheckView:
    credential: CredentialView
    provider: ProviderInfo
    # None: у этого провайдера нет способа проверить токен, например Bitbucket.
    token: TokenCheck | None


class CheckCredentialUC:
    """«Проверить» у сохранённого токена: чей он, какие права и срок. Токен не принят или истёк: ошибка с кодом."""

    def __init__(
        self,
        credentials: IGitCredentialRepository,
        settings: IGitHostSettingsRepository,
        resolver: ProviderResolver,
        token_checker: TokenChecker,
        usage: IGitCredentialUsage,
    ) -> None:
        self._credentials = credentials
        self._usage = usage
        self._settings = settings
        self._resolver = resolver
        self._tokens = token_checker

    async def execute(self, credential_id: UUID) -> CredentialCheckView:
        credential = await self._credentials.get(credential_id)
        if credential is None:
            raise NotFoundError(localized_error("Доступ не найден", "Credential not found"))
        if credential.kind is not GitCredentialKind.pat:
            raise GitSyncError(
                GitErrorCode.credential_invalid,
                localized_error("Проверяются только токены", "Only tokens can be checked"),
            )
        resolved = await self._resolve(credential)
        check = await self._tokens.check(credential, resolved)
        if check is not None and check.state is TokenState.expired:
            raise git_error(GitErrorCode.token_expired)
        if check is not None and check.state is TokenState.rejected:
            raise git_error(GitErrorCode.auth_failed)
        refreshed = await self._credentials.get(credential_id) or credential
        used_by = tuple((await self._usage.by_credential()).get(credential_id, ()))
        return CredentialCheckView(CredentialView(refreshed, used_by), resolved.info, check)

    async def _resolve(self, credential: GitCredential) -> ResolvedProvider:
        """У токена в хранилище нет порта и пути установки: берутся из настроек хоста, где сервер уже встречали."""
        known = next((item for item in self._settings.list() if item.host == credential.host), None)
        info = self._resolver.known(credential.host, known.port if known else None)
        api = known.detected.api_base if known and known.detected and known.detected.provider is info.id else None
        if api is not None and not api.startswith("https://"):
            # У токена нет адреса и согласия на http: запомненный по http корень API ему не подходит.
            api = None
        base = web_base(host=credential.host, port=known.port if known else None)
        ca_file = self._settings.trust_file(known.host, known.port) if known and known.has_trust else None
        return ResolvedProvider(info, api or api_base(info.id, host=credential.host, base=base), ca_file)
