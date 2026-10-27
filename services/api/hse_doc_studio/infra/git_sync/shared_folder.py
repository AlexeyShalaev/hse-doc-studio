"""Поиск папки проекта внутри каталога, который синхронизирует служба (Яндекс Диск, Dropbox, Syncthing...).

Хранилище `.hse-studio/git` внутри такой папки живёт под двумя движками синхронизации сразу: служба
может разнести по машинам наполовину записанные объекты и `index.lock`. Это только эвристика для
предупреждения, подключению и клонированию она не мешает.

Признаки: имя каталога-предка (по пути на машине пользователя: внутри контейнера оно ничего не
говорит, поэтому путь переводится через `PathMapping`) и служебные файлы службы в предке.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from hse_doc_studio.core.git_sync.entities import SharedFolderInfo, SharedFolderProvider
from hse_doc_studio.core.paths import PathMapping

_P = SharedFolderProvider

# Предков смотрим не глубже: дальше уже корень диска и домашние каталоги.
_MAX_ANCESTORS = 12
_MAX_EVIDENCE = 6

# Имя каталога-предка без учёта регистра. Служебное слово в начале имени и граница после него
# отсекают случайные `dropbox-notes`, но оставляют `Dropbox (Personal)` и `Yandex.Disk.localized`.
_NAME_RULES: tuple[tuple[SharedFolderProvider, re.Pattern[str]], ...] = (
    (_P.yandex_disk, re.compile(r"^(?:yandex[.\- _]?dis[ck]|яндекс[.\- _]?диск)(?:$|[\s.(])", re.IGNORECASE)),
    (_P.dropbox, re.compile(r"^dropbox(?:$|[\s(])", re.IGNORECASE)),
    (
        _P.google_drive,
        re.compile(
            r"^(?:google[ _-]?drive|googledrive-.+|my drive|мой диск|общие диски|shared drives)$", re.IGNORECASE
        ),
    ),
    (_P.onedrive, re.compile(r"^onedrive(?:$|[\s(_.-])", re.IGNORECASE)),
    (_P.icloud, re.compile(r"^(?:icloud[ _-]?drive|mobile documents|com~apple~clouddocs)$", re.IGNORECASE)),
    (_P.nextcloud, re.compile(r"^(?:nextcloud|owncloud)(?:$|[\s(])", re.IGNORECASE)),
    (
        _P.unknown,
        re.compile(r"^(?:pcloud(?:drive)?|mega(?:sync)?|sync\.com|resilio sync|synologydrive.*)$", re.IGNORECASE),
    ),
)

# Служебные записи в корне синхронизируемого каталога.
_MARKERS: tuple[tuple[str, SharedFolderProvider], ...] = (
    (".dropbox", _P.dropbox),
    (".dropbox.cache", _P.dropbox),
    (".stfolder", _P.syncthing),
    (".stignore", _P.syncthing),
    (".nextcloudsync.log", _P.nextcloud),
    (".owncloudsync.log", _P.nextcloud),
    (".sync", _P.yandex_disk),
)

# macOS держит облачные диски в ~/Library/CloudStorage/<служба>-<учётная запись>.
_CLOUD_STORAGE = ("Library", "CloudStorage")


@dataclass(frozen=True)
class _Hit:
    provider: SharedFolderProvider
    root: str
    evidence: str


class SharedFolderDetector:
    """Реализация `ISharedFolderDetector`. `paths` переводит пути контейнера в пути машины пользователя."""

    def __init__(self, paths: PathMapping | None = None) -> None:
        self._paths = paths if paths is not None else PathMapping()

    def detect(self, folder: Path) -> SharedFolderInfo | None:
        # Ссылка на папку внутри облака тоже в облаке, поэтому смотрим и сам путь, и его настоящее место.
        for candidate in _candidates(folder):
            info = self._detect_one(candidate)
            if info is not None:
                return info
        return None

    def _detect_one(self, folder: Path) -> SharedFolderInfo | None:
        # Имена читаем по пути пользователя: он длиннее пути в контейнере, выше корня маунта там пусто.
        host = PurePosixPath(self._host(folder))
        hits = [hit for ancestor in [host, *host.parents][:_MAX_ANCESTORS] for hit in _name_hits(str(ancestor))]
        # Служебные файлы видны только там, где есть сама файловая система.
        for ancestor in [folder, *folder.parents][:_MAX_ANCESTORS]:
            hits.extend(_marker_hits(ancestor, self._host(ancestor)))
        if not hits:
            return None
        # Ближайший к проекту признак называет службу, самый дальний из её признаков, корень синхронизации.
        nearest = max(hits, key=_depth)
        same = sorted((h for h in hits if h.provider is nearest.provider), key=_depth)
        evidence = tuple(dict.fromkeys(h.evidence for h in same))[:_MAX_EVIDENCE]
        return SharedFolderInfo(provider=nearest.provider, root=same[0].root, evidence=evidence)

    def _host(self, path: Path) -> str:
        return self._paths.to_host(str(path)) or str(path)


def _candidates(folder: Path) -> list[Path]:
    absolute = folder if folder.is_absolute() else Path.cwd() / folder
    try:
        real = absolute.resolve()
    except (OSError, RuntimeError):
        return [absolute]
    return [absolute] if real == absolute else [absolute, real]


def _depth(hit: _Hit) -> int:
    return len(PurePosixPath(hit.root).parts)


def _name_hits(host: str) -> list[_Hit]:
    path = PurePosixPath(host)
    if not path.name:
        return []
    names = [path.name]
    in_cloud_storage = (path.parent.parent.name, path.parent.name) == _CLOUD_STORAGE
    if in_cloud_storage:
        # Здесь имя `<служба>-<учётная запись>`: `Dropbox-Team`, `OneDrive-Personal`.
        names.append(path.name.split("-", 1)[0])
    for name in names:
        for provider, pattern in _NAME_RULES:
            if pattern.match(name):
                return [_Hit(provider, host, host)]
    return [_Hit(_P.unknown, host, host)] if in_cloud_storage else []


def _marker_hits(ancestor: Path, host: str) -> list[_Hit]:
    hits: list[_Hit] = []
    for marker, provider in _MARKERS:
        if _exists(ancestor / marker):
            hits.append(_Hit(provider, host, f"{host.rstrip('/')}/{marker}"))
    return hits


def _exists(path: Path) -> bool:
    try:
        return path.exists()
    except (OSError, ValueError):
        return False
