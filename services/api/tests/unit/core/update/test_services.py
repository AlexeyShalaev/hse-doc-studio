from __future__ import annotations

import pytest
from hse_doc_studio.core.update.services import (
    extract_version,
    feed_disabled,
    is_newer,
    official_feed_url,
    parse_version,
)


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v0.2.0", "0.2.0"),
        ("0.2.0", "0.2.0"),
        ("hse-doc-studio-v0.2.0", "0.2.0"),
        ("v1.4.0-rc.1", "1.4.0-rc.1"),
        ("v0.2.0 ", "0.2.0"),
    ],
)
def test__extract_version__release_tag__returns_semver_core(tag: str, expected: str) -> None:
    assert extract_version(tag) == expected


def test__extract_version__unparsable_tag__returns_it_without_v_prefix() -> None:
    # Мусор в фиде не должен ронять проверку — вернём хоть что-то сравнимое.
    assert extract_version("vnightly") == "nightly"


@pytest.mark.parametrize(
    ("candidate", "current", "expected"),
    [
        ("0.2.0", "0.1.0", True),
        ("0.10.0", "0.9.0", True),  # сравниваем числами, а не строками
        ("1.0.0", "0.99.99", True),
        ("0.1.0", "0.1.0", False),
        ("0.1.0", "0.2.0", False),
        # Суффикс предрелиза отбрасывается: 0.2.0-rc.1 не «новее» релиза 0.2.0.
        ("0.2.0-rc.1", "0.2.0", False),
        ("", "0.1.0", False),
        ("0.2.0", "", False),
    ],
)
def test__is_newer__version_pairs__compares_numeric_core(candidate: str, current: str, expected: bool) -> None:
    assert is_newer(candidate, current) is expected


def test__parse_version__component_with_junk__keeps_its_digits() -> None:
    assert parse_version("v1.2beta.3") == (1, 2, 3)


def test__parse_version__no_digits_at_all__degrades_to_zero() -> None:
    assert parse_version("nightly") == (0,)


@pytest.mark.parametrize("value", ["", "  ", "off", "OFF", "none", "disabled", "-", "0", "false"])
def test__feed_disabled__off_switches__reports_disabled(value: str) -> None:
    assert feed_disabled(value) is True


def test__feed_disabled__real_url__reports_enabled() -> None:
    assert feed_disabled("https://api.github.com/repos/owner/repo/releases") is False


def test__official_feed_url__repo__points_at_its_github_releases() -> None:
    # Форку достаточно сменить github_repo — адрес фида едет за ним.
    assert official_feed_url("owner/repo") == "https://api.github.com/repos/owner/repo/releases"
