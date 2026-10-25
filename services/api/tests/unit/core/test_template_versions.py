from __future__ import annotations

import pytest
from hse_doc_studio.core.enums import TemplateUpdateClass
from hse_doc_studio.core.template_versions import (
    classify_update,
    is_newer,
    parse_app_version,
    parse_version_key,
    stricter,
    studio_satisfies,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2026.1", (2026, 1, 0)),
        ("2026.1.0", (2026, 1, 0)),
        ("2026.1.3", (2026, 1, 3)),
        (" 2027.0.1 ", (2027, 0, 1)),
        ("dev", None),
        ("2026", None),
        ("2026.1-rc1", None),
    ],
)
def test__parse_version_key(raw: str, expected: tuple[int, int, int] | None) -> None:
    assert parse_version_key(raw) == expected


def test__two_part_id__equals_patch_zero() -> None:
    # Каталоги и lock первых версий ("2026.1") не переименовываются.
    assert not is_newer("2026.1.0", "2026.1")
    assert not is_newer("2026.1", "2026.1.0")
    assert is_newer("2026.1.1", "2026.1")


@pytest.mark.parametrize(
    ("src", "dst", "expected"),
    [
        ("2026.1", "2026.1.1", TemplateUpdateClass.patch),
        ("2026.1.1", "2026.2.0", TemplateUpdateClass.minor),
        ("2026.1", "2026.2", TemplateUpdateClass.minor),
        ("2026.3.4", "2027.0.0", TemplateUpdateClass.major),
        ("2026.1.1", "2026.1.1", None),
        ("2026.2.0", "2026.1.9", None),
        ("2026.1", "dev", None),
    ],
)
def test__classify_update(src: str, dst: str, expected: TemplateUpdateClass | None) -> None:
    assert classify_update(src, dst) == expected


def test__stricter__picks_the_stronger_class() -> None:
    assert stricter(TemplateUpdateClass.patch, TemplateUpdateClass.minor) == TemplateUpdateClass.minor
    assert stricter(TemplateUpdateClass.major, TemplateUpdateClass.patch) == TemplateUpdateClass.major
    assert stricter(None, TemplateUpdateClass.patch) == TemplateUpdateClass.patch
    assert stricter(TemplateUpdateClass.minor, None) == TemplateUpdateClass.minor


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("0.1.3", (0, 1, 3)), ("v0.2.0", (0, 2, 0)), ("0.2.0-rc.1", (0, 2, 0)), ("1.2", (1, 2, 0)), ("dev", None)],
)
def test__parse_app_version(raw: str, expected: tuple[int, int, int] | None) -> None:
    assert parse_app_version(raw) == expected


def test__studio_satisfies() -> None:
    assert studio_satisfies(None, "0.1.3")
    assert studio_satisfies("0.1.3", "0.1.3")
    assert studio_satisfies("0.1.0", "0.2.0")
    assert not studio_satisfies("0.2.0", "0.1.3")
    # dev-сборка с неразобранной версией открывает всё.
    assert studio_satisfies("0.2.0", "dev")
