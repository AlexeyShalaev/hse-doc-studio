"""Проверка адреса git-сервера политикой исходящих запросов (SSRF) перед любым обращением к сети."""

from __future__ import annotations

from hse_doc_studio.core.egress import EgressBlockedError, IEgressPolicy
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError


def egress_error() -> GitSyncError:
    return git_error(GitErrorCode.egress_blocked)


async def authorize_git_host(egress: IEgressPolicy | None, host: str | None, port: int | None) -> None:
    """Закрытый адрес даёт egress_blocked. Имя, которое не разрешилось, не ошибка политики: git сам скажет offline."""
    if egress is None or host is None:
        return
    try:
        await egress.authorize(host, port)
    except EgressBlockedError:
        raise egress_error() from None
    except OSError:
        return
