"""Office editor (ONLYOFFICE Document Server) API schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class OfficeEditorConfigResponse(BaseModel):
    """Состояние движка + полный конфиг DocsAPI.DocEditor (когда state=ready).

    state:
    - "ready" — контейнер здоров, `config` содержит подписанный токеном конфиг;
    - "image_missing" — образ DS не установлен (opt-in), `image` — что ставить;
    - "unavailable" — docker недоступен / контейнер не поднялся (`detail`).
    """

    state: str = Field(description='"ready" | "image_missing" | "unavailable"')
    editor_base_url: str | None = None
    api_js_url: str | None = None
    config: dict[str, Any] | None = None
    image: str | None = None
    detail: str | None = None
    # Константа "presentations": при image_missing фронт ведёт в эту секцию
    # настроек (управление образами офисных сервисов).
    settings_section: str = "presentations"
