"""Персоны смотрящего для плана подписей: локально человек один, на сервере персона из членства в проекте."""

from __future__ import annotations

import asyncio
import contextlib

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.repositories import IProjectAclRepository
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import SigningIdentityKind
from hse_doc_studio.core.repositories import ISignatureRepository, ISigningIdentityRepository
from hse_doc_studio.core.signatures.errors import CmsParseError
from hse_doc_studio.core.signatures.plan import author_personas, grant_personas, slot_persona
from hse_doc_studio.infra.signatures.cms_inspector import describe_certificate


class LocalSignerScope:
    """Локально: авторы проекта и слоты, где на плашке указан один из ключей этой Студии (руководитель у себя)."""

    def __init__(self, signatures: ISignatureRepository, identities: ISigningIdentityRepository) -> None:
        self._signatures = signatures
        self._identities = identities

    async def personas(self, project: Project) -> frozenset[str]:
        state = await asyncio.to_thread(self._signatures.get_state, project.folder)
        expected = {
            sid: slot.signer.signer_id for sid, slot in state.slots.items() if slot.signer and slot.signer.signer_id
        }
        if not expected:
            return author_personas(project)
        mine = await self._own_signer_ids()
        return author_personas(project) | {
            slot_persona(sid) for sid, signer_id in expected.items() if signer_id in mine
        }

    def single_user(self) -> bool:
        return True

    async def _own_signer_ids(self) -> set[str]:
        ids: set[str] = set()
        for identity in await self._identities.list_all():
            if identity.kind is SigningIdentityKind.openpgp and identity.fingerprint:
                ids.add(identity.fingerprint)
                continue
            pem = await self._identities.read_cert(identity.id)
            if pem:
                with contextlib.suppress(CmsParseError):
                    ids.add(describe_certificate(pem).fingerprint_sha256)
        return ids


class ServerSignerScope:
    def __init__(self, acl: IProjectAclRepository) -> None:
        self._acl = acl

    async def personas(self, project: Project) -> frozenset[str]:
        actor = current_actor()
        if actor is None:
            return frozenset()
        if actor.is_local:
            return author_personas(project)
        loaded = await self._acl.load_for(actor, project.id)
        return grant_personas(project, loaded.grant_for(actor) if loaded is not None else None)

    def single_user(self) -> bool:
        actor = current_actor()
        return actor is not None and actor.is_local
