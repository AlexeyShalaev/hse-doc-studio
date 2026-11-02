import pytest
from hse_doc_studio.core.git_remote.local_studio import (
    DEFAULT_LOCAL_PORT,
    StudioCompat,
    local_studio_info,
    parse_version,
    recommended_tag,
    studio_compat,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("0.3.1", (0, 3, 1)),
        ("v0.3", (0, 3, 0)),
        ("1.2.0-rc.1", (1, 2, 0)),
        (" 2.0.5 ", (2, 0, 5)),
        ("dev", None),
        ("", None),
        (None, None),
    ],
)
def test__parse_version__semver_prefix(raw: str | None, expected: tuple[int, int, int] | None) -> None:
    assert parse_version(raw) == expected


@pytest.mark.parametrize(
    ("local", "server", "expected"),
    [
        ("0.3.0", "0.3.0", StudioCompat.same),
        ("0.3.2", "0.3.0", StudioCompat.compatible),
        ("0.3.0", "0.3.4", StudioCompat.compatible),
        ("0.2.9", "0.3.0", StudioCompat.local_older),
        ("0.4.0", "0.3.9", StudioCompat.local_newer),
        ("1.0.0", "0.9.0", StudioCompat.local_newer),
        ("dev", "0.3.0", StudioCompat.unknown),
        ("0.3.0", "", StudioCompat.unknown),
    ],
)
def test__studio_compat__by_major_minor(local: str, server: str, expected: StudioCompat) -> None:
    assert studio_compat(local, server) is expected


def test__recommended_tag__major_minor_or_none() -> None:
    assert recommended_tag("0.3.7") == "0.3"
    assert recommended_tag("main") is None


def test__local_studio_info__links_from_repo_and_trimmed_server_url() -> None:
    info = local_studio_info(
        server_url="https://studio.example.org/",
        server_version="0.3.1",
        github_repo="/Owner/repo/",
        git_remote_enabled=True,
    )

    assert info.server_url == "https://studio.example.org"
    assert info.recommended_tag == "0.3"
    assert info.install_base_url == "https://raw.githubusercontent.com/Owner/repo/master/deploy"
    assert info.releases_url == "https://github.com/Owner/repo/releases"
    assert info.default_port == DEFAULT_LOCAL_PORT
    assert info.image == "ghcr.io/alexeyshalaev/hse-doc-studio"
