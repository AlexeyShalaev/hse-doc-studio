"""Статика одностраничного интерфейса: кэш и ответы на несуществующие файлы.

Хэшированные чанки (`/assets/<имя>-<хэш>.js`) неизменяемы и кэшируются навсегда, а `index.html`, который на них
ссылается, всегда перепроверяется. После выкатки новой версии открытая вкладка ещё просит старые чанки: на
несуществующий файл нужен честный 404. Если вместо него прийти `index.html` с 200, браузер упадёт на неверном
MIME-типе, и клиент не отличит устаревшую сборку от сбоя; 404 клиент превращает в предложение обновить страницу.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from starlette.exceptions import HTTPException
from starlette.responses import PlainTextResponse, Response
from starlette.staticfiles import StaticFiles
from starlette.types import Scope

IMMUTABLE_CACHE = "public, max-age=31536000, immutable"
REVALIDATE_CACHE = "no-cache"
NOT_FOUND_CACHE = "no-store"

# Адреса интерфейса без расширения; всё, что похоже на файл ресурса, но не найдено, получает 404, а не index.html.
_ASSET_SUFFIXES = frozenset(
    {
        ".js",
        ".mjs",
        ".css",
        ".map",
        ".json",
        ".wasm",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".avif",
        ".svg",
        ".ico",
        ".woff",
        ".woff2",
        ".ttf",
        ".otf",
        ".txt",
        ".webmanifest",
    }
)


def looks_like_asset(path: str) -> bool:
    return Path(path.rsplit("/", 1)[-1]).suffix.lower() in _ASSET_SUFFIXES


def _not_found() -> Response:
    return PlainTextResponse("Not Found", status_code=404, headers={"Cache-Control": NOT_FOUND_CACHE})


class ImmutableStaticFiles(StaticFiles):
    """`/assets`: хэш в имени файла, поэтому кэш вечный; отсутствующий файл это 404 без кэша."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404:
                return _not_found()
            raise
        if response.status_code == 404:
            return _not_found()
        if response.status_code in (200, 304):
            response.headers["Cache-Control"] = IMMUTABLE_CACHE
        return response


def mount_assets(app: FastAPI, static_dir: Path) -> None:
    app.mount("/assets", ImmutableStaticFiles(directory=static_dir / "assets"), name="assets")


def index_response(index_html: Path) -> FileResponse:
    return FileResponse(index_html, headers={"Cache-Control": REVALIDATE_CACHE})


def install_spa_fallback(app: FastAPI, static_dir: Path) -> None:
    """Версия сборки и запасной маршрут интерфейса. Последним: он забирает всё, что не нашлось раньше."""
    index_html = static_dir / "index.html"
    version_json = static_dir / "version.json"

    @app.api_route("/version.json", methods=["GET", "HEAD"], include_in_schema=False)
    async def build_version() -> Response:
        if not version_json.is_file():
            return _not_found()
        return FileResponse(version_json, media_type="application/json", headers={"Cache-Control": "no-store"})

    # Маршруты интерфейса получают index.html, чтобы роутер React разобрал адрес на клиенте.
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str) -> Response:
        if looks_like_asset(full_path):
            return _not_found()
        return index_response(index_html)
