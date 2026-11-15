"""Что Студия шаблонов не даёт менять в рабочем пространстве (docs/design/template-studio.md, 4.5, D10).

Выпущенная версия неизменна: её каталог только для чтения, запись и удаление отвечают `version_released`. Реестр
выпусков `releases.yaml` через файлы не меняется (`releases_read_only`): его ведёт мастер «Новая версия» (T10), иначе
правка реестра снимала бы защиту версии. Удаление папки, в которой лежит выпущенная версия или реестр, тоже запрещено.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from hse_doc_studio.core.pack_studio.entities import ReleasedVersions
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.paths import TEMPLATES_DIR, VERSIONS_DIR, fold_path, is_registry_path


@dataclass(frozen=True)
class Protection:
    released: ReleasedVersions
    # Реестры выпусков, которые есть в рабочем пространстве (пути от папки паков).
    registries: tuple[str, ...] = ()

    def read_only_reason(self, path: str) -> PackStudioErrorCode | None:
        if is_registry_path(path):
            return PackStudioErrorCode.releases_read_only
        if self.released.released_dir_of(path) is not None:
            return PackStudioErrorCode.version_released
        return None

    def check_write(self, path: str) -> None:
        """Запись, правка или удаление одного файла."""
        reason = self.read_only_reason(path)
        if reason is PackStudioErrorCode.version_released:
            raise PackStudioError(reason, path=self.released.released_dir_of(path))
        if reason is not None:
            raise PackStudioError(reason, path=path)

    def check_delete_dir(self, path: str) -> None:
        """Удаление папки: она не должна быть выпущенной версией, лежать в ней или содержать её либо реестр."""
        self.check_write(path)
        prefix = fold_path(path) + "/"
        for released_dir in self._released_dirs():
            if released_dir.startswith(prefix):
                raise PackStudioError(PackStudioErrorCode.version_released, path=path)
        if any(fold_path(registry).startswith(prefix) for registry in self.registries):
            raise PackStudioError(PackStudioErrorCode.releases_read_only, path=path)

    def _released_dirs(self) -> Iterable[str]:
        for key, versions in self.released.templates.items():
            pack, _, template = key.partition("/")
            for version in versions:
                yield fold_path(f"{pack}/{TEMPLATES_DIR}/{template}/{VERSIONS_DIR}/{version}")
