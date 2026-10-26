"""Доступы к удалённым репозиториям: личные токены и ключи доступа ssh.

Секрет только входит (`Secret` в запросе) и сохраняется шифртекстом. Наружу из этих сценариев
он не выходит никогда: ни в ответе, ни в сообщении об ошибке, ни в журнале.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

import structlog

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.credentials import (
    normalize_credential_host,
    normalize_label,
    normalize_port,
    normalize_token,
    normalize_username,
    ssh_key_comment,
    token_family,
)
from hse_doc_studio.core.git_sync.entities import (
    CredentialStatus,
    CredentialUsage,
    GitCredential,
    GitCredentialKind,
)
from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.protocols import (
    IGitCredentialRepository,
    IGitCredentialUsage,
    ISecretCipher,
    ISshKeyGenerator,
)
from hse_doc_studio.core.git_sync.secret import KeySource, Secret
from hse_doc_studio.core.git_sync.url import DEFAULT_SSH_USER
from hse_doc_studio.core.i18n import localized_error

logger = structlog.get_logger()


@dataclass(frozen=True)
class CredentialView:
    credential: GitCredential
    used_by: tuple[CredentialUsage, ...] = ()


def _not_found() -> NotFoundError:
    return NotFoundError(localized_error("Доступ не найден", "Credential not found"))


class ListCredentialsUC:
    def __init__(self, repo: IGitCredentialRepository, usage: IGitCredentialUsage) -> None:
        self._repo = repo
        self._usage = usage

    async def execute(self) -> list[CredentialView]:
        used = self._usage.by_credential()
        return [CredentialView(c, tuple(used.get(c.id, ()))) for c in self._repo.list()]


@dataclass
class CreateCredentialInput:
    kind: GitCredentialKind
    label: str
    host: str
    username: str | None = None
    token: Secret | None = None
    port: int | None = None


class CreateCredentialUC:
    def __init__(self, repo: IGitCredentialRepository, key_generator: ISshKeyGenerator) -> None:
        self._repo = repo
        self._key_generator = key_generator

    async def execute(self, inp: CreateCredentialInput) -> CredentialView:
        label = normalize_label(inp.label)
        host = normalize_credential_host(inp.host)
        now = datetime.now(timezone.utc)
        if inp.kind is GitCredentialKind.pat:
            token = normalize_token(inp.token.reveal() if inp.token else "")
            credential = GitCredential(
                id=uuid4(),
                kind=inp.kind,
                label=label,
                host=host,
                username=normalize_username(inp.username),
                status=CredentialStatus.unverified,
                created_at=now,
                token_family=token_family(token.reveal()),
            )
            secret = token
        else:
            generated = self._key_generator.generate(ssh_key_comment(label))
            credential = GitCredential(
                id=uuid4(),
                kind=inp.kind,
                label=label,
                host=host,
                username=DEFAULT_SSH_USER,
                status=CredentialStatus.unverified,
                created_at=now,
                public_key=generated.public_key,
                fingerprint_sha256=generated.fingerprint_sha256,
                port=normalize_port(inp.port),
            )
            secret = generated.private_key
        self._repo.add(credential, secret)
        return CredentialView(credential)


@dataclass
class UpdateCredentialInput:
    credential_id: UUID
    label: str | None = None
    # None оставляет имя как есть, пустая строка очищает.
    username: str | None = None
    # None или пустая строка оставляют сохранённый токен.
    token: Secret | None = None


class UpdateCredentialUC:
    def __init__(self, repo: IGitCredentialRepository, usage: IGitCredentialUsage) -> None:
        self._repo = repo
        self._usage = usage

    async def execute(self, inp: UpdateCredentialInput) -> CredentialView:
        current = self._repo.get(inp.credential_id)
        if current is None:
            raise _not_found()
        changes: dict[str, object] = {}
        if inp.label is not None:
            changes["label"] = normalize_label(inp.label)
        if inp.username is not None:
            changes["username"] = normalize_username(inp.username)
        new_secret: Secret | None = None
        if inp.token is not None and inp.token.reveal().strip():
            if current.kind is not GitCredentialKind.pat:
                raise GitSyncError(
                    GitErrorCode.credential_invalid,
                    localized_error(
                        "У ключа доступа нет токена: его нельзя заменить",
                        "An access key has no token to replace",
                    ),
                )
            new_secret = normalize_token(inp.token.reveal())
            changes["token_family"] = token_family(new_secret.reveal())
            changes["status"] = CredentialStatus.unverified
        updated = replace(current, **changes)  # type: ignore[arg-type]
        self._repo.update(updated, new_secret)
        used = self._usage.by_credential().get(updated.id, ())
        return CredentialView(self._repo.get(updated.id) or updated, tuple(used))


@dataclass
class DeleteCredentialInput:
    credential_id: UUID
    force: bool = False


class DeleteCredentialUC:
    def __init__(self, repo: IGitCredentialRepository, usage: IGitCredentialUsage) -> None:
        self._repo = repo
        self._usage = usage

    async def execute(self, inp: DeleteCredentialInput) -> None:
        if self._repo.get(inp.credential_id) is None:
            raise _not_found()
        used = self._usage.by_credential().get(inp.credential_id, [])
        if used and not inp.force:
            raise GitSyncError(
                GitErrorCode.credential_in_use,
                localized_error(
                    "Доступ используют проекты: сначала отключите их или удалите доступ принудительно",
                    "Projects use this access: disconnect them first or delete it anyway",
                ),
                projects=[{"project_id": str(u.project_id), "name": u.name} for u in used],
            )
        self._repo.delete(inp.credential_id)


@dataclass(frozen=True)
class SecretsStatus:
    ok: bool
    source: KeySource
    permissions_enforced: bool
    credentials_total: int
    credentials_unreadable: int


class GetSecretsStatusUC:
    def __init__(self, cipher: ISecretCipher, repo: IGitCredentialRepository) -> None:
        self._cipher = cipher
        self._repo = repo

    async def execute(self) -> SecretsStatus:
        status = self._cipher.status()
        credentials = self._repo.list()
        unreadable = sum(1 for c in credentials if c.status is CredentialStatus.unreadable)
        return SecretsStatus(
            ok=status.available and unreadable == 0,
            source=status.source,
            permissions_enforced=status.permissions_enforced,
            credentials_total=len(credentials),
            credentials_unreadable=unreadable,
        )
