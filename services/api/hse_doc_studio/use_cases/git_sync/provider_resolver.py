"""Какой это сервер и где у него API: подмена пользователя, имя хоста, ответ API.

Порядок задан каталогом провайдеров (core/git_sync/providers.py). Ответ API спрашивается только у тех хостов,
которых нет среди публичных (github.com, gitlab.com, codeberg.org, bitbucket.org): у них и версия, и корень API
известны заранее. Найденное запоминается в настройках хоста: статус проекта показывает провайдера и версию без сети.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from hse_doc_studio.core.git_sync.host_settings import GitHostSettings
from hse_doc_studio.core.git_sync.protocols import DetectionRequest, IGitHostSettingsRepository, IProviderDetector
from hse_doc_studio.core.git_sync.providers import (
    ApiDetection,
    DetectedBy,
    GitProvider,
    ProviderInfo,
    api_base,
    catalog,
    detect_provider,
    provider_spec,
    web_base,
)
from hse_doc_studio.core.git_sync.url import RemoteKind, RemoteUrl

# Порядок, в котором спрашиваем незнакомый сервер: самый вероятный для внутренних установок первым.
_GUESS_ORDER = (GitProvider.gitlab, GitProvider.gitea, GitProvider.github)


@dataclass(frozen=True)
class ResolvedProvider:
    info: ProviderInfo
    # Корень API для проверки токена; None, если его нельзя определить (Bitbucket не на bitbucket.org, other).
    api_base: str | None
    # Файл PEM со своим CA или закреплённым сертификатом этого сервера.
    ca_file: Path | None


def _saas_hosts() -> frozenset[str]:
    return frozenset(rule.value for spec in catalog().providers for rule in spec.host_rules if rule.match == "exact")


class ProviderResolver:
    def __init__(self, settings: IGitHostSettingsRepository, detector: IProviderDetector) -> None:
        self._settings = settings
        self._detector = detector

    def known(self, host: str | None, port: int | None) -> ProviderInfo:
        """Провайдер без сети: выбор пользователя, имя хоста, ответ API при прошлой проверке."""
        stored = self._settings.get(host, port) if host else None
        return self._decide(host, stored, None)

    async def resolve(self, url: RemoteUrl) -> ResolvedProvider:
        host = url.host
        stored = self._settings.get(host, url.port) if host else None
        ca_file = self._settings.trust_file(host, url.port) if host and stored and stored.has_trust else None
        found = await self._detect(url, stored, ca_file)
        if found is not None and host and (stored is None or stored.detected != found):
            self._settings.save((stored or GitHostSettings(host, url.port)).with_detection(found))
        info = self._decide(host, stored, found)
        return ResolvedProvider(
            info, self._api_base(url, info, found or (stored.detected if stored else None)), ca_file
        )

    async def _detect(
        self, url: RemoteUrl, stored: GitHostSettings | None, ca_file: Path | None
    ) -> ApiDetection | None:
        if url.host is None or url.kind not in {RemoteKind.https, RemoteKind.http} or url.host in _saas_hosts():
            return None
        providers = self._candidates(self._decide(url.host, stored, None))
        if not providers:
            return None
        segments = tuple(part for part in urlsplit(url.display_url).path.split("/") if part)
        return await self._detector.detect(
            DetectionRequest(
                secure=url.kind is RemoteKind.https,
                host=url.host,
                port=url.port,
                segments=segments,
                providers=providers,
                ca_file=ca_file,
            )
        )

    @staticmethod
    def _decide(host: str | None, stored: GitHostSettings | None, found: ApiDetection | None) -> ProviderInfo:
        overrides = {host: stored.provider_override} if host and stored and stored.provider_override else None
        return detect_provider(host, overrides=overrides, api=found or (stored.detected if stored else None))

    @staticmethod
    def _candidates(info: ProviderInfo) -> tuple[GitProvider, ...]:
        if info.detected_by in {DetectedBy.override, DetectedBy.host}:
            return (info.id,) if provider_spec(info.id).api.detect is not None else ()
        return _GUESS_ORDER

    @staticmethod
    def _api_base(url: RemoteUrl, info: ProviderInfo, detection: ApiDetection | None) -> str | None:
        if detection is not None and detection.provider is info.id and detection.api_base is not None:
            return detection.api_base
        base = web_base(host=url.host, port=url.port, secure=url.kind is not RemoteKind.http)
        return api_base(info.id, host=url.host, base=base)
