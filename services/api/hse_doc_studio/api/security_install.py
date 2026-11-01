"""Подключение CSRF и заголовков безопасности в серверном режиме."""

from __future__ import annotations

from fastapi import FastAPI

from hse_doc_studio.api.auth_cookie import is_secure_public_url, public_origin
from hse_doc_studio.api.body_limit import BODY_OVERHEAD_BYTES, UploadBodyLimitMiddleware
from hse_doc_studio.api.config import Settings
from hse_doc_studio.api.csrf import CsrfMiddleware
from hse_doc_studio.api.security_headers import SecurityHeadersMiddleware


def install_server_security(app: FastAPI, cfg: Settings) -> None:
    """Вызывается до CORS: CORS-слой оказывается снаружи и дописывает свои заголовки к ответам, в том числе к 403."""
    origins = [*cfg.cors.allow_origins]
    public = public_origin(cfg.auth.public_url)
    if public:
        origins.append(public)
    app.add_middleware(
        UploadBodyLimitMiddleware,
        path_suffix="/projects/import",
        max_bytes=cfg.server.project_import_max_bytes + BODY_OVERHEAD_BYTES,
    )
    app.add_middleware(CsrfMiddleware, allowed_origins=origins)
    app.add_middleware(
        SecurityHeadersMiddleware,
        frame_ancestors=cfg.auth.frame_ancestors,
        hsts=is_secure_public_url(cfg.auth.public_url),
    )
