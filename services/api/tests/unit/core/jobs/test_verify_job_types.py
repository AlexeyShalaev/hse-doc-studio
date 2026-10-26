from __future__ import annotations

import json
from dataclasses import replace

import pytest
from hse_doc_studio.core.jobs.codec import decode_result, decode_spec, encode_result, encode_spec
from hse_doc_studio.core.jobs.entities import job_tags
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.files import InlineBlob, ManifestFile
from hse_doc_studio.core.jobs.registry import job_kind_spec
from hse_doc_studio.core.jobs.verify import (
    OpenPgpTrust,
    OpenPgpTrustMode,
    TrustBundle,
    VerifyDetachedPayload,
    VerifyDetachedResult,
)

from tests.unit.core.jobs.samples import make_verify_payload, make_verify_result, make_verify_spec


def test__verify_job_types__codec_round_trip_including_verified_signature() -> None:
    spec = make_verify_spec()
    result = make_verify_result()

    wire_spec = json.loads(json.dumps(encode_spec(spec)))
    wire_result = json.loads(json.dumps(encode_result(result)))

    assert decode_spec(wire_spec) == spec
    assert decode_result(JobKind.verify_detached, wire_result) == result
    assert isinstance(decode_result(JobKind.verify_detached, wire_result).data, VerifyDetachedResult)


def test__verify_job_types__inline_openpgp_trust_round_trip() -> None:
    payload = make_verify_payload(mode=OpenPgpTrustMode.inline)

    wire = json.loads(json.dumps(encode_spec(replace(make_verify_spec(), payload=payload))))

    assert decode_spec(wire).payload == payload
    assert payload.trust.openpgp.keys
    assert payload.trust.openpgp.digest == "ab12"


def test__verify_payload__defaults_use_runner_home_and_no_material() -> None:
    payload = VerifyDetachedPayload(
        pdf=ManifestFile("a.pdf"), signature=InlineBlob.from_bytes(b"x"), trust=TrustBundle()
    )

    assert payload.trust.roots == ()
    assert payload.trust.intermediates == ()
    assert payload.trust.openpgp == OpenPgpTrust()
    assert payload.trust.openpgp.mode is OpenPgpTrustMode.runner_home


def test__verify_payload__signature_blob_keeps_binary_bytes() -> None:
    raw = bytes(range(256))

    assert InlineBlob.from_bytes(raw).to_bytes() == raw


@pytest.mark.parametrize("path", ["/abs/a.pdf", "../a.pdf", "a\\b.pdf"])
def test__verify_payload__pdf_outside_project_rejected(path: str) -> None:
    with pytest.raises(ValueError, match="path"):
        ManifestFile(path=path)


def test__verify_registry__policy_awaitable_idempotent_not_detached_not_counted() -> None:
    policy = job_kind_spec(JobKind.verify_detached).policy

    assert (policy.awaitable, policy.idempotent) == (True, True)
    assert (policy.detachable, policy.streams_log, policy.counts_as_active, policy.blocks_folder_ops) == (
        False,
        False,
        False,
        False,
    )
    assert policy.embedded_concurrency is None


def test__job_tags__verify_detached__verify_tag() -> None:
    assert job_tags(JobKind.verify_detached, make_verify_payload()) == frozenset({"verify"})


def test__job_kind__verify_detached_wire_name() -> None:
    assert JobKind.verify_detached.value == "signature.verify_detached"
