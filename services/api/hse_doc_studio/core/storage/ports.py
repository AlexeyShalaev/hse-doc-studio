from __future__ import annotations

from collections.abc import AsyncIterator, Collection
from typing import BinaryIO, Protocol

from hse_doc_studio.core.storage.models import BlobInfo, ObjectInfo, PresignedUrl

ObjectSource = bytes | BinaryIO
"""Источник данных: байты или перематываемый двоичный файл (читается от текущей позиции до конца)."""

ByteRange = tuple[int, int | None]
"""Диапазон `(начало, конец включительно)`; конец None означает до конца объекта."""


class IObjectStore(Protocol):
    async def put(
        self,
        key: str,
        source: ObjectSource,
        *,
        content_type: str | None = None,
        sha256: str | None = None,
    ) -> ObjectInfo:
        """Записывает объект целиком (перезаписывает). Заявленный sha256 сверяется до записи:
        при расхождении ChecksumMismatchError и в хранилище ничего нет; сверх предела размера ObjectTooLargeError."""
        ...

    async def get(self, key: str, *, byte_range: ByteRange | None = None) -> bytes:
        """Содержимое или его часть; нет объекта это ObjectNotFoundError."""
        ...

    def stream(self, key: str, *, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]:
        """Содержимое кусками; нет объекта это ObjectNotFoundError при первом чтении."""
        ...

    async def head(self, key: str) -> ObjectInfo | None: ...

    async def delete(self, key: str) -> None:
        """Удаляет объект; отсутствие ключа не ошибка."""
        ...

    async def list_objects(self, prefix: str = "") -> list[ObjectInfo]:
        """Все объекты, ключ которых начинается с prefix, по возрастанию ключа."""
        ...

    async def presign_get(self, key: str, *, expires_in_s: int = 300) -> PresignedUrl | None:
        """Ссылка на чтение с поддержкой Range; None, если хранилище ссылок не выдаёт (диск)."""
        ...

    async def presign_put(
        self, key: str, *, expires_in_s: int = 300, content_type: str | None = None
    ) -> PresignedUrl | None:
        """Ссылка на запись; None, если хранилище ссылок не выдаёт."""
        ...

    async def check(self) -> None:
        """Проверка готовности: бакет или каталог доступны на запись; иначе ObjectStoreError."""
        ...


class IBlobStore(Protocol):
    """Контентно-адресуемое хранилище поверх IObjectStore: ключ блоба это его sha256."""

    async def put(self, source: ObjectSource, *, sha256: str | None = None) -> BlobInfo:
        """Кладёт блоб; без sha256 хеш считается сам, с ним сверяется (ChecksumMismatchError, ничего не записано)."""
        ...

    async def has_many(self, shas: Collection[str]) -> set[str]:
        """Какие из блобов уже лежат в хранилище."""
        ...

    async def head(self, sha256: str) -> BlobInfo | None: ...

    async def get(self, sha256: str, *, byte_range: ByteRange | None = None) -> bytes: ...

    def stream(self, sha256: str, *, chunk_size: int = 1024 * 1024) -> AsyncIterator[bytes]: ...

    async def delete(self, sha256: str) -> None: ...

    async def presign_get(self, sha256: str, *, expires_in_s: int = 300) -> PresignedUrl | None: ...

    async def presign_put(self, sha256: str, *, expires_in_s: int = 300) -> PresignedUrl | None: ...

    async def verify(self, sha256: str) -> BlobInfo:
        """Перечитывает блоб, залитый по presigned PUT, и сверяет хеш; при расхождении удаляет его
        и бросает ChecksumMismatchError, нет блоба это ObjectNotFoundError."""
        ...
