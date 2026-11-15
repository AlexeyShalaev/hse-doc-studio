"""Включение раздела и право «Автор шаблонов» (docs/design/template-studio.md, D4 и 3.3).

- Раздел включён: переменная `HSE_STUDIO__PACK_STUDIO__ENABLED`, если задана (переключатель тогда только для чтения),
  иначе профиль standalone (D2), иначе сохранённый выбор: локально в Настройках, на сервере у админа установки.
- Право: локальному актору всегда; на сервере админу установки всегда, остальным по праву человеку или его группе.
  Гость по ссылке права не имеет никогда.
- Персональный токен (PAT) дополнительно должен нести область `packs`: токен только с `api` раздел не открывает,
  как `sign` не открывается правом `mcp`.
"""

from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.access.entities import Actor, ActorSource
from hse_doc_studio.core.identity.entities import TokenScope
from hse_doc_studio.core.pack_studio.entities import SectionState
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.protocols import IPackStudioGrantRepository, IPackStudioSectionStore


@dataclass(frozen=True)
class SectionView:
    enabled: bool
    # Включение задано окружением или профилем standalone: переключатель только для чтения.
    locked: bool
    # Этому человеку раздел открыт: включён и есть право.
    allowed: bool
    # Есть ли право само по себе (без учёта включения): интерфейс объясняет, чего не хватает.
    has_right: bool
    standalone: bool


class PackStudioAccess:
    def __init__(
        self,
        store: IPackStudioSectionStore,
        grants: IPackStudioGrantRepository | None,
        *,
        forced: bool | None,
        standalone: bool,
    ) -> None:
        self._store = store
        self._grants = grants
        self._forced = forced
        self._standalone = standalone

    async def section(self) -> SectionState:
        if self._forced is not None:
            return SectionState(enabled=self._forced, locked=True)
        if self._standalone:
            return SectionState(enabled=True, locked=True)
        return SectionState(enabled=bool(await self._store.get()), locked=False)

    async def has_right(self, actor: Actor) -> bool:
        if actor.is_local:
            return True
        if actor.is_guest or actor.id is None:
            return False
        if actor.is_instance_admin:
            return True
        return self._grants is not None and await self._grants.has_grant(actor.id)

    async def allowed(self, actor: Actor) -> bool:
        return (await self.section()).enabled and await self.has_right(actor)

    async def require(self, actor: Actor) -> None:
        """Гард раздела: выключен (404), токен без `packs` (403), нет права (403)."""
        if not (await self.section()).enabled:
            raise PackStudioError(PackStudioErrorCode.pack_studio_disabled)
        if actor.source is ActorSource.pat and TokenScope.packs.value not in actor.scopes:
            raise PackStudioError(PackStudioErrorCode.pack_scope_required)
        if not await self.has_right(actor):
            raise PackStudioError(PackStudioErrorCode.pack_studio_forbidden)

    async def view(self, actor: Actor) -> SectionView:
        section = await self.section()
        right = await self.has_right(actor)
        return SectionView(
            enabled=section.enabled,
            locked=section.locked,
            allowed=section.enabled and right,
            has_right=right,
            standalone=self._standalone,
        )

    async def set_enabled(self, actor: Actor, enabled: bool) -> SectionView:
        """Переключатель раздела. Сохранённый выбор меняет вызывающий слой с правом на это (Настройки локально,
        админка на сервере); здесь только запрет, если включение задано окружением."""
        if (await self.section()).locked:
            raise PackStudioError(PackStudioErrorCode.section_locked)
        await self._store.set(enabled)
        return await self.view(actor)
