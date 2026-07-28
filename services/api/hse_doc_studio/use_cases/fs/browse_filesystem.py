from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.paths import PathMapping
from hse_doc_studio.core.repositories import BrowseEntry, IFilesystemBrowser


@dataclass
class BrowseFilesystemInput:
    path: str | None


@dataclass
class BrowseFilesystemOutput:
    path: Path
    parent: Path | None
    entries: list[BrowseEntry]
    # Текущий каталог — корень смонтированной папки пользователя. Клиент по
    # этому признаку и прячет «наверх», и разрешает подтвердить выбор сразу:
    # папка уже та, что нужна, требовать лишней навигации не за что.
    is_root: bool = False


class BrowseFilesystemUC:
    def __init__(self, browser: IFilesystemBrowser, paths: PathMapping | None = None) -> None:
        self._browser = browser
        self._paths = paths if paths is not None else PathMapping()

    def _default_root(self) -> Path:
        """С чего начинать обзор, когда путь не задан.

        Нативно это домашний каталог пользователя. В контейнере домашнего
        каталога у служебного пользователя нет вовсе, а показывать корень
        контейнера бессмысленно — там нет ни одного файла пользователя. Поэтому
        стартуем с первого смонтированного каталога: это и есть «его» файлы.
        """
        if self._paths:
            return Path(self._paths.mounts[0].container)
        return Path.home()

    def _clamp_to_mounts(self, target: Path) -> Path:
        """Не выпускать обзор за пределы смонтированных каталогов.

        Выше корня маунта лежит файловая система ОБРАЗА (`/app` с кодом и паком):
        показывать её пользователю бессмысленно, а созданный там проект исчез бы
        при первом обновлении версии. Запрошенное «наверх» из корня возвращаем в
        сам корень, а не отказываем: кнопка «наверх» — не ошибка пользователя.
        """
        if not self._paths:
            return target
        as_text = str(target).replace("\\", "/")
        for mount in self._paths.mounts:
            if as_text == mount.container or as_text.startswith(f"{mount.container}/"):
                return target
        return Path(self._paths.mounts[0].container)

    async def execute(self, inp: BrowseFilesystemInput) -> BrowseFilesystemOutput:
        target = (
            self._default_root()
            if inp.path is None or inp.path.strip() == ""
            else self._clamp_to_mounts(Path(inp.path).expanduser())
        )

        try:
            target = target.resolve(strict=False)
        except OSError as exc:
            raise FileNotFoundError(
                localized_error(f"Не удалось разрешить путь: '{inp.path}'", f"Cannot resolve path: '{inp.path}'")
            ) from exc

        # Browsing a not-yet-created path (the create wizard appends the future
        # project folder name to a picked/suggested parent) should land on its
        # nearest existing ancestor instead of 404-ing. Truly rootless paths
        # still fall through to the browser's FileNotFoundError.
        while not target.exists() and target.parent != target:
            target = target.parent

        parent, entries = self._browser.browse(target)
        is_root = self._paths.is_root(str(target))
        return BrowseFilesystemOutput(
            path=target,
            # В корне маунта «наверх» вести некуда — выше уже не файлы пользователя.
            parent=None if is_root else parent,
            entries=entries,
            is_root=is_root,
        )
