"""Скрипт установки раннера как службы: статичный шаблон без секретов, образ подставляется при выдаче."""

from __future__ import annotations

from functools import cache
from importlib import resources

IMAGE_PLACEHOLDER = "@@IMAGE@@"


@cache
def _template() -> str:
    return resources.files(__package__).joinpath("install.sh").read_text(encoding="utf-8")


def render_install_script(image: str) -> str:
    """Тот же текст для всех: токен и адрес Студии скрипт берёт из окружения команды, а не из тела."""
    return _template().replace(IMAGE_PLACEHOLDER, image)
