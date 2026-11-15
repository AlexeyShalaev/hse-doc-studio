"""Сетевой git и доступ к секретам Студии шаблонов одной связкой (срез T6).

Локально это те же запускатель, транспорт и доступ, что у синхронизации проектов. На сервере запускатель собирается
отдельно с доступом, который знает и служебные доступы репозиториев паков (`PackStudioCredentialAccess`): остальная
Студия по-прежнему видит только личные доступы.
"""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.git_sync.protocols import ICredentialAccess, IGitRemoteRunner, IGitTransport


@dataclass(frozen=True)
class PackGitPlumbing:
    runner: IGitRemoteRunner
    transport: IGitTransport
    access: ICredentialAccess
