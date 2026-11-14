from __future__ import annotations

import pytest
from hse_doc_studio.core.pack_studio.entities import ReleasedVersions
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.protection import Protection

_PROTECTION = Protection(
    released=ReleasedVersions(templates={"p/t": {"2026.1.0": "sha256:x"}}),
    registries=("p/templates/t/releases.yaml",),
)


@pytest.mark.parametrize(
    ("path", "code"),
    [
        ("p/templates/t/versions/2026.1.0/version.yaml", PackStudioErrorCode.version_released),
        ("p/templates/t/versions/2026.1.0", PackStudioErrorCode.version_released),
        ("P/Templates/T/Versions/2026.1.0/x.tex", PackStudioErrorCode.version_released),
        ("p/templates/t/releases.yaml", PackStudioErrorCode.releases_read_only),
    ],
)
def test__check_write__protected__refused(path: str, code: PackStudioErrorCode) -> None:
    with pytest.raises(PackStudioError) as caught:
        _PROTECTION.check_write(path)

    assert caught.value.code is code


@pytest.mark.parametrize(
    "path",
    ["p/templates/t/versions/2026.1.1/version.yaml", "p/templates/t/examples/a.yaml", "p/pack.yaml", "README.md"],
)
def test__check_write__draft_and_outside__allowed(path: str) -> None:
    _PROTECTION.check_write(path)


@pytest.mark.parametrize("path", ["p", "p/templates", "p/templates/t", "p/templates/t/versions"])
def test__check_delete_dir__parent_of_released__refused(path: str) -> None:
    with pytest.raises(PackStudioError):
        _PROTECTION.check_delete_dir(path)


def test__check_delete_dir__draft_version__allowed() -> None:
    _PROTECTION.check_delete_dir("p/templates/t/versions/2026.1.1")


def test__check_delete_dir__parent_of_registry_only__refused() -> None:
    protection = Protection(released=ReleasedVersions(), registries=("q/templates/u/releases.yaml",))

    with pytest.raises(PackStudioError) as caught:
        protection.check_delete_dir("q/templates/u")

    assert caught.value.code is PackStudioErrorCode.releases_read_only
