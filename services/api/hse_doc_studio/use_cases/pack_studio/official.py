"""Официальные паки (docs/design/template-studio.md, 4.7, срез T22).

Кнопка «Официальные паки» создаёт или открывает рабочее пространство над официальным репозиторием паков установки
(частичный клон только папки паков, D6). Вклад идёт только своим аккаунтом GitHub: токен человека, обычный поток T6
с форком в его аккаунт. Нет токена: интерфейс объясняет, какой выпустить. Бота установки и GitHub App нет (решение
владельца продукта: PR в официальные паки создают только люди).

Перед первой отправкой из официального пространства человек подтверждает, что вклад публичен и идёт под лицензией
репозитория (`license_accepted_at`).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.identity.protocols import IAuditLog
from hse_doc_studio.core.pack_studio.entities import PackWorkspace, WorkspaceKind
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.official import OfficialRepo
from hse_doc_studio.use_cases.pack_studio.workspaces import (
    CreateWorkspaceInput,
    PackWorkspaceService,
    WorkspaceView,
)

AUDIT_LICENSE = "pack_studio.official_license_accepted"
OFFICIAL_LABEL = "Официальные паки"


@dataclass(frozen=True)
class OfficialInfo:
    repo: OfficialRepo | None
    # Уже созданное официальное пространство человека: кнопка его открывает.
    workspace_id: UUID | None


def _now() -> datetime:
    return datetime.now(UTC)


class OfficialPacks:
    def __init__(
        self,
        repo: OfficialRepo | None,
        workspaces: PackWorkspaceService,
        *,
        audit: IAuditLog | None = None,
    ) -> None:
        self._repo = repo
        self._workspaces = workspaces
        self._audit = audit

    @property
    def repo(self) -> OfficialRepo | None:
        return self._repo

    # ── для людей ──

    async def info(self, actor: Actor) -> OfficialInfo:
        existing = await self._existing(actor) if self._repo is not None else None
        return OfficialInfo(repo=self._repo, workspace_id=existing)

    async def open(self, actor: Actor, credential_id: UUID) -> tuple[WorkspaceView, bool]:
        """Пространство над официальным репозиторием своим токеном: уже созданное или новое. Второе значение:
        создано ли сейчас."""
        repo = self._require_repo()
        existing = await self._existing(actor)
        if existing is not None:
            return await self._workspaces.get(actor, existing), False
        created = await self._workspaces.create(
            actor,
            CreateWorkspaceInput(
                kind=WorkspaceKind.git,
                label=OFFICIAL_LABEL,
                url=repo.url,
                credential_id=credential_id,
                base_branch=repo.base_branch,
                packs_path=repo.packs_path,
            ),
        )
        return created, True

    # ── для git рабочего пространства (PackGitService) ──

    def is_official(self, ws: PackWorkspace) -> bool:
        return self._repo is not None and self._repo.matches(ws.remote_url)

    async def accept_license(self, actor: Actor, ws: PackWorkspace, *, accepted: bool) -> PackWorkspace:
        """Согласие с лицензией перед первой отправкой из официального пространства (4.7)."""
        if not self.is_official(ws) or ws.license_accepted_at is not None:
            return ws
        repo = self._require_repo()
        if not accepted:
            raise PackStudioError(
                PackStudioErrorCode.license_consent_required,
                license=repo.license,
                license_url=repo.license_url,
                contributing_url=repo.contributing_url,
            )
        saved = await self._workspaces.save(replace(ws, license_accepted_at=_now()))
        if self._audit is not None:
            await self._audit.record(
                AUDIT_LICENSE,
                actor_id=actor.id,
                target=str(ws.id),
                details={"url": repo.url, "license": repo.license},
            )
        return saved

    # ── служебное ──

    def _require_repo(self) -> OfficialRepo:
        if self._repo is None:
            raise PackStudioError(PackStudioErrorCode.official_unavailable)
        return self._repo

    async def _existing(self, actor: Actor) -> UUID | None:
        views = await self._workspaces.list(actor)
        official = [v.workspace for v in views if self.is_official(v.workspace)]
        return max(official, key=lambda ws: ws.created_at).id if official else None
