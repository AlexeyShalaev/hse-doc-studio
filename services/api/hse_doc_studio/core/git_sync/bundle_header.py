"""Заголовок файла git bundle: что в нём лежит, прежде чем git его откроет.

Заголовок текстовый и стоит перед пакетом объектов: сигнатура, необязательные возможности (v3), предпосылки
(коммиты, которые должны уже быть в репозитории), ссылки и пустая строка. По нему видно, есть ли в файле
ветки и не нужна ли для него более ранняя история, ещё до запуска git.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

# Заголовок с сотнями веток укладывается в этот объём с запасом.
MAX_HEADER_BYTES: Final = 256 * 1024
_HEADS: Final = "refs/heads/"
_SIGNATURES: Final = frozenset({"# v2 git bundle", "# v3 git bundle"})
_SHA: Final = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class BundleHead:
    ref: str
    sha: str

    @property
    def branch(self) -> str | None:
        return self.ref.removeprefix(_HEADS) if self.ref.startswith(_HEADS) else None


@dataclass(frozen=True)
class BundleHeader:
    heads: tuple[BundleHead, ...]
    prerequisites: tuple[str, ...]
    # Возможности v3 вроде `object-format=sha256` или `filter=...`: Студия их не поддерживает.
    capabilities: tuple[str, ...]

    @property
    def branches(self) -> tuple[BundleHead, ...]:
        return tuple(head for head in self.heads if head.branch is not None)


def parse_bundle_header(data: bytes) -> BundleHeader | None:
    """None, если это не заголовок bundle или он оборван.

    `data` начинается с файла и может уходить в пакет объектов (двоичный): разбирается только текст до пустой строки.
    """
    end = data.find(b"\n\n")
    if end < 0:
        return None
    try:
        lines = data[:end].decode("utf-8").split("\n")
    except UnicodeDecodeError:
        return None
    if lines[0] not in _SIGNATURES:
        return None
    capabilities: list[str] = []
    prerequisites: list[str] = []
    heads: list[BundleHead] = []
    for line in lines[1:]:
        if not _take(line, capabilities, prerequisites, heads):
            return None
    return BundleHeader(tuple(heads), tuple(prerequisites), tuple(capabilities))


def _take(line: str, capabilities: list[str], prerequisites: list[str], heads: list[BundleHead]) -> bool:
    """Разбирает одну строку заголовка в нужный список; False, если строка не по формату."""
    if line.startswith("@"):
        capabilities.append(line[1:])
        return True
    required = line.startswith("-")
    sha, _, rest = line.removeprefix("-").partition(" ")
    if not _SHA.match(sha):
        return False
    if required:
        prerequisites.append(sha)
        return True
    if not rest:
        return False
    heads.append(BundleHead(rest, sha))
    return True
