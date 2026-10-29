"""Проверка адреса ИИ-провайдера политикой исходящих запросов (SSRF) до сохранения и перед обращением."""

from __future__ import annotations

from urllib.parse import urlsplit

from hse_doc_studio.core.egress import EgressBlockedError, EgressPurpose, IEgressPolicy
from hse_doc_studio.core.enums import AIProviderOwnerKind
from hse_doc_studio.core.i18n import localized_error


async def authorize_base_url(egress: IEgressPolicy | None, base_url: str, owner_kind: AIProviderOwnerKind) -> None:
    """Пустой адрес это хост SDK по умолчанию. Адрес личного провайдера проверяется строго, общего (его задал
    админ, например Ollama в локальной сети) мягче. Имя, которое не разрешилось, не блокируется: провайдер
    просто не ответит."""
    if egress is None or not base_url:
        return
    parts = urlsplit(base_url)
    try:
        host = parts.hostname
        port = parts.port
    except ValueError:
        host, port = None, None
    if parts.scheme not in ("http", "https") or not host:
        raise ValueError(
            localized_error(
                "Адрес провайдера должен быть http:// или https:// URL",
                "Provider URL must be an http:// or https:// URL",
            )
        )
    purpose = EgressPurpose.admin if owner_kind is AIProviderOwnerKind.instance else EgressPurpose.user
    try:
        await egress.authorize(host, port, purpose=purpose)
    except EgressBlockedError:
        raise ValueError(
            localized_error(
                "Адрес провайдера недоступен: внутренние адреса сервера запрещены",
                "Provider URL is not allowed: internal server addresses are blocked",
            )
        ) from None
    except OSError:
        return
