"""Пользовательская справка по пути /help/ на хосте Студии.

Справка (services/user-docs) собрана дважды: `user` без статей администратора и `admin` со всеми. Какую
сборку отдать, решает сессия: админ установки (с разрешённого для админки host/IP) читает `admin`,
все остальные, включая не вошедших и локальную Студию, читают `user`. Это не спрятанные ссылки:
в сборке `user` нет ни страниц администратора, ни их текста в индексе поиска.

Медиа (скриншоты, ролики) общие и лежат один раз в `media/`. Ассеты `_astro/` одинаковы в обеих
сборках и отдаются без проверки сессии. Всё остальное зависит от читателя: `Cache-Control: private`.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Literal

from fastapi import FastAPI, Request
from starlette.responses import FileResponse, RedirectResponse, Response

from hse_doc_studio.api.admin_access import admin_request_allowed
from hse_doc_studio.api.auth_cookie import credentials_from_request
from hse_doc_studio.api.config import Settings
from hse_doc_studio.core.mode import StudioMode
from hse_doc_studio.use_cases.identity.sessions import SessionService

HelpAudience = Literal["user", "admin"]
HELP_PREFIX = "/help"
HELP_LANGS = ("ru", "en")
_SHARED_DIRS = ("_astro",)
_IMMUTABLE = "public, max-age=31536000, immutable"
_MEDIA = "public, max-age=86400"
_PRIVATE = "private, no-cache"


def safe_relative(path: str) -> PurePosixPath | None:
    """Путь внутри сборки без выхода наружу: `..`, абсолютные пути и обратные косые отклоняются."""
    if "\\" in path or "\x00" in path:
        return None
    parts = [part for part in PurePosixPath(path).parts if part not in ("", ".", "/")]
    if any(part == ".." for part in parts):
        return None
    return PurePosixPath(*parts) if parts else PurePosixPath()


def resolve_help_file(root: Path, audience: HelpAudience, path: str) -> Path | None:
    """Файл для запроса `/help/<path>`: медиа и ассеты общие, страницы и индекс поиска из сборки аудитории."""
    rel = safe_relative(path)
    if rel is None:
        return None
    first = rel.parts[0] if rel.parts else ""
    if first == "media":
        base = root
    elif first in _SHARED_DIRS:
        base = root / "user"
    else:
        base = root / audience
    candidate = base / rel
    if candidate.is_file():
        return candidate
    index = candidate / "index.html"
    if index.is_file():
        return index
    return None


def pick_language(request: Request) -> str:
    """Язык справки для `/help/`: явный `?lang=`, затем язык интерфейса из заголовка, затем Accept-Language."""
    explicit = request.query_params.get("lang")
    if explicit in HELP_LANGS:
        return explicit
    header = request.headers.get("x-interface-language")
    if header in HELP_LANGS:
        return header
    accept = request.headers.get("accept-language", "").lower()
    for item in accept.split(","):
        code = item.split(";", 1)[0].strip()[:2]
        if code in HELP_LANGS:
            return code
    return "ru"


def cache_control(path: str) -> str:
    rel = safe_relative(path)
    first = rel.parts[0] if rel is not None and rel.parts else ""
    if first in _SHARED_DIRS:
        return _IMMUTABLE
    if first == "media":
        return _MEDIA
    return _PRIVATE


async def help_audience(request: Request, cfg: Settings) -> HelpAudience:
    """Админская сборка только админу установки, и только там, где ему открыта админка."""
    if cfg.mode is StudioMode.local:
        return "user"
    secret = credentials_from_request(request).session_secret
    if not secret:
        return "user"
    container = getattr(request.state, "dishka_container", None) or request.app.state.dishka_container
    sessions = await container.get(SessionService)
    resolved = await sessions.resolve(secret)
    if resolved is None or not resolved.user.is_instance_admin:
        return "user"
    return "admin" if admin_request_allowed(request) else "user"


async def serve_help(path: str, request: Request, cfg: Settings) -> Response:
    root = cfg.help_dir
    rel = safe_relative(path)
    first = rel.parts[0] if rel is not None and rel.parts else ""
    audience: HelpAudience = "user" if first in (*_SHARED_DIRS, "media") else await help_audience(request, cfg)
    found = resolve_help_file(root, audience, path)
    if found is None:
        not_found = root / audience / "404.html"
        if not_found.is_file() and not path.endswith(".json"):
            return FileResponse(not_found, status_code=404, headers={"Cache-Control": _PRIVATE})
        return Response(status_code=404)
    if found.name == "index.html" and path and not path.endswith(("/", ".html")):
        # Относительные ссылки страницы считаются от каталога: без слэша они бы промахнулись.
        return RedirectResponse(f"{HELP_PREFIX}/{path}/", status_code=301)
    headers = {"Cache-Control": cache_control(path)}
    if headers["Cache-Control"] == _PRIVATE:
        headers["Vary"] = "Cookie"
    return FileResponse(found, headers=headers)


def install_help_site(app: FastAPI, cfg: Settings) -> bool:
    """Маршрут /help/ ставится, если сборка справки есть на диске (в образе всегда, в разработке после pnpm build)."""
    if not (cfg.help_dir / "user").is_dir():
        return False

    @app.get(HELP_PREFIX, include_in_schema=False)
    @app.get(f"{HELP_PREFIX}/", include_in_schema=False)
    async def help_root(request: Request) -> RedirectResponse:
        return RedirectResponse(f"{HELP_PREFIX}/{pick_language(request)}/", status_code=302)

    @app.get(f"{HELP_PREFIX}/{{path:path}}", include_in_schema=False)
    async def help_file(path: str, request: Request) -> Response:
        return await serve_help(path, request, cfg)

    return True
