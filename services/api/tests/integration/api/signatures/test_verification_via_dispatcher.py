"""Проверка открепленных подписей идет задачей signature.verify_detached через диспетчер.

HTTP-поведение закреплено в test_error_contracts.py и test_detached_signatures.py; здесь
видно, что именно уходит диспетчеру. Все сценарии идут с включенным проводным кодеком
(`jobs.round_trip_payloads`), как будет у удаленного раннера.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.api.config import settings
from hse_doc_studio.core.jobs.entities import JobResult, JobSpec
from hse_doc_studio.core.jobs.enums import JobKind
from hse_doc_studio.core.jobs.verify import OpenPgpTrustMode, VerifyDetachedPayload
from hse_doc_studio.infra.jobs.local_dispatcher import LocalJobDispatcher
from httpx import AsyncClient
from pytest_mock import MockerFixture

from tests.integration.api.signatures.test_detached_signatures import (
    _DOC,
    _SLOT,
    _enable_detached_slot,
    _freeze,
    _frozen_bytes,
    _project_with_pdf,
)
from tests.unit.infra.signatures.gost_fixture import make_detached_cms, make_identity

_BASE = f"/api/v1/projects/{{pid}}/docs/{_DOC}/detached/{_SLOT}"


@pytest.fixture
def round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Включается до создания контейнера: фикстура test_app идет следом по порядку аргументов."""
    monkeypatch.setattr(settings.jobs, "round_trip_payloads", True)


@pytest.fixture
def seen_specs(mocker: MockerFixture) -> list[JobSpec]:
    specs: list[JobSpec] = []
    original = LocalJobDispatcher.run

    async def spy(self: LocalJobDispatcher, spec: JobSpec, *, timeout_s: float | None = None) -> JobResult:
        specs.append(spec)
        return await original(self, spec, timeout_s=timeout_s)

    mocker.patch.object(LocalJobDispatcher, "run", spy)
    return specs


async def test__attach__verifies_through_the_dispatcher_with_trust_built_from_current_dirs(
    round_trip: None, test_app: AsyncClient, tmp_path: Path, seen_specs: list[JobSpec]
) -> None:
    data_dir = tmp_path / "data"
    identity = make_identity()
    (data_dir / "trusted_roots").mkdir()
    (data_dir / "trusted_roots" / "root.cer").write_bytes(identity.cert_der)
    (data_dir / "trusted_roots" / "notes.txt").write_bytes(b"not a certificate")
    (data_dir / "chain_cache").mkdir()
    (data_dir / "chain_cache" / "issuer.cer").write_bytes(b"cached issuer")
    project_id, _ = await _project_with_pdf(test_app, tmp_path / "proj")
    await _enable_detached_slot(test_app, project_id)
    frozen_info = await _freeze(test_app, project_id)
    signature = make_detached_cms(identity, await _frozen_bytes(test_app, project_id))

    resp = await test_app.post(
        _BASE.format(pid=project_id), files={"file": ("sig.p7s", signature, "application/octet-stream")}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["signature"]["chain"] == "trusted"
    (spec,) = seen_specs
    assert spec.kind is JobKind.verify_detached
    assert spec.project_id.hex == project_id.replace("-", "")
    assert spec.local_root == Path((await test_app.get(f"/api/v1/projects/{project_id}")).json()["folder"])
    payload = spec.payload
    assert isinstance(payload, VerifyDetachedPayload)
    assert payload.pdf.path.endswith("annotation.pdf")
    assert payload.pdf.sha256 == frozen_info["frozen"]["sha256"]
    assert payload.signature.to_bytes() == signature
    assert [b.to_bytes() for b in payload.trust.roots] == [identity.cert_der]
    assert [b.to_bytes() for b in payload.trust.intermediates] == [b"cached issuer"]
    assert payload.trust.openpgp.mode is OpenPgpTrustMode.runner_home


async def test__recheck__verifies_the_stored_signature_through_the_dispatcher(
    round_trip: None, test_app: AsyncClient, tmp_path: Path, seen_specs: list[JobSpec]
) -> None:
    project_id, _ = await _project_with_pdf(test_app, tmp_path / "proj")
    await _enable_detached_slot(test_app, project_id)
    await _freeze(test_app, project_id)
    signature = make_detached_cms(make_identity(), await _frozen_bytes(test_app, project_id))
    await test_app.post(_BASE.format(pid=project_id), files={"file": ("sig.p7s", signature, "application/pkix-cms")})
    seen_specs.clear()

    resp = await test_app.post(_BASE.format(pid=project_id) + "/recheck")

    assert resp.status_code == 200, resp.text
    (spec,) = seen_specs
    assert isinstance(spec.payload, VerifyDetachedPayload)
    assert spec.payload.signature.to_bytes() == signature


async def test__sign_in_studio__verifies_own_signature_via_dispatcher(
    round_trip: None, test_app: AsyncClient, tmp_path: Path, seen_specs: list[JobSpec]
) -> None:
    project_id, _ = await _project_with_pdf(test_app, tmp_path / "proj")
    await _enable_detached_slot(test_app, project_id)
    await _freeze(test_app, project_id)
    resp = await test_app.post(
        "/api/v1/signing-identities/self-signed", json={"label": "My Cert", "subject_cn": "Ivan Ivanov"}
    )
    assert resp.status_code == 201, resp.text

    resp = await test_app.post(_BASE.format(pid=project_id) + "/sign", json={"identity_id": resp.json()["id"]})

    assert resp.status_code == 200, resp.text
    assert resp.json()["signature"]["origin"] == "studio"
    (spec,) = seen_specs
    assert spec.kind is JobKind.verify_detached
    assert isinstance(spec.payload, VerifyDetachedPayload)
    assert spec.local_root is not None
    (stored,) = spec.local_root.rglob("*.p7s")
    assert spec.payload.signature.to_bytes() == stored.read_bytes()
