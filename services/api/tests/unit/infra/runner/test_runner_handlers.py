from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from hse_doc_studio.core.jobs.files import InlineBlob, ManifestFile
from hse_doc_studio.core.jobs.verify import (
    OpenPgpTrust,
    OpenPgpTrustMode,
    TrustBundle,
    VerifyDetachedPayload,
)
from hse_doc_studio.infra.runner.capabilities import detect_tags
from hse_doc_studio.infra.runner.config import RunnerConfig
from hse_doc_studio.infra.runner.office import GotenbergConverter
from hse_doc_studio.infra.runner.verify import EphemeralVerifyHandler
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring

from tests.unit.infra.signatures.gost_fixture import make_detached_cms, make_identity


class _SpyKeyring(GpgKeyring):
    homes: list[Path] = []  # noqa: RUF012
    imported: list[bytes] = []  # noqa: RUF012
    stopped = 0

    def __init__(self, home: Path) -> None:
        super().__init__(home)
        type(self).homes.append(home)

    def import_public_key(self, blob: bytes) -> None:
        type(self).imported.append(blob)

    def stop_agent(self) -> None:
        type(self).stopped += 1


@pytest.fixture(autouse=True)
def _reset_spy() -> None:
    _SpyKeyring.homes, _SpyKeyring.imported, _SpyKeyring.stopped = [], [], 0


def _ctx(workspace: Path):  # type: ignore[no-untyped-def]
    from uuid import uuid4  # noqa: PLC0415

    from hse_doc_studio.core.access.entities import Actor  # noqa: PLC0415
    from hse_doc_studio.core.enums import Lang  # noqa: PLC0415
    from hse_doc_studio.core.jobs.protocols import JobContext  # noqa: PLC0415
    from hse_doc_studio.infra.jobs.outputs import LocalJobOutputs  # noqa: PLC0415

    return JobContext(
        job_id=uuid4(),
        project_id=uuid4(),
        actor=Actor.user("u1"),
        locale=Lang.ru,
        workspace=workspace,
        outputs=LocalJobOutputs(),
    )


async def test_verify_keyring_is_per_job_filled_from_payload_and_removed(tmp_path: Path) -> None:
    pdf = b"%PDF body"
    (tmp_path / "f.pdf").write_bytes(pdf)
    ident = make_identity()
    payload = VerifyDetachedPayload(
        pdf=ManifestFile("f.pdf"),
        signature=InlineBlob.from_bytes(make_detached_cms(ident, pdf)),
        trust=TrustBundle(
            roots=(InlineBlob.from_bytes(ident.cert_der),),
            openpgp=OpenPgpTrust(mode=OpenPgpTrustMode.inline, keys=(InlineBlob.from_bytes(b"KEY"),), digest="d"),
        ),
    )
    handler = EphemeralVerifyHandler(_SpyKeyring)

    first = await handler.handle(payload, _ctx(tmp_path))
    await handler.handle(payload, _ctx(tmp_path))

    assert first.signature.chain == "trusted"  # type: ignore[attr-defined]
    assert _SpyKeyring.imported == [b"KEY", b"KEY"]
    assert len(set(_SpyKeyring.homes)) == 2
    assert all(not home.parent.exists() for home in _SpyKeyring.homes)
    assert _SpyKeyring.stopped == 2


async def test_verify_runner_home_mode_imports_nothing(tmp_path: Path) -> None:
    pdf = b"%PDF body"
    (tmp_path / "f.pdf").write_bytes(pdf)
    ident = make_identity()
    payload = VerifyDetachedPayload(
        pdf=ManifestFile("f.pdf"),
        signature=InlineBlob.from_bytes(make_detached_cms(ident, pdf)),
        trust=TrustBundle(openpgp=OpenPgpTrust(keys=(InlineBlob.from_bytes(b"KEY"),))),
    )

    await EphemeralVerifyHandler(_SpyKeyring).handle(payload, _ctx(tmp_path))

    assert _SpyKeyring.imported == []


async def test_verify_missing_pdf_is_a_typed_failure(tmp_path: Path) -> None:
    from hse_doc_studio.core.jobs.errors import JobFailure  # noqa: PLC0415

    payload = VerifyDetachedPayload(
        pdf=ManifestFile("none.pdf"), signature=InlineBlob.from_bytes(b"x"), trust=TrustBundle()
    )

    with pytest.raises(JobFailure) as caught:
        await EphemeralVerifyHandler(_SpyKeyring).handle(payload, _ctx(tmp_path))

    assert caught.value.error.code == "pdf_missing"
    assert _SpyKeyring.homes == []


def test_tags_follow_the_environment() -> None:
    assert detect_tags(office_url=None, archive_available=lambda fmt: False) == {"verify", "pack"}
    assert detect_tags(office_url="http://g", archive_available=lambda fmt: fmt == "7z") == {
        "verify",
        "pack",
        "office",
        "archive:7z",
    }


def test_explicit_tags_override_detection() -> None:
    config = RunnerConfig(api_url="http://api", token="t", tags=" verify, pack ,")  # type: ignore[arg-type]

    assert config.explicit_tags() == {"verify", "pack"}
    assert RunnerConfig(api_url="http://api", token="t").explicit_tags() is None  # type: ignore[arg-type]


async def test_gotenberg_converter_returns_none_on_error_and_never_raises(tmp_path: Path) -> None:
    source = tmp_path / "a.docx"
    source.write_bytes(b"doc")
    ok = GotenbergConverter("http://g/", 5, httpx.MockTransport(lambda r: httpx.Response(200, content=b"PDF")))
    bad = GotenbergConverter("http://g", 5, httpx.MockTransport(lambda r: httpx.Response(500)))

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    down = GotenbergConverter("http://g", 5, httpx.MockTransport(boom))

    assert await ok.convert_to_pdf(source) == b"PDF"
    assert await bad.convert_to_pdf(source) is None
    assert await down.convert_to_pdf(source) is None
    assert await ok.convert_to_pdf(tmp_path / "missing.docx") is None
