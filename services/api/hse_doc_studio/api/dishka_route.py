"""Маршрут dishka, у которого строковый тип ответа разрешается в модуле эндпоинта, а не в модуле обёртки.

`DishkaRoute` оборачивает эндпоинт, и `-> Response` при `from __future__ import annotations` FastAPI потом
вычисляет в глобальных именах обёртки: имени там нет, и схема OpenAPI не строится. Здесь аннотация
возврата вычисляется заранее, по глобальным именам самого эндпоинта.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, get_type_hints

from dishka.integrations.fastapi import DishkaRoute


def _resolve_return_annotation(endpoint: Callable[..., Any]) -> None:
    annotations = getattr(endpoint, "__annotations__", None)
    if not annotations or not isinstance(annotations.get("return"), str):
        return
    try:
        resolved = get_type_hints(endpoint)["return"]
    except Exception:  # noqa: BLE001 — не вычислилось: оставляем как было, поведение прежнее
        return
    # get_type_hints превращает None в NoneType, а FastAPI ждёт именно None (иначе 204 «с телом»).
    annotations["return"] = None if resolved is type(None) else resolved


class SafeDishkaRoute(DishkaRoute):
    def __init__(self, path: str, endpoint: Callable[..., Any], **kwargs: Any) -> None:
        _resolve_return_annotation(endpoint)
        super().__init__(path, endpoint, **kwargs)
