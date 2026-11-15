"""«Применить» и выключение источника над хранилищем `packs-store` (порт ICatalogStore, template-studio.md, 10.3).

Запись идёт под замком хранилища. Сначала версии кладутся в хранилище по дайджесту (существующие ключи не
трогаются), потом `catalog.json` заменяется одним переименованием с новой ревизией. Упавшее посередине применение
оставляет в хранилище лишние каталоги, но не меняет каталог: следующее применение их переиспользует.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

import structlog

from hse_doc_studio.core.catalog import PackOrigin, PackOriginKind
from hse_doc_studio.core.pack_catalog.entities import CatalogSource
from hse_doc_studio.core.pack_catalog.errors import CatalogError, CatalogErrorCode
from hse_doc_studio.core.pack_catalog.plan import Blocker, CatalogPlan, PlannedPack
from hse_doc_studio.core.pack_catalog.protocols import AppliedPacks, ICatalogReloader
from hse_doc_studio.core.pack_catalog.store import CatalogState, StoredPack, StoredTemplate, StoredVersion
from hse_doc_studio.infra.pack_catalog.store import PacksStore, StoreIntegrityError, StoreLockTimeoutError

logger = structlog.get_logger()

PACK_MANIFEST = "pack.yaml"
TEMPLATE_MANIFEST = "template.yaml"


def origin_of(source: CatalogSource, *, revision: str | None, replaces_builtin: bool) -> PackOrigin:
    return PackOrigin(
        kind=PackOriginKind.subscribed,
        source_id=str(source.id),
        source_kind=source.kind.value,
        label=source.label,
        url=source.url,
        ref=source.ref,
        revision=revision,
        replaces_builtin=replaces_builtin,
    )


class FsCatalogStore:
    def __init__(self, store: PacksStore, reloader: ICatalogReloader | None = None) -> None:
        self._store = store
        self._reloader = reloader

    def state(self) -> CatalogState:
        return self._store.read()

    def apply(self, source: CatalogSource, plan: CatalogPlan, root: Path) -> AppliedPacks:
        if not plan.ok:
            raise CatalogError(CatalogErrorCode.plan_blocked, blockers=[b.value for b in plan.blockers])
        try:
            with self._store.locked():
                state = self._store.read()
                _verify(state, plan)
                added: list[str] = []
                packs: list[StoredPack] = []
                for pack in plan.packs:
                    stored = self._store_pack(source, plan.revision, pack, root, state, added)
                    if stored is not None:
                        packs.append(stored)
                written = {p.id for p in packs}
                # Пак, который источник больше не несёт, остаётся для проектов, но мастер его не предлагает.
                kept = [
                    replace(p, listed=False) if p.source_id == str(source.id) else p
                    for p in state.packs
                    if p.id not in written
                ]
                new_state = CatalogState(
                    revision=state.revision + 1, updated_at=_now(), packs=tuple(_ordered(state, kept + packs))
                )
                self._store.write(new_state)
        except StoreLockTimeoutError:
            raise CatalogError(CatalogErrorCode.catalog_busy) from None
        except StoreIntegrityError as exc:
            raise CatalogError(CatalogErrorCode.revision_moved, reason=str(exc)) from exc
        self._reload()
        logger.info("pack catalog applied", source=str(source.id), revision=new_state.revision, added=len(added))
        return AppliedPacks(state=new_state, added=tuple(added))

    def set_listed(self, source_id: str, *, listed: bool, origin_label: str | None = None) -> CatalogState:
        try:
            with self._store.locked():
                state = self._store.read()
                packs = tuple(
                    replace(
                        p,
                        listed=listed,
                        origin=replace(p.origin, label=origin_label) if origin_label is not None else p.origin,
                    )
                    if p.source_id == source_id
                    else p
                    for p in state.packs
                )
                if packs == state.packs:
                    return state
                new_state = CatalogState(revision=state.revision + 1, updated_at=_now(), packs=packs)
                self._store.write(new_state)
        except StoreLockTimeoutError:
            raise CatalogError(CatalogErrorCode.catalog_busy) from None
        self._reload()
        return new_state

    def _store_pack(  # noqa: PLR0913 — пак плана и всё, что нужно для его записи
        self,
        source: CatalogSource,
        revision: str,
        pack: PlannedPack,
        root: Path,
        state: CatalogState,
        added: list[str],
    ) -> StoredPack | None:
        stored_versions = [v for v in pack.versions if v.stored and v.digest is not None]
        previous = state.pack(pack.id)
        if not stored_versions and previous is None:
            return None  # ни одной версии для этой Студии: пак в каталог пока не попадает
        pack_dir = root / pack.path
        meta = self._store.put_meta(pack.id, None, PACK_MANIFEST, (pack_dir / PACK_MANIFEST).read_bytes())
        # Прежние версии пака остаются (проекты на них закреплены), но мастер предлагает только версии ревизии.
        templates: dict[str, tuple[str, dict[str, StoredVersion]]] = {
            tpl.id: (tpl.meta, {v.version: replace(v, listed=False) for v in tpl.versions})
            for tpl in (previous.templates if previous is not None else ())
        }
        for version in stored_versions:
            template_dir = pack_dir / "templates" / version.template
            tpl_meta = self._store.put_meta(
                pack.id, version.template, TEMPLATE_MANIFEST, (template_dir / TEMPLATE_MANIFEST).read_bytes()
            )
            _, versions = templates.get(version.template, (tpl_meta, {}))
            digest = version.digest or ""
            known = state.stored_digest(pack.id, version.template, version.version) is not None
            existed = known or self._store.has_version(pack.id, version.template, version.version, digest)
            rel = self._store.put_version(
                template_dir / "versions" / version.version, pack.id, version.template, version.version, digest
            )
            if not known:
                added.append(f"{pack.id}/{version.template}@{version.version}")
            if not existed:
                logger.info("pack version stored", pack=pack.id, template=version.template, version=version.version)
            versions[version.version] = StoredVersion(
                version=version.version, digest=digest, dir=rel, kind=version.kind, listed=True
            )
            templates[version.template] = (tpl_meta, versions)
        return StoredPack(
            id=pack.id,
            meta=meta,
            source_id=str(source.id),
            origin=origin_of(source, revision=revision, replaces_builtin=pack.replaces_builtin),
            templates=tuple(
                StoredTemplate(id=tpl_id, meta=tpl_meta, versions=tuple(versions[v] for v in sorted(versions)))
                for tpl_id, (tpl_meta, versions) in sorted(templates.items())
            ),
            listed=source.enabled,
        )

    def _reload(self) -> None:
        if self._reloader is not None:
            self._reloader.reload()


def _verify(state: CatalogState, plan: CatalogPlan) -> None:
    """Свежий каталог под замком: версия, которую план считает новой или той же, не появилась с другим дайджестом."""
    for pack in plan.packs:
        for version in pack.versions:
            if not version.stored:
                continue
            current = state.stored_digest(pack.id, version.template, version.version)
            if current is not None and current != version.digest:
                raise CatalogError(CatalogErrorCode.plan_blocked, blockers=[Blocker.version_changed.value])


def _ordered(state: CatalogState, packs: list[StoredPack]) -> list[StoredPack]:
    """Прежний порядок паков каталога, новые в конце."""
    position = {p.id: i for i, p in enumerate(state.packs)}
    return sorted(packs, key=lambda p: (position.get(p.id, len(position)), p.id))


def _now() -> str:
    return datetime.now(UTC).isoformat()
