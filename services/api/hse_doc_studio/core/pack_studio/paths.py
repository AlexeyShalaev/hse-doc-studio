"""Пути внутри папки паков рабочего пространства (docs/design/template-studio.md, раздел 9).

Путь приходит от клиента относительным к папке паков (`hse-cs-sse/templates/coursework/versions/2026.1.5/version.yaml`).
Здесь только строковая проверка: без `..`, абсолютных путей, обратных слешей, управляющих символов и служебных
папок git. Символьные ссылки на диске проверяет слой файлов (`infra/pack_studio/workspace_files.py`).

Раскладка пака (`docs/ru/reference/pack.md`): `<пак>/templates/<шаблон>/versions/<версия>/...`, реестр выпусков
`<пак>/templates/<шаблон>/releases.yaml`. Сравнение частей раскладки идёт без учёта регистра и в форме NFC:
на macOS и Windows `Versions/2026.1.5` и `versions/2026.1.5` это одна папка, и запрет на выпущенную версию не должен
обходиться регистром.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass

from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode

MAX_PATH_CHARS = 1024
MAX_SEGMENT_BYTES = 255
TEMPLATES_DIR = "templates"
VERSIONS_DIR = "versions"
RELEASES_FILE = "releases.yaml"
PACK_MANIFEST = "pack.yaml"
TEMPLATE_MANIFEST = "template.yaml"
VERSION_MANIFEST = "version.yaml"
YAML_SUFFIXES = (".yaml", ".yml")
# Служебные имена git: папка хранилища и файлы, которые git читает из дерева как настройки.
_GIT_NAMES = frozenset({".git", ".gitmodules"})


def _fold(segment: str) -> str:
    return unicodedata.normalize("NFC", segment).casefold()


def _bad_char(ch: str) -> bool:
    return ord(ch) < 0x20 or ord(ch) == 0x7F or ch in "\\" or unicodedata.category(ch) in {"Cc", "Cs"}


def _invalid() -> PackStudioError:
    return PackStudioError(PackStudioErrorCode.path_not_allowed)


def validate_rel_path(raw: str) -> str:
    """Нормализованный относительный путь (NFC, `/`) или `path_not_allowed`."""
    if not raw or len(raw) > MAX_PATH_CHARS or raw.startswith("/") or any(_bad_char(ch) for ch in raw):
        raise _invalid()
    text = unicodedata.normalize("NFC", raw)
    segments = text.split("/")
    for segment in segments:
        if segment in {"", ".", ".."} or len(segment.encode("utf-8")) > MAX_SEGMENT_BYTES:
            raise _invalid()
        if segment.strip() != segment or _fold(segment) in _GIT_NAMES:
            raise _invalid()
    return text


def validate_packs_path(raw: str) -> str:
    """Путь папки паков внутри репозитория; `.` значит корень репозитория."""
    text = raw.strip().strip("/")
    if text in {"", "."}:
        return "."
    return validate_rel_path(text)


@dataclass(frozen=True)
class VersionRef:
    """Версия шаблона, к которой относится путь; `rest` это путь внутри каталога версии (пусто: сам каталог)."""

    pack: str
    template: str
    version: str
    rest: str = ""

    @property
    def key(self) -> str:
        """Ключ шаблона в реестре выпущенных: `<пак>/<шаблон>` в свёрнутом регистре."""
        return template_key(self.pack, self.template)

    @property
    def dir(self) -> str:
        return f"{self.pack}/{TEMPLATES_DIR}/{self.template}/{VERSIONS_DIR}/{self.version}"


def template_key(pack: str, template: str) -> str:
    return f"{_fold(pack)}/{_fold(template)}"


def fold_path(path: str) -> str:
    """Путь для сравнения: NFC и без учёта регистра."""
    return "/".join(_fold(part) for part in path.split("/"))


def version_ref_of(path: str) -> VersionRef | None:
    """Версия шаблона, внутри которой лежит путь (или сам каталог версии); None для прочих путей."""
    parts = path.split("/")
    if len(parts) < 5 or _fold(parts[1]) != TEMPLATES_DIR or _fold(parts[3]) != VERSIONS_DIR:  # noqa: PLR2004
        return None
    return VersionRef(parts[0], parts[2], parts[4], "/".join(parts[5:]))


def is_registry_path(path: str) -> bool:
    """`<пак>/templates/<шаблон>/releases.yaml`: реестр выпусков шаблона."""
    parts = path.split("/")
    return len(parts) == 4 and _fold(parts[1]) == TEMPLATES_DIR and _fold(parts[3]) == RELEASES_FILE  # noqa: PLR2004


def is_yaml(path: str) -> bool:
    return path.lower().endswith(YAML_SUFFIXES)
