from __future__ import annotations

import dataclasses

import pytest
from hse_doc_studio.core.jobs.codec import decode, encode
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
    # `slot_id` метки только для текста ошибок, на PDF его нет: по проводу не едет (раннер отверг бы лишнее поле),
    # штамповщик пакета берет слот из имени картинки.
    stamp_fields = [f.name for f in dataclasses.fields(Stamp) if f.name != "slot_id"]
    spec_fields = [f.name for f in dataclasses.fields(StampSpec)]

    assert [("png" if n == "png_path" else n) for n in stamp_fields] == spec_fields
    stamp_defaults = {
        f.name: f.default
        for f in dataclasses.fields(Stamp)
        if f.default is not dataclasses.MISSING and f.name != "slot_id"
    }
    spec_defaults = {f.name: f.default for f in dataclasses.fields(StampSpec) if f.default is not dataclasses.MISSING}
    assert stamp_defaults == spec_defaults


def test__stamp_spec__date_fields_go_on_the_wire_only_when_set() -> None:
    # Раннер прежней версии отвергает незнакомые поля: пакет без меток даты должен идти к нему как раньше.
    plain = StampSpec(page=1, x_mm=1, y_mm=2, width_mm=3, png=None, aspect_ratio=0.4, text="Подписано")
    dated = StampSpec(
        page=2, x_mm=1, y_mm=2, width_mm=8, png=None, aspect_ratio=0.6, text="13", height_mm=5, align="left"
    )

    plain_wire, dated_wire = encode(plain), encode(dated)

    assert isinstance(plain_wire, dict)
    assert isinstance(dated_wire, dict)
    assert {"height_mm", "align"} & set(plain_wire) == set()
    assert (dated_wire["height_mm"], dated_wire["align"]) == (5, "left")
    assert decode(StampSpec, plain_wire) == plain
    assert decode(StampSpec, dated_wire) == dated
