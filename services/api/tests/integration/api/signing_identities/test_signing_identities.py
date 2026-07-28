from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from cryptography.x509.oid import NameOID
from httpx import AsyncClient
from pytest_lazy_fixtures import lf


def _make_pkcs12(passphrase: bytes | None = None, cn: str = "Test Signer") -> bytes:
    """Build a real self-signed key+cert PKCS#12 blob for the import endpoint to parse."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(seconds=60))
        .not_valid_after(now + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    encryption = serialization.BestAvailableEncryption(passphrase) if passphrase else serialization.NoEncryption()
    return pkcs12.serialize_key_and_certificates(b"test-friendly-name", key, cert, None, encryption)


@pytest_asyncio.fixture
async def self_signed_identity_id(test_app: AsyncClient) -> str:
    resp = await test_app.post(
        "/api/v1/signing-identities/self-signed",
        json={"label": "My Cert", "subject_cn": "Ivan Ivanov"},
    )
    return resp.json()["id"]


@pytest_asyncio.fixture
async def pkcs12_identity_id(test_app: AsyncClient) -> str:
    blob = _make_pkcs12(cn="Deletable Signer")
    resp = await test_app.post(
        "/api/v1/signing-identities/import-pkcs12",
        data={"label": "Imported cert"},
        files={"file": ("cert.p12", blob, "application/x-pkcs12")},
    )
    return resp.json()["id"]


async def test__api__list_signing_identities__empty_by_default(test_app: AsyncClient) -> None:
    resp = await test_app.get("/api/v1/signing-identities")

    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test__api__create_self_signed__persists_and_returns_201(test_app: AsyncClient) -> None:
    resp = await test_app.post(
        "/api/v1/signing-identities/self-signed",
        json={"label": "My Cert", "subject_cn": "Ivan Ivanov", "validity_days": 30},
    )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["label"] == "My Cert"
    assert data["subject_cn"] == "Ivan Ivanov"
    assert data["kind"] == "self_signed"
    assert data["trusted"] is False
    assert "id" in data


@pytest.mark.parametrize(
    ("label", "subject_cn"),
    [
        pytest.param("   ", "Ivan Ivanov", id="blank_label"),
        pytest.param("My Cert", "   ", id="blank_subject_cn"),
    ],
)
async def test__api__create_self_signed__blank_field__returns_400(
    test_app: AsyncClient, label: str, subject_cn: str
) -> None:
    resp = await test_app.post(
        "/api/v1/signing-identities/self-signed",
        json={"label": label, "subject_cn": subject_cn},
    )

    assert resp.status_code == 400, resp.text


@pytest.mark.parametrize("validity_days", [0, 3651])
async def test__api__create_self_signed__validity_days_out_of_bounds__returns_422(
    test_app: AsyncClient, validity_days: int
) -> None:
    resp = await test_app.post(
        "/api/v1/signing-identities/self-signed",
        json={"label": "My Cert", "subject_cn": "Ivan Ivanov", "validity_days": validity_days},
    )

    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize(
    "identity_id",
    [lf("self_signed_identity_id"), lf("pkcs12_identity_id")],
    ids=["self_signed", "pkcs12"],
)
async def test__api__list_signing_identities__after_create__includes_it(
    test_app: AsyncClient, identity_id: str
) -> None:
    resp = await test_app.get("/api/v1/signing-identities")

    assert resp.status_code == 200
    assert [i["id"] for i in resp.json()] == [identity_id]


@pytest.mark.parametrize(
    "identity_id",
    [lf("self_signed_identity_id"), lf("pkcs12_identity_id")],
    ids=["self_signed", "pkcs12"],
)
async def test__api__delete_signing_identity__existing__removes_it(test_app: AsyncClient, identity_id: str) -> None:
    resp = await test_app.delete(f"/api/v1/signing-identities/{identity_id}")
    assert resp.status_code == 204

    listed = (await test_app.get("/api/v1/signing-identities")).json()
    assert listed == []


async def test__api__delete_signing_identity__missing__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.delete("/api/v1/signing-identities/00000000-0000-0000-0000-000000000000")

    assert resp.status_code == 404


async def test__api__import_pkcs12__valid_bundle_without_passphrase__persists_and_returns_201(
    test_app: AsyncClient,
) -> None:
    blob = _make_pkcs12(cn="Petr Petrov")

    resp = await test_app.post(
        "/api/v1/signing-identities/import-pkcs12",
        data={"label": "Imported cert"},
        files={"file": ("cert.p12", blob, "application/x-pkcs12")},
    )

    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["label"] == "Imported cert"
    assert data["kind"] == "pkcs12"
    assert data["subject_cn"] == "Petr Petrov"
    assert data["trusted"] is False


async def test__api__import_pkcs12__correct_passphrase__succeeds(test_app: AsyncClient) -> None:
    blob = _make_pkcs12(passphrase=b"correct-horse", cn="Passphrase Signer")

    resp = await test_app.post(
        "/api/v1/signing-identities/import-pkcs12",
        data={"label": "Imported cert", "passphrase": "correct-horse"},
        files={"file": ("cert.p12", blob, "application/x-pkcs12")},
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["subject_cn"] == "Passphrase Signer"


@pytest.mark.parametrize(
    ("data", "file_bytes"),
    [
        pytest.param({"label": "Corrupt cert"}, b"not a real pkcs12 blob", id="corrupt_bytes"),
        pytest.param({"label": "Empty file"}, b"", id="empty_file"),
        pytest.param({"label": "   "}, _make_pkcs12(), id="blank_label"),
        pytest.param(
            {"label": "Imported cert", "passphrase": "wrong-pass"},
            _make_pkcs12(passphrase=b"correct-horse"),
            id="wrong_passphrase",
        ),
    ],
)
async def test__api__import_pkcs12__invalid_input__returns_400(
    test_app: AsyncClient, data: dict[str, str], file_bytes: bytes
) -> None:
    resp = await test_app.post(
        "/api/v1/signing-identities/import-pkcs12",
        data=data,
        files={"file": ("cert.p12", file_bytes, "application/x-pkcs12")},
    )

    assert resp.status_code == 400, resp.text
