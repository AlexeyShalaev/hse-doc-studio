"""Ответ GET /settings переживает испорченные числа в config.json: файл правят вручную и переносят между машинами."""

from __future__ import annotations

import pytest
from fastapi import HTTPException
from hse_doc_studio.api.routers.v1.settings import _checked_projects_dir, _map_settings
from hse_doc_studio.core.paths import Mount, PathMapping
from hse_doc_studio.use_cases.settings.value_rules import projects_dir

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("bad", ["abc", None, 1.5, True, [1]])
def test__map_settings__bad_stored_number__falls_back_to_the_default(bad: object) -> None:
    mapped = _map_settings(
        {"git_fetch_interval_s": bad, "disk_usage_warn_gb": bad, "latex_passes": bad, "max_concurrent_compiles": bad}
    )

    assert (mapped.git_fetch_interval_s, mapped.disk_usage_warn_gb) == (300, 10)
    assert (mapped.latex_passes, mapped.max_concurrent_compiles) == (3, 2)


def test__map_settings__good_numbers__are_kept() -> None:
    mapped = _map_settings({"git_fetch_interval_s": 900, "disk_usage_warn_gb": 0, "latex_passes": 2})

    assert (mapped.git_fetch_interval_s, mapped.disk_usage_warn_gb, mapped.latex_passes) == (900, 0, 2)


def test__map_settings__projects_dir__text_or_none() -> None:
    assert _map_settings({"projects_dir": "/Users/anna/Studio"}).projects_dir == "/Users/anna/Studio"
    for bad in (None, "", 5, ["x"]):
        assert _map_settings({"projects_dir": bad}).projects_dir is None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/Users/anna/work", "/Users/anna/work"),
        ("  C:/Users/anna  ", "C:/Users/anna"),
        ("relative/dir", None),
        ("", None),
    ],
)
def test__projects_dir_rule__absolute_paths_only(raw: str, expected: str | None) -> None:
    assert projects_dir(raw) == expected
    assert projects_dir(5) is None


def test__checked_projects_dir__empty_resets_and_bad_values_are_rejected() -> None:
    free, closed = PathMapping(), PathMapping([Mount(container="/data", host="/Users/anna/Studio")])

    assert _checked_projects_dir("", free) is None
    assert _checked_projects_dir(None, free) is None
    assert _checked_projects_dir("/anywhere", free) == "/anywhere"
    assert _checked_projects_dir("/Users/anna/Studio/work", closed) == "/Users/anna/Studio/work"
    for raw, paths in (("relative", free), ("/elsewhere", closed)):
        with pytest.raises(HTTPException) as raised:
            _checked_projects_dir(raw, paths)
        assert raised.value.status_code == 400
