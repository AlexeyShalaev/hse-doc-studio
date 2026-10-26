"""verify_frozen: проверка подписи задачей диспетчера и тексты ошибок по кодам."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from hse_doc_studio.core.access.context import set_current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.enums import DetachedFormat, DetachedVerdict, Lang
from hse_doc_studio.core.i18n import set_interface_language
from hse_doc_studio.core.jobs.entities import JobResult, JobSpec
from hse_doc_studio.core.jobs.enums import JobErrorCategory, JobKind, JobStatus
from hse_doc_studio.core.jobs.errors import JobError, JobFailedError, JobUnavailableError
from hse_doc_studio.core.jobs.files import InlineBlob
from hse_doc_studio.core.jobs.verify import (
    CODE_GPG_UNAVAILABLE,
    CODE_UNKNOWN_SIGNATURE_FORMAT,
    TrustBundle,
    VerifyDetachedPayload,
    VerifyDetachedResult,
)
from hse_doc_studio.core.signatures.verification import VerifiedSignature
from hse_doc_studio.core.value_objects import FrozenPdf
from hse_doc_studio.use_cases.signatures._detached_store import verify_frozen

from tests.factories import make_project

_VERIFIED = VerifiedSignature(
    format=DetachedFormat.cms,
    verdict=DetachedVerdict.valid,
    signer="Иванов Иван",
    signer_id="abc",
    notes=("chain_untrusted_root",),
)


class FakeDispatcher:
    def __init__(self, result: JobResult) -> None:
        self.result = result
        self.specs: list[JobSpec] = []

    async def run(self, spec: JobSpec, *, timeout_s: float | None = None) -> JobResult:
        self.specs.append(spec)
        return self.result


class FakeTrust:
    def __init__(self, bundle: TrustBundle) -> None:
        self.bundle = bundle
        self.calls = 0
        self.hints: list[bytes | None] = []

    def snapshot(self, signature: bytes | None = None) -> TrustBundle:
        self.calls += 1
        self.hints.append(signature)
        return self.bundle


def _frozen() -> FrozenPdf:
    return FrozenPdf(
        path=".hse-studio/frozen/annotation.pdf",
        sha256="f" * 64,
        source_sha256="a" * 64,
        size=10,
        frozen_at="2026-10-26T00:00:00+00:00",
    )


def _ctx(tmp_path: Path) -> Any:
    return SimpleNamespace(project=make_project(folder=tmp_path))


def _failed(category: JobErrorCategory, code: str, detail: str = "") -> JobResult:
    return JobResult(status=JobStatus.failed, error=JobError(category, code, detail))


async def _verify(dispatcher: FakeDispatcher, tmp_path: Path, trust: FakeTrust | None = None) -> VerifiedSignature:
    return await verify_frozen(dispatcher, trust or FakeTrust(TrustBundle()), _ctx(tmp_path), _frozen(), b"sig-bytes")  # type: ignore[arg-type]


async def test__verify_frozen__builds_spec_from_frozen_pdf_and_trust_snapshot(tmp_path: Path) -> None:
    bundle = TrustBundle(roots=(InlineBlob.from_bytes(b"root"),), intermediates=(InlineBlob.from_bytes(b"mid"),))
    trust = FakeTrust(bundle)
    dispatcher = FakeDispatcher(JobResult(status=JobStatus.succeeded, data=VerifyDetachedResult(_VERIFIED)))
    set_interface_language("en")

    verified = await _verify(dispatcher, tmp_path, trust)

    assert verified == _VERIFIED
    assert trust.calls == 1
    assert trust.hints == [b"sig-bytes"]
    (spec,) = dispatcher.specs
    assert spec.kind is JobKind.verify_detached
    assert spec.tags == frozenset({"verify"})
    assert spec.local_root == tmp_path
    assert spec.locale is Lang.en
    assert spec.actor == Actor.local()
    payload = spec.payload
    assert isinstance(payload, VerifyDetachedPayload)
    assert payload.pdf.path == ".hse-studio/frozen/annotation.pdf"
    assert payload.pdf.sha256 == "f" * 64
    assert payload.signature.to_bytes() == b"sig-bytes"
    assert payload.trust == bundle


async def test__verify_frozen__takes_the_actor_of_the_request(tmp_path: Path) -> None:
    dispatcher = FakeDispatcher(JobResult(status=JobStatus.succeeded, data=VerifyDetachedResult(_VERIFIED)))
    actor = Actor.user("u-1", name="Иван")
    set_current_actor(actor)
    try:
        await _verify(dispatcher, tmp_path)
    finally:
        set_current_actor(None)

    assert dispatcher.specs[0].actor == actor


@pytest.mark.parametrize(
    ("lang", "text"),
    [
        (
            "ru",
            "Файл не распознан как открепленная подпись (OpenPGP .asc/.sig или CMS .sig/.p7s): not a signature",
        ),
        (
            "en",
            "The file is not recognised as a detached signature (OpenPGP .asc/.sig or CMS .sig/.p7s): not a signature",
        ),
    ],
)
async def test__verify_frozen__unknown_format__localized_value_error_with_detail(
    tmp_path: Path, lang: str, text: str
) -> None:
    set_interface_language(lang)
    dispatcher = FakeDispatcher(
        _failed(JobErrorCategory.invalid_input, CODE_UNKNOWN_SIGNATURE_FORMAT, "not a signature")
    )

    with pytest.raises(ValueError, match="^" + text.replace("(", r"\(").replace(")", r"\)") + "$"):
        await _verify(dispatcher, tmp_path)


@pytest.mark.parametrize(
    ("lang", "text"),
    [
        ("ru", "В системе нет gpg: подписи OpenPGP проверить нельзя"),
        ("en", "gpg is not installed: OpenPGP signatures cannot be checked"),
    ],
)
async def test__verify_frozen__gpg_unavailable__localized_value_error(tmp_path: Path, lang: str, text: str) -> None:
    set_interface_language(lang)
    dispatcher = FakeDispatcher(_failed(JobErrorCategory.unavailable, CODE_GPG_UNAVAILABLE))

    with pytest.raises(ValueError) as caught:  # noqa: PT011
        await _verify(dispatcher, tmp_path)

    assert str(caught.value) == text


async def test__verify_frozen__other_failures__go_through_raise_for_error(tmp_path: Path) -> None:
    with pytest.raises(JobFailedError, match="boom"):
        await _verify(FakeDispatcher(_failed(JobErrorCategory.internal, "handler_crashed", "boom")), tmp_path)
    with pytest.raises(JobUnavailableError):
        await _verify(FakeDispatcher(_failed(JobErrorCategory.unavailable, "docker_down")), tmp_path)
