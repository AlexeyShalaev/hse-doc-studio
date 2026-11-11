"""Категории «Диска»: какой репозиторий образа к какой подсистеме Студии относится.

Карта «репозиторий -> категория» решает, что из Docker вообще считается нашим: всё вне карты
(и вне префикса образа самой Студии) получает категорию `other`, не показывается и не удаляется.
Локальная Студия строит карту из allowlist своих настроек, раннер из умолчаний ниже и репозитория
своего `tex_image` (docs/design/storage-cleanup.md, 5.2). Умолчания совпадают с умолчаниями
настроек api (`api/config`), это сверяет тест.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

CATEGORY_COMPILE: Final = "compile"
CATEGORY_LANGUAGETOOL: Final = "languagetool"
CATEGORY_OFFICE: Final = "office"
CATEGORY_AI: Final = "ai"
CATEGORY_APP: Final = "app"

DEFAULT_COMPILE_REPOS: Final[tuple[str, ...]] = ("texlive/texlive",)
DEFAULT_LANGUAGETOOL_REPOS: Final[tuple[str, ...]] = ("erikvl87/languagetool",)
# Gotenberg (конвертация) и ONLYOFFICE (редактор): обе подсистемы Office.
DEFAULT_OFFICE_REPOS: Final[tuple[str, ...]] = ("gotenberg/gotenberg", "onlyoffice/documentserver")
DEFAULT_AI_IMAGE: Final = "ollama/ollama:latest"


def image_repository(ref: str) -> str:
    """Репозиторий из ссылки на образ без тега и дайджеста; порт реестра остаётся: `host:5000/a:1` это `host:5000/a`."""
    name = ref.split("@", 1)[0]
    head, sep, tail = name.rpartition(":")
    if sep and "/" not in tail:
        return head
    return name


def docker_categories(
    *,
    compile_repos: Iterable[str] = (),
    languagetool_repos: Iterable[str] = (),
    office_repos: Iterable[str] = (),
    ai_repos: Iterable[str] = (),
) -> dict[str, str]:
    """Карта «репозиторий -> категория». Репозиторий в двух списках получает категорию из более позднего."""
    groups: tuple[tuple[str, Iterable[str]], ...] = (
        (CATEGORY_COMPILE, compile_repos),
        (CATEGORY_LANGUAGETOOL, languagetool_repos),
        (CATEGORY_OFFICE, office_repos),
        (CATEGORY_AI, ai_repos),
    )
    return {repo: category for category, repos in groups for repo in repos}


def default_docker_categories(*, tex_image: str | None = None) -> dict[str, str]:
    """Карта из умолчаний allowlist; репозиторий `tex_image` (раннер собирает им) добавляется к сборке."""
    compile_repos = list(DEFAULT_COMPILE_REPOS)
    if tex_image:
        compile_repos.append(image_repository(tex_image))
    return docker_categories(
        compile_repos=compile_repos,
        languagetool_repos=DEFAULT_LANGUAGETOOL_REPOS,
        office_repos=DEFAULT_OFFICE_REPOS,
        ai_repos=(image_repository(DEFAULT_AI_IMAGE),),
    )


def studio_protected_refs(image_base: str, version: str) -> frozenset[str]:
    """Образы Студии, которые не удаляются никогда: своя версия и `latest`."""
    return frozenset({f"{image_base}:{version}", f"{image_base}:latest"})
