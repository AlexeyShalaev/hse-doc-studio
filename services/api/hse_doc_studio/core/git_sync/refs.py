"""Ссылки хранилища проекта, которые заводит только переносной файл (остальные: sync_apply)."""

from __future__ import annotations

from typing import Final

# Чужая ветка из переносного файла лежит здесь, пока идёт слияние; в сеть эти ссылки не уходят.
BUNDLE_PREFIX: Final = "refs/hse/bundle/"


def bundle_ref(branch: str) -> str:
    return f"{BUNDLE_PREFIX}{branch}"
