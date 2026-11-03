"""Корневой адрес сервера для ссылок в мессенджерах: теги заголовка, описания и Open Graph в самой странице.

Интерфейс одностраничный, и боты предпросмотра (Telegram, Slack, почтовые клиенты) скрипты не выполняют: они
читают только `<head>` из ответа. Поэтому `GET /` на сервере отдаёт собранный `index.html` с подставленными
тегами, а не голый каркас. Название берётся из настроек установки, язык из `?lang=`, `X-Interface-Language`
и `Accept-Language`; ничего внутреннего (версии, адреса сервисов, данные пользователей) в теги не попадает.

Выключенный лендинг, локальный режим и любой сбой чтения настроек отдают файл как есть.
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

import structlog
from fastapi import FastAPI, Request
from starlette.responses import FileResponse, HTMLResponse, Response

from hse_doc_studio.api.auth_cookie import public_origin
from hse_doc_studio.api.help_site import pick_language
from hse_doc_studio.core.identity.instance_settings import (
    InstanceEnvOverrides,
    InstanceSettings,
    effective_instance_settings,
)
from hse_doc_studio.core.identity.protocols import IInstanceSettingsRepository
from hse_doc_studio.core.mode import StudioMode

logger = structlog.get_logger(__name__)

OG_IMAGE_PATH = "/og-landing.png"
OG_IMAGE_SIZE = (1200, 630)
_OG_IMAGE_CACHE = "public, max-age=86400"

_TEXTS = {
    "ru": {
        "title": "{name}: ВКР и курсовые НИУ ВШЭ по ГОСТ в облаке",
        "description": (
            "Готовьте ВКР, курсовые и другие документы НИУ ВШЭ по ГОСТ: проверки оформления, сборка PDF, "
            "ИИ-помощник, совместная работа с научруком, электронные подписи. Войти можно сразу."
        ),
        "image_alt": "{name}: подготовка документов НИУ ВШЭ по ГОСТ",
        "locale": "ru_RU",
    },
    "en": {
        "title": "{name}: HSE theses and coursework to GOST in the cloud",
        "description": (
            "Prepare HSE theses, coursework and other documents to GOST: formatting checks, PDF builds, "
            "an AI assistant, teamwork with your supervisor, electronic signatures. Sign in right away."
        ),
        "image_alt": "{name}: preparing HSE documents to GOST",
        "locale": "en_US",
    },
}

_TITLE = re.compile(r"<title>.*?</title>", re.DOTALL)
_DESCRIPTION = re.compile(r'<meta\s+name="description"\s+content="[^"]*"\s*/?>', re.DOTALL)


def landing_texts(lang: str, name: str) -> dict[str, str]:
    texts = _TEXTS.get(lang, _TEXTS["ru"])
    return {key: value.format(name=name) for key, value in texts.items()}


def render_landing_index(index_html: str, *, lang: str, name: str, origin: str) -> str:
    """`index.html` с названием, описанием и Open Graph; `origin` без хвостового слэша, он нужен абсолютным ссылкам."""
    texts = landing_texts(lang, name)
    title = escape(texts["title"])
    description = escape(texts["description"])
    image = escape(f"{origin}{OG_IMAGE_PATH}")
    tags = "\n    ".join(
        [
            f'<meta name="description" content="{description}" />',
            f'<link rel="canonical" href="{escape(origin + "/")}" />',
            '<meta property="og:type" content="website" />',
            f'<meta property="og:site_name" content="{escape(name)}" />',
            f'<meta property="og:title" content="{title}" />',
            f'<meta property="og:description" content="{description}" />',
            f'<meta property="og:url" content="{escape(origin + "/")}" />',
            f'<meta property="og:locale" content="{texts["locale"]}" />',
            f'<meta property="og:image" content="{image}" />',
            '<meta property="og:image:type" content="image/png" />',
            f'<meta property="og:image:width" content="{OG_IMAGE_SIZE[0]}" />',
            f'<meta property="og:image:height" content="{OG_IMAGE_SIZE[1]}" />',
            f'<meta property="og:image:alt" content="{escape(texts["image_alt"])}" />',
            '<meta name="twitter:card" content="summary_large_image" />',
            f'<meta name="twitter:title" content="{title}" />',
            f'<meta name="twitter:description" content="{description}" />',
            f'<meta name="twitter:image" content="{image}" />',
        ]
    )
    html = _DESCRIPTION.sub("", index_html, count=1)
    html = _TITLE.sub(lambda _m: f"<title>{title}</title>\n    {tags}", html, count=1)
    return re.sub(r'<html lang="[a-z]{2}">', f'<html lang="{lang if lang in _TEXTS else "ru"}">', html, count=1)


async def _instance(request: Request) -> InstanceSettings | None:
    container = getattr(request.state, "dishka_container", None) or request.app.state.dishka_container
    repo = await container.get(IInstanceSettingsRepository)
    env = await container.get(InstanceEnvOverrides)
    return effective_instance_settings(await repo.get_all(), env)


def install_landing_root(app: FastAPI, *, mode: StudioMode, static_dir: Path) -> None:
    """Маршруты `/` и картинки предпросмотра. До SPA-фолбэка, иначе их забрал бы он."""
    index_html = static_dir / "index.html"
    image = static_dir / OG_IMAGE_PATH.lstrip("/")

    @app.get(OG_IMAGE_PATH, include_in_schema=False)
    async def landing_image() -> Response:
        if not image.is_file():
            return Response(status_code=404)
        return FileResponse(image, headers={"Cache-Control": _OG_IMAGE_CACHE})

    @app.get("/", include_in_schema=False)
    async def root(request: Request) -> Response:
        plain = FileResponse(index_html)
        if mode is not StudioMode.server:
            return plain
        try:
            instance = await _instance(request)
        except Exception:
            logger.exception("landing settings read failed")
            return plain
        if instance is None or not instance.landing_enabled:
            return plain
        origin = public_origin(instance.public_url) or public_origin(str(request.base_url)) or ""
        html = render_landing_index(
            index_html.read_text(encoding="utf-8"),
            lang=pick_language(request),
            name=instance.name,
            origin=origin,
        )
        return HTMLResponse(html, headers={"Cache-Control": "no-cache", "Vary": "Accept-Language"})
