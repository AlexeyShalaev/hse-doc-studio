"""Карта категорий «Диска»: умолчания совпадают с настройками api, раннер добавляет свой tex_image."""

from __future__ import annotations

import pytest
from hse_doc_studio.api.config.build import CompileConfig
from hse_doc_studio.api.config.services import (
    LanguageToolConfig,
    OfficeConvertConfig,
    OfficeEditorConfig,
    OllamaConfig,
)
from hse_doc_studio.api.config.settings import Settings
from hse_doc_studio.core.docker_disk.categories import (
    DEFAULT_IMAGE_BASE,
    DEFAULT_SERVICE_VOLUMES,
    default_docker_categories,
    docker_categories,
    image_repository,
    studio_protected_refs,
)
from hse_doc_studio.core.git_remote.local_studio import IMAGE
from hse_doc_studio.infra.runner.config import RunnerConfig


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        ("ollama/ollama:latest", "ollama/ollama"),
        ("texlive/texlive", "texlive/texlive"),
        ("registry.local:5000/tex/live:TL2024", "registry.local:5000/tex/live"),
        ("registry.local:5000/tex/live", "registry.local:5000/tex/live"),
        ("ghcr.io/a/b@sha256:abc", "ghcr.io/a/b"),
        ("ghcr.io/a/b:1.0@sha256:abc", "ghcr.io/a/b"),
    ],
)
def test__image_repository__strips_tag_and_digest_keeps_registry_port(ref: str, expected: str) -> None:
    assert image_repository(ref) == expected


def test__default_docker_categories__match_api_config_defaults() -> None:
    expected: dict[str, str] = {}
    for repo in CompileConfig().allowed_repos:
        expected[repo] = "compile"
    for repo in LanguageToolConfig().allowed_repos:
        expected[repo] = "languagetool"
    for repo in [*OfficeConvertConfig().allowed_repos, *OfficeEditorConfig().allowed_repos]:
        expected[repo] = "office"
    expected[OllamaConfig().image.rsplit(":", 1)[0]] = "ai"

    assert default_docker_categories() == expected


def test__default_docker_categories__runner_tex_image_repo_is_compile() -> None:
    categories = default_docker_categories(tex_image="registry.local:5000/tex/live:TL2024")

    assert categories["registry.local:5000/tex/live"] == "compile"
    assert categories["texlive/texlive"] == "compile"


def test__docker_categories__later_group_wins_on_overlap() -> None:
    categories = docker_categories(compile_repos=["shared/repo"], office_repos=["shared/repo"])

    assert categories == {"shared/repo": "office"}


def test__studio_protected_refs__own_version_and_latest() -> None:
    assert studio_protected_refs("ghcr.io/x/studio", "1.2.3") == frozenset(
        {"ghcr.io/x/studio:1.2.3", "ghcr.io/x/studio:latest"}
    )


def test__runner_defaults__image_base_and_service_volumes_match_api_config() -> None:
    # Раннер не импортирует api/config: его умолчания сверяются с настройками сервера здесь.
    assert Settings.model_fields["image_base"].default == DEFAULT_IMAGE_BASE
    assert IMAGE == DEFAULT_IMAGE_BASE
    assert RunnerConfig.model_fields["image_base"].default == DEFAULT_IMAGE_BASE
    assert (LanguageToolConfig().model_volume_name, OllamaConfig().model_volume_name) == DEFAULT_SERVICE_VOLUMES
