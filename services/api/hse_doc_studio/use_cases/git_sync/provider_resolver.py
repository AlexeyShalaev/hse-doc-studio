"""Какой это сервер и где у него API: подмена пользователя, имя хоста, ответ API.

Порядок задан каталогом провайдеров (core/git_sync/providers.py). Ответ API спрашивается только у тех хостов,
которых нет среди публичных (github.com, gitlab.com, codeberg.org, bitbucket.org): у них и версия, и корень API
известны заранее. Найденное запоминается в настройках хоста: статус проекта показывает провайдера и версию без сети.

Запомненный ответ стареет: сервер обновляют, а проверка шла один раз, при подключении. Поэтому удачная выборка или
синхронизация освежает его (`refresh`), но не чаще раза в `PROVIDER_REFRESH_S` на хост: у десятков проектов одного
сервера один общий ответ.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

import structlog

from hse_doc_studio.core.git_sync.host_settings import GitHostSettings, host_settings_key
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

logger = structlog.get_logger()

# Как долго запомненный ответ API (версия сервера) считается свежим после последней проверки.
PROVIDER_REFRESH_S = 15 * 60

# Порядок, в котором спрашиваем незнакомый сервер: самый вероятный для внутренних установок первым.
_GUESS_ORDER = (GitProvider.gitlab, GitProvider.gitea, GitProvider.github)
# Локальная Студия узнаёт и сервер HSE Doc Studio (`/git/-/info`); сам сервер с собой не синхронизируется.
LOCAL_GUESS_ORDER = (GitProvider.hse_studio, *_GUESS_ORDER)


@dataclass(frozen=True)
class ResolvedProvider:
    info: ProviderInfo
    # Корень API для проверки токена; None, если его нельзя определить (Bitbucket не на bitbucket.org, other).
    api_base: str | None
    # Файл PEM со своим CA или закреплённым сертификатом этого сервера.
    ca_file: Path | None


class ProviderRefreshBook:
    """Когда ответ API хоста освежали в последний раз. Общий на процесс: кнопка и фоновая выборка видят одно."""

    def __init__(self, interval_s: float = PROVIDER_REFRESH_S, clock: Callable[[], float] = time.monotonic) -> None:
        self._interval_s = interval_s
        self._clock = clock
        self._last: dict[str, float] = {}

    def take(self, key: str) -> bool:
        """Пора ли спросить хост снова. Отметка ставится сразу: параллельные выборки второй раз его не спросят."""
        now = self._clock()
        last = self._last.get(key)
        if last is not None and now - last < self._interval_s:
            return False
        self._last[key] = now
        return True


def _saas_hosts() -> frozenset[str]:
    return frozenset(rule.value for spec in catalog().providers for rule in spec.host_rules if rule.match == "exact")


class ProviderResolver:
    def __init__(
        self,
        settings: IGitHostSettingsRepository,
        detector: IProviderDetector,
        guess_order: tuple[GitProvider, ...] = _GUESS_ORDER,
        refresh_book: ProviderRefreshBook | None = None,
    ) -> None:
        self._settings = settings
        self._detector = detector
        self._guess_order = guess_order
        self._refresh_book = refresh_book

    async def known(self, host: str | None, port: int | None) -> ProviderInfo:
        """Провайдер без сети: выбор пользователя, имя хоста, ответ API при прошлой проверке."""
        stored = await self._settings.get(host, port) if host else None
        return self._decide(host, stored, None)

    async def refresh(self, url: RemoteUrl) -> None:
        """Освежить запомненный ответ API хоста после удачной связи с ним (выборка, синхронизация).

        Спрашиваем только хост, чей ответ уже запомнен: незнакомый сервер так не начнут перебирать каждые четверть
        часа. Сбой проверки ничего не портит: остаётся прежний ответ, статус покажет его.
        """
        host = url.host
        if self._refresh_book is None or host is None or url.kind not in {RemoteKind.https, RemoteKind.http}:
            return
        try:
            stored = await self._settings.get(host, url.port)
            if stored is None or stored.detected is None:
                return
            if not self._refresh_book.take(host_settings_key(host, url.port)):
                return
            await self.resolve(url)
        except Exception:  # noqa: BLE001 — сведения о сервере вторичны: выборка уже удалась
            logger.info("git provider refresh failed", host=host, exc_info=True)

    async def resolve(self, url: RemoteUrl) -> ResolvedProvider:
        host = url.host
        stored = await self._settings.get(host, url.port) if host else None
        if stored is not None and stored.has_trust:
            await self._settings.materialize()
        ca_file = self._settings.trust_file(host, url.port) if host and stored and stored.has_trust else None
        found = await self._detect(url, stored, ca_file)
        if found is not None and host and (stored is None or stored.detected != found):
            await self._settings.save((stored or GitHostSettings(host, url.port)).with_detection(found))
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

    def _candidates(self, info: ProviderInfo) -> tuple[GitProvider, ...]:
        if info.detected_by in {DetectedBy.override, DetectedBy.host}:
            return (info.id,) if provider_spec(info.id).api.detect is not None else ()
        return self._guess_order

    @staticmethod
    def _api_base(url: RemoteUrl, info: ProviderInfo, detection: ApiDetection | None) -> str | None:
        if detection is not None and detection.provider is info.id and detection.api_base is not None:
            # Настройки хоста не знают схемы: http-корень, найденный пробой по http, не годится для https-адреса,
            # иначе токен ушёл бы открытым текстом туда, куда человек этого не разрешал.
            expected = "http://" if url.kind is RemoteKind.http else "https://"
            if detection.api_base.startswith(expected):
                return detection.api_base
        base = web_base(host=url.host, port=url.port, secure=url.kind is not RemoteKind.http)
        return api_base(info.id, host=url.host, base=base)
