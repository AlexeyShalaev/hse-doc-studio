"""Доступ к секрету Студии шаблонов: личный доступ как раньше, служебный только своему репозиторию и с правом."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
from hse_doc_studio.core.access.context import current_actor, set_current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import CredentialStatus, GitCredential, GitCredentialKind
from hse_doc_studio.core.git_sync.secret import Secret
from hse_doc_studio.core.git_sync.url import RemoteUrl, parse_remote_url
from hse_doc_studio.core.pack_studio.git_flow import repo_key
from hse_doc_studio.core.pack_studio.protocols import ServiceAccess
from hse_doc_studio.infra.pack_studio.credential_access import AUDIT_SERVICE_USE, PackStudioCredentialAccess

PERSONAL = uuid4()
SERVICE = uuid4()
URL = "https://gitlab.example.org/fcs/packs.git"


class _Base:
    async def get(self, credential_id: UUID, *, project_id: UUID | None) -> GitCredential | None:
        if credential_id != PERSONAL:
            return None
        return GitCredential(
            id=PERSONAL,
            kind=GitCredentialKind.pat,
            label="мой",
            host="gitlab.example.org",
            username=None,
            status=CredentialStatus.ok,
            created_at=datetime.now(UTC),
        )

    async def get_secret(self, credential_id: UUID, *, project_id: UUID | None, remote: RemoteUrl) -> Secret:
        return Secret("personal")


class _Service:
    access = ServiceAccess(
        id=SERVICE,
        url=URL,
        host="gitlab.example.org",
        port=None,
        repo_key=repo_key("gitlab.example.org", None, "fcs/packs"),
        label="fcs/packs",
        created_at=datetime.now(UTC),
        token_family="glpat",
    )

    async def get(self, access_id: UUID) -> ServiceAccess | None:
        return self.access if access_id == SERVICE else None

    async def secret(self, access_id: UUID) -> Secret | None:
        return Secret("service") if access_id == SERVICE else None


class _Grants:
    def __init__(self, allowed: set[str]) -> None:
        self.allowed = allowed

    async def has_grant(self, user_id: str) -> bool:
        return user_id in self.allowed


class _Audit:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def record(self, action: str, **kwargs: Any) -> None:
        self.events.append((action, kwargs))


@pytest.fixture
def actor() -> Iterator[None]:
    saved = current_actor()
    set_current_actor(Actor.user("anna", "Анна"))
    yield
    set_current_actor(saved)


def _access(allowed: set[str] | None = None) -> tuple[PackStudioCredentialAccess, _Audit]:
    audit = _Audit()
    return PackStudioCredentialAccess(
        _Base(), _Service(), _Grants({"anna"} if allowed is None else allowed), audit
    ), audit  # type: ignore[arg-type]


@pytest.mark.usefixtures("actor")
async def test__personal_credential__goes_through_the_base_access() -> None:
    access, audit = _access()

    secret = await access.get_secret(PERSONAL, project_id=None, remote=parse_remote_url(URL))

    assert secret.reveal() == "personal"
    assert audit.events == []


@pytest.mark.usefixtures("actor")
async def test__service_access__for_its_repository__given_and_audited() -> None:
    access, audit = _access()

    credential = await access.get(SERVICE, project_id=None)
    secret = await access.get_secret(
        SERVICE, project_id=None, remote=parse_remote_url("https://GitLab.example.org/FCS/packs")
    )

    assert credential is not None
    assert (credential.kind, credential.host) == (GitCredentialKind.pat, "gitlab.example.org")
    assert secret.reveal() == "service"
    ((action, details),) = audit.events
    assert action == AUDIT_SERVICE_USE
    assert details["actor_id"] == "anna"
    assert "service" not in str(details)


@pytest.mark.usefixtures("actor")
async def test__service_access__other_repository_or_fork__not_found() -> None:
    access, _ = _access()

    with pytest.raises(NotFoundError):
        await access.get_secret(
            SERVICE, project_id=None, remote=parse_remote_url("https://gitlab.example.org/anna/packs.git")
        )


@pytest.mark.usefixtures("actor")
async def test__service_access__person_without_the_right__does_not_see_it() -> None:
    access, _ = _access(allowed=set())

    assert await access.get(SERVICE, project_id=None) is None
    with pytest.raises(NotFoundError):
        await access.get_secret(SERVICE, project_id=None, remote=parse_remote_url(URL))


async def test__service_access__no_actor_or_guest__does_not_see_it() -> None:
    access, _ = _access()
    saved = current_actor()
    try:
        set_current_actor(None)
        assert await access.get(SERVICE, project_id=None) is None
        set_current_actor(Actor.guest("gs_1"))
        assert await access.get(SERVICE, project_id=None) is None
        set_current_actor(Actor.user("boss", is_instance_admin=True))
        assert await access.get(SERVICE, project_id=None) is not None
    finally:
        set_current_actor(saved)
