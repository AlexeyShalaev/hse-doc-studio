"""Проверка токена у сервера: чей он, какие у него права и до какого срока действует.

Если сервер ничего не сообщает (старая версия, точный токен GitHub, Bitbucket), вывод `unknown`, а не отказ:
годность токена тогда покажет сам git. Срок, который назвал сервер, запоминается в доступе, чтобы список
показывал «истекает через N дней» без сети.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from hse_doc_studio.core.git_sync.entities import (
    CredentialStatus,
    GitCredential,
    GitCredentialKind,
    TokenInfo,
    TokenState,
)
from hse_doc_studio.core.git_sync.protocols import IGitCredentialRepository, IntrospectionRequest, ITokenIntrospector
from hse_doc_studio.core.git_sync.providers import Sufficiency, assess_scopes, provider_spec
from hse_doc_studio.use_cases.git_sync.provider_resolver import ResolvedProvider


@dataclass(frozen=True)
class TokenCheck:
    state: TokenState
    # None, когда сервер не принял токен: рассказывать о нём нечего.
    info: TokenInfo | None


class TokenChecker:
    def __init__(self, introspector: ITokenIntrospector, credentials: IGitCredentialRepository) -> None:
        self._introspector = introspector
        self._credentials = credentials

    def supported(self, credential: GitCredential, resolved: ResolvedProvider) -> bool:
        return (
            credential.kind is GitCredentialKind.pat
            and provider_spec(resolved.info.id).introspection is not None
            and resolved.api_base is not None
        )

    async def check(self, credential: GitCredential, resolved: ResolvedProvider) -> TokenCheck | None:
        """None, если у провайдера нет способа проверить токен. Ошибки связи и сертификата идут исключением."""
        if not self.supported(credential, resolved) or resolved.api_base is None:
            return None
        result = await self._introspector.introspect(
            IntrospectionRequest(
                provider=resolved.info.id,
                api_base=resolved.api_base,
                token=self._credentials.get_secret(credential.id),
                ca_file=resolved.ca_file,
            )
        )
        self._remember(credential, result.state, result.expires_at)
        if result.state is TokenState.rejected:
            return TokenCheck(result.state, None)
        assessment = assess_scopes(resolved.info.id, result.scopes)
        info = TokenInfo(
            login=result.login,
            scopes=result.scopes or (),
            expires_at=result.expires_at,
            sufficiency=Sufficiency.unknown if result.state is not TokenState.valid else assessment.sufficiency,
            missing=assessment.missing if result.state is TokenState.valid else (),
        )
        return TokenCheck(result.state, info)

    def _remember(self, credential: GitCredential, state: TokenState, expires_at: datetime | None) -> None:
        if expires_at is not None and expires_at != credential.expires_at:
            self._credentials.update(replace(credential, expires_at=expires_at))
        if state in {TokenState.rejected, TokenState.expired}:
            self._credentials.mark(credential.id, CredentialStatus.auth_failed)
        elif state is TokenState.valid and credential.status is CredentialStatus.auth_failed:
            # Сервер подтвердил токен: прежний отказ был временным или токен заменили, значок «обновить доступ» лишний.
            self._credentials.mark(credential.id, CredentialStatus.ok)
