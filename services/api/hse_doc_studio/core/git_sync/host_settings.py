"""Настройки git-сервера, общие для всех проектов: подмена провайдера, свой CA, закреплённый сертификат.

Секретов здесь нет: сертификаты публичны. Права на файлы всё равно такие же, как у доступов, потому что
доверие к чужому сертификату меняет, кому Студия отдаёт токены.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from hse_doc_studio.core.git_sync.providers import ApiDetection, GitProvider

DEFAULT_HTTPS_PORT = 443


def host_settings_key(host: str, port: int | None) -> str:
    """Имя записи: `host` или `host:port`, хост уже в нижнем регистре; порт https по умолчанию это отсутствие порта."""
    return f"{host}:{port}" if port and port != DEFAULT_HTTPS_PORT else host


@dataclass(frozen=True)
class GitHostSettings:
    host: str
    port: int | None = None
    provider_override: GitProvider | None = None
    # Сертификаты центров выдачи, которым Студия верит для этого сервера; уже нормализованный PEM.
    ca_pem: str | None = None
    # Закреплённый сертификат сервера: отпечаток, который подтвердил человек, и сам сертификат.
    pinned_fingerprint: str | None = None
    pinned_pem: str | None = None
    # Последний ответ API сервера: кэш для версии и корня API, человек его не задаёт.
    detected: ApiDetection | None = None

    @property
    def key(self) -> str:
        return host_settings_key(self.host, self.port)

    @property
    def has_trust(self) -> bool:
        return self.ca_pem is not None or self.pinned_pem is not None

    @property
    def is_empty(self) -> bool:
        return self.provider_override is None and not self.has_trust and self.detected is None

    def with_detection(self, detected: ApiDetection | None) -> GitHostSettings:
        return replace(self, detected=detected)
