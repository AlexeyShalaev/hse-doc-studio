from __future__ import annotations

import json

import pytest
from hse_doc_studio.core.jobs.codec import decode_result, decode_spec, encode_result, encode_spec
from hse_doc_studio.core.jobs.entities import job_tags
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.files import ManifestFile
from hse_doc_studio.core.jobs.office import OfficeConvertPayload, OfficeConvertReason

from tests.unit.core.jobs.samples import make_office_payload, make_office_result, make_office_spec


def test__office_payload__codec_round_trip() -> None:
    spec = make_office_spec()

    wire = json.loads(json.dumps(encode_spec(spec)))

    assert decode_spec(wire) == spec
    assert decode_spec(wire).payload == make_office_payload()


def test__office_payload__defaults_keep_default_image_and_no_pages() -> None:
    payload = OfficeConvertPayload(source=ManifestFile(path="a/b.pptx"), output_path="a/b.pdf")

    assert payload.image is None
    assert payload.want_pages is False
    assert payload.convert_timeout_s is None
    assert payload.reason is OfficeConvertReason.upload


def test__office_result__codec_round_trip() -> None:
    result = make_office_result()

    assert decode_result(JobKind.office_convert, json.loads(json.dumps(encode_result(result)))) == result


@pytest.mark.parametrize("path", ["/abs/a.docx", "../a.docx", "a\\b.docx", ""])
def test__office_payload__source_outside_project_rejected(path: str) -> None:
    with pytest.raises(ValueError, match="path"):
        ManifestFile(path=path)


def test__job_tags__office_convert__office_tag() -> None:
    assert job_tags(JobKind.office_convert, make_office_payload()) == frozenset({"office"})
