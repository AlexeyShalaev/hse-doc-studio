"""Базы обновления шаблона: запись для новых проектов, восстановление для старых.

База версии — чистый рендер этой версии шаблона для проекта, то, от чего
пользователь начинал править. Новый проект получает её сразу при создании
(`recorded`); поздняя материализация (NDA, новый автор, недостающие файлы
вариантов) дописывает в неё появившиеся файлы.

У проектов, созданных до этого механизма, базы нет, и первое планирование
обновления восстанавливает её:

* `root` — корневой коммит истории чистый (kind=init, тот же проект, тот же
  lock): рендерим версию с данными из `project.json` корня. Где файл корня
  отличается от рендера (проект сделан на dev-сборке с другим паком), базой
  служит содержимое корня — то, что Студия тогда действительно записала;
* `approximate` — чистого корня нет (история пересоздана при подключении, папку
  копировали без `.hse-studio/git`): рендер с текущими данными. Строки с
  вшитыми данными (ФИО, тема) могут дать ложные «правки» — лишние конфликты,
  но не потерю; предпросмотр об этом предупреждает.
"""

from __future__ import annotations

import re
from dataclasses import replace

import structlog

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import TemplateBaseProvenance
from hse_doc_studio.core.template_update.entities import TemplateBase
from hse_doc_studio.core.template_update.layout import dynamic_output_paths
from hse_doc_studio.core.template_update.protocols import ITemplateBaseStore, ITemplateTreeRenderer, RootSnapshot
from hse_doc_studio.core.vcs.protocols import IVcsService

logger = structlog.get_logger()

_INIT_KIND_RE = re.compile(r"^Hse-Kind:\s*init\s*$", re.MULTILINE)


class TemplateBaseService:
    def __init__(
        self,
        tree_renderer: ITemplateTreeRenderer,
        base_store: ITemplateBaseStore,
        vcs_service: IVcsService,
    ) -> None:
        self._renderer = tree_renderer
        self._store = base_store
        self._vcs = vcs_service

    def render(self, project: Project, version: TemplateVersion) -> dict[str, bytes]:
        """Чистый рендер версии для проекта без выходов dynamic include."""
        dynamic = dynamic_output_paths(project, version)
        return {path: data for path, data in self._renderer.render(project, version).items() if path not in dynamic}

    def _message(self, version: TemplateVersion, what: str) -> str:
        return f"{what}: {version.pack_id}/{version.template_id}@{version.version}"

    def record_initial(self, project: Project, version: TemplateVersion, preexisting: frozenset[str]) -> str | None:
        """База нового проекта: ровно то, что только что записало создание.

        Корневой коммит истории сделан сразу после рендера, поэтому база берётся из
        его дерева — без второго рендера. Исключаются служебное `.hse-studio/`,
        выходы dynamic include и файлы, лежавшие в папке до создания (`preexisting`:
        создание допускает скрытые файлы пользователя, например `.vscode/`).
        """
        if not self._vcs.is_initialized(project):
            return None
        dynamic = dynamic_output_paths(project, version)

        def keep(path: str) -> bool:
            return not path.startswith(".hse-studio/") and path not in dynamic and path not in preexisting

        return self._store.record_from_head(
            project, version.version, keep, message=self._message(version, "Чистый рендер шаблона")
        )

    def extend(self, project: Project, version: TemplateVersion) -> None:
        """После поздней материализации дописать в базу появившиеся файлы.

        Только если база уже есть: старому проекту её восстановит первое
        планирование обновления, а частичная база была бы хуже никакой.
        """
        if not self._vcs.is_initialized(project):
            return
        base = self._store.load(project, version.version)
        if base is None:
            return
        missing = {p: d for p, d in self.render(project, version).items() if p not in base.files}
        if not missing:
            return
        extended = replace(base, files={**base.files, **missing})
        self._store.save(project, extended, message=self._message(version, "Довключение файлов шаблона"))
        logger.info("template base extended", version=version.version, files=sorted(missing))

    def load_or_reconstruct(self, project: Project, version: TemplateVersion, *, persist: bool = True) -> TemplateBase:
        """База текущей версии проекта; при отсутствии — восстановленная.

        Файлы, которые шаблон пишет для проекта сейчас, но которых в базе нет
        (материализованы мимо хука), добираются рендером с текущими данными и
        помечаются приблизительными.
        """
        stored = self._store.load(project, version.version) if self._vcs.is_initialized(project) else None
        rendered = self.render(project, version)
        if stored is None:
            base = self._reconstruct(project, version, rendered)
            changed = True
        else:
            missing = {p: d for p, d in rendered.items() if p not in stored.files}
            base = stored
            changed = bool(missing)
            if missing:
                base = replace(
                    stored,
                    files={**stored.files, **missing},
                    approximate_paths=stored.approximate_paths | frozenset(missing),
                )
        if persist and changed and self._vcs.is_initialized(project):
            commit = self._store.save(project, base, message=self._message(version, "База обновления шаблона"))
            base = replace(base, commit=commit)
        return base

    def _reconstruct(self, project: Project, version: TemplateVersion, rendered: dict[str, bytes]) -> TemplateBase:
        root = self._store.root_snapshot(project) if self._vcs.is_initialized(project) else None
        root_project = _pristine_root_project(project, root)
        if root is None or root_project is None:
            logger.info("template base reconstructed approximately", project_id=str(project.id))
            return TemplateBase(
                version=version.version,
                files=rendered,
                provenance=TemplateBaseProvenance.approximate,
                approximate_paths=frozenset(rendered),
            )
        root_rendered = self.render(root_project, version)
        files: dict[str, bytes] = {}
        approximate: set[str] = set()
        for path in set(root_rendered) | set(rendered):
            if path in root.files:
                # Корень чистый: в нём то, что Студия действительно записала.
                files[path] = root.files[path]
            elif path in root_rendered:
                files[path] = root_rendered[path]
            else:
                # Появился позже (новый автор, NDA): данные того момента не знаем.
                files[path] = rendered[path]
                approximate.add(path)
        logger.info("template base reconstructed from the root commit", project_id=str(project.id))
        return TemplateBase(
            version=version.version,
            files=files,
            provenance=TemplateBaseProvenance.root,
            approximate_paths=frozenset(approximate),
        )


def _pristine_root_project(project: Project, root: RootSnapshot | None) -> Project | None:
    """Проект из корневого коммита, если корень — чистое создание этого проекта."""
    if root is None or root.project is None or not _INIT_KIND_RE.search(root.message):
        return None
    root_project = root.project
    same_lock = (
        root_project.lock.pack_id == project.lock.pack_id
        and root_project.lock.template_id == project.lock.template_id
        and root_project.lock.version == project.lock.version
    )
    if root_project.id != project.id or root_project.created_at != project.created_at or not same_lock:
        return None
    return root_project


def extend_template_base(base_service: TemplateBaseService | None, project: Project, version: TemplateVersion) -> None:
    """Дописать в базу обновления файлы, только что материализованные из пака (best-effort)."""
    if base_service is None:
        return
    try:
        base_service.extend(project, version)
    except Exception as exc:  # noqa: BLE001 — база нужна обновлению, но не этой операции
        logger.warning("template base not extended", project_id=str(project.id), exc=str(exc))
