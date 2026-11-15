"""Приём архива источника каталога потоком: тело запроса целиком это файл (.zip или .tar.gz), без multipart.

Starlette сложил бы multipart на диск до обработчика, поэтому файл читается потоком здесь же и обрывается на
пределе размера (`Content-Length` и фактически принятые байты), а пишется сразу на том хранилища.
"""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

from fastapi import Request

from hse_doc_studio.core.pack_catalog.errors import CatalogError, CatalogErrorCode


async def receive_archive(request: Request, target: Path, *, max_bytes: int) -> Path:
    declared = request.headers.get("content-length")
    with contextlib.suppress(ValueError):
        if declared is not None and int(declared) > max_bytes:
            raise CatalogError(CatalogErrorCode.archive_too_large, limit=max_bytes)
    size = 0
    try:
        with target.open("wb") as out:
            async for chunk in request.stream():
                size += len(chunk)
                if size > max_bytes:
                    raise CatalogError(CatalogErrorCode.archive_too_large, limit=max_bytes)
                await asyncio.to_thread(out.write, chunk)
        if size == 0:
            raise CatalogError(CatalogErrorCode.archive_invalid)
    except BaseException:
        target.unlink(missing_ok=True)
        raise
    return target
