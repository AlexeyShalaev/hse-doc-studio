from __future__ import annotations

import dataclasses

import pytest
from hse_doc_studio.core.jobs.files import ArtifactRef, InlineBlob, ManifestFile, StampSpec
from hse_doc_studio.core.signatures.stamps import Stamp


@pytest.mark.parametrize("path", ["a.pdf", "tz/main.tex", "Заявка/Аннотация.pdf", ".build/x.pdf"])
def test__manifest_file__project_relative_posix__accepted(path: str) -> None:
    assert ManifestFile(path).path == path


@pytest.mark.parametrize(
    "path", ["", "/etc/passwd", "../x", "a/../../x", "a/..", "a\\b.pdf", "..\\x", "C:/x", "c:x", "D:\\x"]
)
def test__manifest_file__absolute_dotdot_backslash_or_empty__rejected(path: str) -> None:
    with pytest.raises(ValueError, match="path"):
        ManifestFile(path)


def test__manifest_file__dots_inside_a_name__are_not_traversal() -> None:
    assert ManifestFile("a/..b/c..d").path == "a/..b/c..d"


def test__artifact_ref__path_is_validated_too() -> None:
    assert ArtifactRef("out/a.zip", "ab" * 32, 3).size == 3
    with pytest.raises(ValueError, match="escapes"):
        ArtifactRef("../out.zip", "ab" * 32, 3)


def test__inline_blob__bytes_round_trip() -> None:
    data = bytes(range(256))

    blob = InlineBlob.from_bytes(data)

    assert blob.to_bytes() == data
    assert blob.data_b64.isascii()
    assert InlineBlob.from_bytes(b"").to_bytes() == b""


def test__stamp_spec__mirrors_stamp_field_for_field_with_png_instead_of_png_path() -> None:
    stamp_fields = [f.name for f in dataclasses.fields(Stamp)]
    spec_fields = [f.name for f in dataclasses.fields(StampSpec)]

    assert [("png" if n == "png_path" else n) for n in stamp_fields] == spec_fields
    stamp_defaults = {f.name: f.default for f in dataclasses.fields(Stamp) if f.default is not dataclasses.MISSING}
    spec_defaults = {f.name: f.default for f in dataclasses.fields(StampSpec) if f.default is not dataclasses.MISSING}
    assert stamp_defaults == spec_defaults
