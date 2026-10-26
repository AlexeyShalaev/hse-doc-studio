from __future__ import annotations

import dataclasses
import json

import pytest
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.jobs.codec import decode_result, decode_spec, encode_result, encode_spec
from hse_doc_studio.core.jobs.entities import job_tags
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.files import InlineBlob, ManifestFile, StampSpec
from hse_doc_studio.core.jobs.pack import ArchiveFormat, PackEntry, PackEntryKind, PackSubmissionPayload
from hse_doc_studio.core.signatures.stamps import Stamp

from tests.unit.core.jobs.samples import make_pack_payload, make_pack_result, make_pack_spec


def _file(path: str, sha: str = "aa") -> ManifestFile:
    return ManifestFile(path=path, sha256=sha * 32, size=1)


def _payload(*entries: PackEntry) -> PackSubmissionPayload:
    return PackSubmissionPayload(
        base_name="pack",
        profile_id="p",
        lang=Lang.ru,
        archive_format=ArchiveFormat.zip,
        keep_folder=False,
        entries=entries,
    )


def test__pack_payload__codec_round_trip_equal() -> None:
    spec = make_pack_spec()

    wire = json.loads(json.dumps(encode_spec(spec)))

    assert decode_spec(wire) == spec
    assert decode_spec(wire).payload == make_pack_payload()
    assert decode_result(JobKind.pack_submission, json.loads(json.dumps(encode_result(make_pack_result())))) == (
        make_pack_result()
    )


def test__pack_payload__defaults_keep_manifest_unverified() -> None:
    payload = _payload()

    assert payload.verify_manifest is False
    assert payload.entries == ()


@pytest.mark.parametrize("base_name", ["", "/abs", "../x", "a/b", "a\\b"])
def test__pack_payload__base_name_must_be_a_single_segment(base_name: str) -> None:
    with pytest.raises(ValueError, match="path|segment"):
        PackSubmissionPayload(
            base_name=base_name,
            profile_id="p",
            lang=Lang.en,
            archive_format=ArchiveFormat.zip,
            keep_folder=True,
            entries=(),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"kind": PackEntryKind.copy},
        {"kind": PackEntryKind.stamp_pdf},
        {"kind": PackEntryKind.text},
        {"kind": PackEntryKind.blob},
        {"kind": PackEntryKind.text, "text": "x", "source": _file("a.pdf")},
        {"kind": PackEntryKind.blob, "blob": InlineBlob.from_bytes(b"k"), "text": "x"},
        {"kind": PackEntryKind.copy, "source": _file("a.pdf"), "blob": InlineBlob.from_bytes(b"k")},
    ],
)
def test__pack_entry__kind_field_requirements(kwargs: dict[str, object]) -> None:
    with pytest.raises(ValueError, match="entry"):
        PackEntry(arcname="out.bin", **kwargs)  # type: ignore[arg-type]


def test__pack_entry__stamps_only_on_stamp_pdf() -> None:
    stamp = StampSpec(page=1, x_mm=1, y_mm=1, width_mm=10, png=None, aspect_ratio=0.4, text="Подписано")

    assert PackEntry(PackEntryKind.stamp_pdf, "a.pdf", source=_file("a.pdf"), stamps=(stamp,)).stamps == (stamp,)
    with pytest.raises(ValueError, match="stamps"):
        PackEntry(PackEntryKind.copy, "a.pdf", source=_file("a.pdf"), stamps=(stamp,))


def test__pack_entry__empty_text_is_a_valid_text_entry() -> None:
    assert PackEntry(PackEntryKind.text, "empty.txt", text="").text == ""


def test__pack_entry__text_and_blob_entries_carry_no_path() -> None:
    text = PackEntry(PackEntryKind.text, "README.txt", text="hello")
    blob = PackEntry(PackEntryKind.blob, "key.asc", blob=InlineBlob.from_bytes(b"k"))

    assert text.source is None
    assert blob.source is None
    assert text.manifest_files() == ()
    assert blob.manifest_files() == ()
    assert blob.blob is not None
    assert blob.blob.to_bytes() == b"k"


@pytest.mark.parametrize("arcname", ["", "/abs.pdf", "../x.pdf", "a/../../x", "a\\b.pdf"])
def test__pack_entry__arcname_outside_the_archive_root__rejected(arcname: str) -> None:
    with pytest.raises(ValueError, match="path"):
        PackEntry(PackEntryKind.text, arcname, text="x")


def test__pack_payload__manifest_files_deduplicated_and_relative() -> None:
    png = _file(".hse-studio/sig.png", "cc")
    stamp = StampSpec(page=1, x_mm=1, y_mm=1, width_mm=10, png=png, aspect_ratio=0.4)
    payload = _payload(
        PackEntry(PackEntryKind.stamp_pdf, "A.pdf", source=_file("a/a.pdf"), stamps=(stamp, stamp)),
        PackEntry(PackEntryKind.copy, "A-orig.pdf", source=_file("a/a.pdf")),
        PackEntry(PackEntryKind.copy, "B.pdf", source=_file("b/b.pdf", "bb")),
        PackEntry(PackEntryKind.text, "README.txt", text="x"),
    )

    files = payload.manifest_files()

    assert [f.path for f in files] == ["a/a.pdf", ".hse-studio/sig.png", "b/b.pdf"]
    assert all(not f.path.startswith("/") and ".." not in f.path.split("/") for f in files)


def test__pack_payload__same_path_with_different_hash__rejected() -> None:
    payload = _payload(
        PackEntry(PackEntryKind.copy, "1.pdf", source=_file("a.pdf", "aa")),
        PackEntry(PackEntryKind.copy, "2.pdf", source=_file("a.pdf", "bb")),
    )

    with pytest.raises(ValueError, match="different"):
        payload.manifest_files()


def test__stamp_spec__field_parity_with_core_stamp() -> None:
    stamp_fields = [f.name for f in dataclasses.fields(Stamp)]
    spec_fields = [f.name for f in dataclasses.fields(StampSpec)]

    assert [("png" if name == "png_path" else name) for name in stamp_fields] == spec_fields


@pytest.mark.parametrize(
    ("archive_format", "tags"),
    [
        (ArchiveFormat.zip, {"pack"}),
        (ArchiveFormat.targz, {"pack"}),
        (ArchiveFormat.sevenz, {"pack", "archive:7z"}),
        (ArchiveFormat.rar, {"pack", "archive:rar"}),
    ],
)
def test__pack_job_tags__zip_vs_7z_vs_rar(archive_format: ArchiveFormat, tags: set[str]) -> None:
    payload = make_pack_payload(archive_format=archive_format)

    assert job_tags(JobKind.pack_submission, payload) == frozenset(tags)


def test__pack_payload__unknown_archive_format__rejected_on_decode() -> None:
    wire = encode_spec(make_pack_spec())
    payload = dict(wire["payload"])  # type: ignore[call-overload]
    payload["archive_format"] = "arj"

    with pytest.raises(ValueError, match="arj"):
        decode_spec({**wire, "payload": payload})
