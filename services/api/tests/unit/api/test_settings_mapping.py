"""Ответ GET /settings переживает испорченные числа в config.json: файл правят вручную и переносят между машинами."""

from __future__ import annotations

import pytest
from hse_doc_studio.api.routers.v1.settings import _map_settings

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
