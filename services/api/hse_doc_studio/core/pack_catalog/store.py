"""Состояние хранилища подключённых паков: что сейчас в каталоге Студии сверх вшитых паков.

Хранилище `data_dir/packs-store/` только дописывается: каталог версии лежит по ключу с дайджестом
(`<пак>/<шаблон>/<версия>@<hex>/`) и никогда не удаляется и не меняется, манифесты пака и шаблона лежат рядом по
хешу содержимого. Какие из них сейчас в каталоге, говорит `catalog.json` (`CatalogState`): его заменяет только
«Применить», атомарно, с ростом `revision`. Каждый процесс api замечает новую ревизию по файлу и перечитывает
каталог сам, без рестарта.

Здесь только модель и правила имён; чтение и запись диска живут в `infra.pack_catalog.store`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from hse_doc_studio.core.catalog import PackOrigin

CATALOG_FORMAT = 1
DIGEST_PREFIX = "sha256:"
# Id пака и шаблона и номер версии становятся частью пути в хранилище: только безопасные имена.
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
_HEX_RE = re.compile(r"^[0-9a-f]{64}$")


# Имена файлов самого хранилища в его корне: пак так называться не может.
_RESERVED = frozenset({"catalog.json"})


def is_store_name(value: str) -> bool:
    """Имя годится в путь хранилища: латиница, цифры, точка, дефис, подчёркивание; начинается с буквы или цифры
    (служебные папки хранилища начинаются с точки) и не совпадает с его файлами."""
    return bool(_NAME_RE.fullmatch(value)) and value.lower() not in _RESERVED


def digest_hex(digest: str) -> str | None:
    """Шестнадцатеричная часть дайджеста `sha256:<64 hex>`; None, если дайджест не такой."""
    if not digest.startswith(DIGEST_PREFIX):
        return None
    hex_part = digest[len(DIGEST_PREFIX) :]
    return hex_part if _HEX_RE.fullmatch(hex_part) else None


def version_store_path(pack: str, template: str, version: str, digest: str) -> str:
    """Путь каталога версии от корня хранилища: `<пак>/<шаблон>/<версия>@<hex>`."""
    hex_part = digest_hex(digest)
    if hex_part is None or not all(is_store_name(part) for part in (pack, template, version)):
        raise ValueError(f"недопустимый ключ хранилища: {pack}/{template}/{version} {digest}")
    return f"{pack}/{template}/{version}@{hex_part}"


@dataclass(frozen=True)
class StoredVersion:
    version: str
    digest: str
    # Каталог версии от корня хранилища.
    dir: str
    # Класс выпуска из `releases.yaml` источника (`patch`, `minor`, `major`) или None.
    kind: str | None = None
    # False: версия есть для существующих проектов, но источник её больше не несёт; мастер её не предлагает.
    listed: bool = True


@dataclass(frozen=True)
class StoredTemplate:
    id: str
    # `template.yaml` в хранилище (от корня), снятый с применённой ревизии источника.
    meta: str
    versions: tuple[StoredVersion, ...] = ()


@dataclass(frozen=True)
class StoredPack:
    id: str
    # `pack.yaml` в хранилище (от корня).
    meta: str
    source_id: str
    origin: PackOrigin
    templates: tuple[StoredTemplate, ...] = ()
    # False: источник отключён или удалён; пак остаётся для проектов, но мастер его не предлагает.
    listed: bool = True

    @property
    def replace_builtin(self) -> bool:
        return self.origin.replaces_builtin


@dataclass(frozen=True)
class CatalogState:
    revision: int = 0
    updated_at: str | None = None
    packs: tuple[StoredPack, ...] = field(default_factory=tuple)

    def pack(self, pack_id: str) -> StoredPack | None:
        return next((p for p in self.packs if p.id == pack_id), None)

    def stored_digest(self, pack: str, template: str, version: str) -> str | None:
        stored = self.pack(pack)
        if stored is None:
            return None
        tpl = next((t for t in stored.templates if t.id == template), None)
        if tpl is None:
            return None
        return next((v.digest for v in tpl.versions if v.version == version), None)

    def packs_of(self, source_id: str) -> tuple[StoredPack, ...]:
        return tuple(p for p in self.packs if p.source_id == source_id)
