from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from hse_doc_studio.core.paths import Mount, PathMapping


class PathNotInContainerMountError(ValueError):
    def __init__(self, path: Path, container_roots: Sequence[str]) -> None:
        roots = ", ".join(repr(r) for r in container_roots)
        super().__init__(
            f"path {path!s} is not inside any configured host mount ({roots}); "
            f"cannot translate to a host path for docker -v",
        )
        self.path = path
        self.container_roots = tuple(container_roots)


class HostPathResolver:
    """Переводит путь контейнера в путь хоста для монтирования в дочерний контейнер.

    docker-демон разрешает `-v <src>:<dst>` относительно ХОСТА, поэтому свой
    внутренний путь к каталогу проекта нужно вернуть в хостовые термины. Само
    соответствие живёт в домене (`PathMapping`) и общее с интерфейсом: файловый
    браузер и карточка проекта показывают пользователю те же хостовые пути.

    Пустое соответствие — нативный запуск: путь возвращается как есть, только с
    прямыми слэшами (единственная форма, которую docker принимает на любой ОС).
    """

    def __init__(self, mapping: PathMapping | None = None) -> None:
        self._mapping = mapping if mapping is not None else PathMapping()

    @classmethod
    def from_mounts(cls, mounts: Sequence[tuple[str, str]]) -> HostPathResolver:
        """Удобный конструктор из пар (корень в контейнере, корень на хосте)."""
        return cls(PathMapping([Mount(container=c, host=h) for c, h in mounts]))

    def to_host(self, path: Path) -> str:
        host = self._mapping.to_host(str(path))
        if host is None:
            raise PathNotInContainerMountError(path, [m.container for m in self._mapping.mounts])
        return host
