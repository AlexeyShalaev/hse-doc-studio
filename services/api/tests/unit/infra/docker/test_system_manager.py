"""Pure logic of the disk-usage size parser and image categorization.

The docker-CLI-backed methods (disk_usage, prune_*, remove_images) shell out
to a real `docker` process and are exercised live against the dev machine's
daemon rather than mocked here — see the manual smoke test in the PR/session
notes. This file covers the string parsing and classification, which have
enough edge cases (docker's inconsistent unit suffixes, "N/A", dangling
images) to be worth pinning down directly.
"""

from __future__ import annotations

import pytest
from hse_doc_studio.infra.docker.system_manager import (
    DANGLING_CATEGORY,
    OTHER_CATEGORY,
    DockerSystemManager,
    parse_size,
)


def test__parse_size__parses_common_docker_units() -> None:
    assert parse_size("8.72GB") == int(8.72 * 10**9)
    assert parse_size("12.1MB") == int(12.1 * 10**6)
    assert parse_size("0B") == 0
    assert parse_size("287MB") == 287 * 10**6


def test__parse_size__reads_only_the_first_token_in_a_virtual_size_string() -> None:
    # Container "Size" column: "12.2MB (virtual 6.07GB)" — we want the
    # writable-layer part, not the shared base image size.
    assert parse_size("12.2MB (virtual 6.07GB)") == int(12.2 * 10**6)


def test__parse_size__handles_missing_or_unparsable_input() -> None:
    assert parse_size(None) == 0
    assert parse_size("") == 0
    assert parse_size("N/A") == 0


def _manager() -> DockerSystemManager:
    return DockerSystemManager(
        category_by_repo={
            "texlive/texlive": "compile",
            "erikvl87/languagetool": "languagetool",
        },
        app_repo_prefix="ghcr.io/alexeyshalaev/hse-doc-studio",
        managed_volume_names=frozenset({"hse-tex-cache"}),
    )


def test__classify__maps_allowlisted_repo_to_its_category() -> None:
    manager = _manager()
    assert manager._classify("texlive/texlive") == "compile"  # noqa: SLF001
    assert manager._classify("erikvl87/languagetool") == "languagetool"  # noqa: SLF001


def test__classify__maps_own_image_prefix_to_app_category() -> None:
    manager = _manager()
    assert (
        manager._classify("ghcr.io/alexeyshalaev/hse-doc-studio/all-in-one")  # noqa: SLF001
        == "app"
    )


def test__classify__falls_back_to_other_for_unrelated_repos() -> None:
    manager = _manager()
    assert manager._classify("postgres") == OTHER_CATEGORY  # noqa: SLF001
    assert manager._classify("confluentinc/cp-kafka") == OTHER_CATEGORY  # noqa: SLF001


def test__map_image__dangling_image_is_categorized_as_dangling_and_referenced_by_id() -> None:
    manager = _manager()
    entry = {
        "Repository": "<none>",
        "Tag": "<none>",
        "ID": "sha256:deadbeef",
        "Size": "287MB",
        "CreatedSince": "2 months ago",
        "Containers": "0",
    }
    usage = manager._map_image(entry, protected_refs=frozenset())  # noqa: SLF001
    assert usage.dangling is True
    assert usage.category == DANGLING_CATEGORY
    assert usage.reference == "sha256:deadbeef"


@pytest.mark.parametrize(
    ("entry", "protected_refs", "expected_protected"),
    [
        (
            {
                "Repository": "texlive/texlive",
                "Tag": "latest",
                "ID": "sha256:abc",
                "Size": "8.72GB",
                "CreatedSince": "7 weeks ago",
                "Containers": "1",
            },
            frozenset(),
            True,
        ),
        (
            {
                "Repository": "texlive/texlive",
                "Tag": "TL2024-historic",
                "ID": "sha256:def",
                "Size": "8.2GB",
                "CreatedSince": "7 weeks ago",
                "Containers": "0",
            },
            frozenset({"texlive/texlive:TL2024-historic"}),
            True,
        ),
        (
            {
                "Repository": "texlive/texlive",
                "Tag": "TL2023",
                "ID": "sha256:ghi",
                "Size": "8.1GB",
                "CreatedSince": "1 year ago",
                "Containers": "0",
            },
            frozenset({"texlive/texlive:TL2024-historic"}),
            False,
        ),
    ],
    ids=["referenced_by_container", "in_configured_protected_refs", "neither"],
)
def test__map_image__protected_reflects_container_refs_and_protected_refs(
    entry: dict[str, str], protected_refs: frozenset[str], expected_protected: bool
) -> None:
    manager = _manager()

    usage = manager._map_image(entry, protected_refs=protected_refs)  # noqa: SLF001

    assert usage.protected is expected_protected


@pytest.mark.parametrize(
    ("entry", "expected_managed"),
    [
        (
            {
                "Names": "hse-ollama",
                "Image": "ollama/ollama:latest",
                "State": "exited",
                "Status": "Exited (0) 3 days ago",
                "Size": "8.2kB",
                "Labels": "com.hse-studio.managed=true,com.docker.compose.project=hse",
            },
            True,
        ),
        # Same NAME the app would use, but no label — e.g. a container the user
        # created independently that happens to collide with our --name. Must
        # never be reported as managed, since that's what gates deletion.
        (
            {
                "Names": "hse-ollama",
                "Image": "some/other-image:latest",
                "State": "exited",
                "Status": "Exited (0) 3 days ago",
                "Size": "1.2GB",
                "Labels": "",
            },
            False,
        ),
        (
            {
                "Names": "my-postgres",
                "Image": "postgres:17-alpine",
                "State": "exited",
                "Status": "Exited (0) 2 months ago",
                "Size": "399MB",
                "Labels": "some.other.label=true",
            },
            False,
        ),
    ],
    ids=["own_label", "name_collision_without_label", "unrelated_container"],
)
def test__map_container__managed_is_true_only_for_the_apps_own_label(
    entry: dict[str, str], expected_managed: bool
) -> None:
    manager = _manager()

    result = manager._map_container(entry)  # noqa: SLF001

    assert result.managed is expected_managed
