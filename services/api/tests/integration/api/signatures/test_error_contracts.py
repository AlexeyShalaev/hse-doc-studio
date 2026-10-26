"""Характеризация проверки открепленных подписей: коды ответов и тексты ошибок.

Фиксирует, что видит пользователь при прикреплении подписи, перепроверке, достройке
цепочки и подписании в Студии, на ru и en: статусы, дословные тексты, заметки вердикта.
Страховочная сетка для переноса проверки за диспетчер заданий: тесты читают только
HTTP-ответы и файлы данных и не знают, кто и в каком потоке проверяет подпись.

Подменяются только внешние зависимости: сеть при достройке цепочки (httpx.get с
фальшивым транспортом), поиск бинарника gpg и проверка OpenPGP-подписи там, где
важна не она, а реакция на ее результат. Сценарии с настоящим gpg пропускаются без него.
"""

from __future__ import annotations

import hashlib
import shutil
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs7
from cryptography.x509.oid import AuthorityInformationAccessOID, NameOID
from hse_doc_studio.infra.signatures import chain_fetcher, openpgp
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring, GpgVerification
from httpx import AsyncClient, Response
from pytest_mock import MockerFixture

from tests.integration.api.signatures.test_detached_signatures import (
    _DOC,
    _SLOT,
    _enable_detached_slot,
    _freeze,
    _frozen_bytes,
    _make_pdf,
    _project_with_pdf,
)
from tests.unit.infra.signatures.gost_fixture import make_detached_cms, make_identity

_BASE = "/api/v1/projects/{pid}/docs/" + _DOC + "/detached/" + _SLOT
_ISSUER_URL = "http://pki.example.org/root.cer"
_PGP_SIGNATURE = b"-----BEGIN PGP SIGNATURE-----\n\nfake\n-----END PGP SIGNATURE-----\n"
_PGP_PUBLIC_KEY = b"-----BEGIN PGP PUBLIC KEY BLOCK-----\n\nfake-key\n-----END PGP PUBLIC KEY BLOCK-----\n"

_NO_GPG = (
    "В системе нет gpg: подписи OpenPGP проверить нельзя",
    "gpg is not installed: OpenPGP signatures cannot be checked",
)
_NO_SIGNATURE = ("К слоту не приложена подпись", "No signature is attached to this slot")
_NO_FREEZE = ("Сначала зафиксируйте PDF на подпись", "Freeze the PDF for signing first")
_NOT_A_KEY = (
    "Файл не похож на открытый ключ OpenPGP (ожидается -----BEGIN PGP PUBLIC KEY BLOCK-----)",
    "The file does not look like an OpenPGP public key (expected -----BEGIN PGP PUBLIC KEY BLOCK-----)",
)

needs_gpg = pytest.mark.skipif(shutil.which("gpg") is None, reason="gpg is not installed")


# --- helpers ---------------------------------------------------------------


def _headers(lang: str) -> dict[str, str]:
    return {"X-Interface-Language": lang}


def _text(pair: tuple[str, str], lang: str) -> str:
    return pair[0] if lang == "ru" else pair[1]


async def _post_attach(
    client: AsyncClient,
    project_id: str,
    content: bytes,
    lang: str = "ru",
    public_key: bytes | None = None,
) -> Response:
    files = {"file": ("sig.p7s", content, "application/octet-stream")}
    if public_key is not None:
        files["public_key"] = ("key.asc", public_key, "application/octet-stream")
    return await client.post(_BASE.format(pid=project_id), files=files, headers=_headers(lang))


async def _post_recheck(
    client: AsyncClient, project_id: str, lang: str = "ru", public_key: bytes | None = None
) -> Response:
    files = {"public_key": ("key.asc", public_key, "application/octet-stream")} if public_key is not None else None
    return await client.post(_BASE.format(pid=project_id) + "/recheck", files=files, headers=_headers(lang))


async def _post_complete_chain(client: AsyncClient, project_id: str, lang: str = "ru") -> Response:
    return await client.post(_BASE.format(pid=project_id) + "/complete-chain", headers=_headers(lang))


async def _frozen_project(client: AsyncClient, folder: Path) -> tuple[str, Path, bytes]:
    """Проект с PDF, слотом открепленной подписи и зафиксированным PDF: (id, PDF сборки, байты фиксации)."""
    project_id, pdf = await _project_with_pdf(client, folder)
    await _enable_detached_slot(client, project_id)
    await _freeze(client, project_id)
    return project_id, pdf, await _frozen_bytes(client, project_id)


async def _signature_state(client: AsyncClient, project_id: str) -> dict:
    return (await client.get(f"/api/v1/projects/{project_id}/signatures")).json()["detached"]


def _pgp_unknown_key(mocker: MockerFixture) -> None:
    """Проверка OpenPGP-подписи отвечает «ключа нет»: настоящий gpg не нужен."""
    mocker.patch.object(
        GpgKeyring, "verify_detached", return_value=GpgVerification(status="no_pubkey", key_id="B" * 16)
    )


def _without_gpg(mocker: MockerFixture) -> None:
    """В системе нет бинарника gpg: действует только до первого запроса, в котором создается связка ключей."""
    real = shutil.which
    mocker.patch.object(
        openpgp.shutil, "which", side_effect=lambda cmd, *a, **kw: None if cmd == "gpg" else real(cmd, *a, **kw)
    )


@contextmanager
def _foreign_ring(tmp_path: Path, name: str) -> Iterator[GpgKeyring]:
    """Чужая связка ключей: ее владелец подписывает файл, а в Студии его открытого ключа нет."""
    home = Path("/tmp") / f"hds-gpg-j0c-{name}-{tmp_path.name}"
    ring = GpgKeyring(home)
    try:
        yield ring
    finally:
        ring.stop_agent()
        shutil.rmtree(home, ignore_errors=True)


def _sign_with_foreign_key(ring: GpgKeyring, tmp_path: Path, pdf: bytes, signer: str) -> tuple[bytes, bytes, str]:
    """(подпись, открытый ключ, отпечаток): ключ создан с адресом `<signer>@example.org`."""
    key = ring.generate(signer, f"{signer.lower()}@example.org")
    doc = tmp_path / f"{signer}.pdf"
    doc.write_bytes(pdf)
    out = tmp_path / f"{signer}.pdf.asc"
    ring.sign_detached(doc, key.fingerprint, out)
    return out.read_bytes(), ring.export_public(key.fingerprint), key.fingerprint


def _rsa_chain(issuer_url: str, content: bytes) -> tuple[bytes, bytes]:
    """(CMS-подпись с одним листовым сертификатом, DER корня): корень доступен только по AIA."""
    now = datetime.now(timezone.utc)

    def name(cn: str) -> x509.Name:
        return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])

    root_key = rsa.generate_private_key(65537, 2048)
    root = (
        x509.CertificateBuilder()
        .subject_name(name("Test Root"))
        .issuer_name(name("Test Root"))
        .public_key(root_key.public_key())
        .serial_number(1)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=365))
        .sign(root_key, hashes.SHA256())
    )
    leaf_key = rsa.generate_private_key(65537, 2048)
    leaf = (
        x509.CertificateBuilder()
        .subject_name(name("Петров Пётр"))
        .issuer_name(name("Test Root"))
        .public_key(leaf_key.public_key())
        .serial_number(2)
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(
            x509.AuthorityInformationAccess(
                [
                    x509.AccessDescription(
                        AuthorityInformationAccessOID.CA_ISSUERS, x509.UniformResourceIdentifier(issuer_url)
                    )
                ]
            ),
            critical=False,
        )
        .sign(root_key, hashes.SHA256())
    )
    sig = (
        pkcs7.PKCS7SignatureBuilder()
        .set_data(content)
        .add_signer(leaf, leaf_key, hashes.SHA256())
        .sign(serialization.Encoding.DER, [pkcs7.PKCS7Options.DetachedSignature, pkcs7.PKCS7Options.Binary])
    )
    return sig, root.public_bytes(serialization.Encoding.DER)


def _fake_network(mocker: MockerFixture, root_der: bytes) -> list[str]:
    """Сеть достройки цепочки: публичный хост, ответ отдает корень. Возвращает список запрошенных адресов."""
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, content=root_der)

    transport = httpx.MockTransport(handler)

    def fake_get(url: str, **kwargs: object) -> httpx.Response:
        with httpx.Client(transport=transport) as client:
            return client.get(url)

    mocker.patch.object(chain_fetcher, "_is_public_http", return_value=True)
    mocker.patch.object(chain_fetcher.httpx, "get", side_effect=fake_get)
    return requested


# --- таблица ошибок --------------------------------------------------------


@dataclass(frozen=True)
class _Case:
    """Сценарий: что подготовить, какой запрос отправить, какой ответ ждем."""

    setup: Callable[[AsyncClient, Path], Awaitable[str]]
    call: Callable[[AsyncClient, str, str], Awaitable[Response]]
    status: int
    text: tuple[str, str] | Callable[[str], tuple[str, str]]
    # Добавка после текста, не зависящая от языка (деталь исходной ошибки).
    suffix: str = ""


async def _setup_frozen(client: AsyncClient, tmp_path: Path) -> str:
    return (await _frozen_project(client, tmp_path / "proj"))[0]


async def _setup_not_frozen(client: AsyncClient, tmp_path: Path) -> str:
    project_id, _ = await _project_with_pdf(client, tmp_path / "proj")
    await _enable_detached_slot(client, project_id)
    return project_id


async def _setup_rebuilt(client: AsyncClient, tmp_path: Path) -> str:
    project_id, pdf, _ = await _frozen_project(client, tmp_path / "proj")
    _make_pdf(pdf, "annotation, rebuilt")
    return project_id


async def _setup_attached_cms(client: AsyncClient, tmp_path: Path) -> str:
    project_id, _, frozen = await _frozen_project(client, tmp_path / "proj")
    resp = await _post_attach(client, project_id, make_detached_cms(make_identity(), frozen))
    assert resp.status_code == 200, resp.text
    return project_id


async def _call_attach_empty(client: AsyncClient, project_id: str, lang: str) -> Response:
    return await _post_attach(client, project_id, b"", lang)


async def _call_attach_text(client: AsyncClient, project_id: str, lang: str) -> Response:
    return await _post_attach(client, project_id, b"just some text", lang)


async def _call_attach_cms(client: AsyncClient, project_id: str, lang: str) -> Response:
    return await _post_attach(client, project_id, make_detached_cms(make_identity(), b"x"), lang)


async def _call_attach_with_bad_key(client: AsyncClient, project_id: str, lang: str) -> Response:
    return await _post_attach(client, project_id, make_detached_cms(make_identity(), b"x"), lang, public_key=b"junk")


async def _call_recheck(client: AsyncClient, project_id: str, lang: str) -> Response:
    return await _post_recheck(client, project_id, lang)


async def _call_recheck_with_bad_key(client: AsyncClient, project_id: str, lang: str) -> Response:
    return await _post_recheck(client, project_id, lang, public_key=b"this is not a key")


async def _call_complete_chain(client: AsyncClient, project_id: str, lang: str) -> Response:
    return await _post_complete_chain(client, project_id, lang)


async def _call_attach_to_unknown_slot(client: AsyncClient, project_id: str, lang: str) -> Response:
    return await client.post(
        f"/api/v1/projects/{project_id}/docs/{_DOC}/detached/nope",
        files={"file": ("sig.p7s", b"x", "application/octet-stream")},
        headers=_headers(lang),
    )


_NO_SLOT = (
    f"Слот 'nope' не относится к документу '{_DOC}'",
    f"Slot 'nope' does not apply to document '{_DOC}'",
)
_REBUILT = (
    "Документ пересобран после фиксации: зафиксируйте PDF заново, прежние подписи к нему не подходят",
    "The document was rebuilt after freezing: freeze the PDF again, earlier signatures no longer fit",
)
_NOT_RECOGNISED = (
    "Файл не распознан как открепленная подпись (OpenPGP .asc/.sig или CMS .sig/.p7s)",
    "The file is not recognised as a detached signature (OpenPGP .asc/.sig or CMS .sig/.p7s)",
)

_CASES = {
    "attach_empty_upload": _Case(_setup_frozen, _call_attach_empty, 400, ("Загружен пустой файл", "Empty file upload")),
    "attach_not_a_signature_with_detail": _Case(
        _setup_frozen, _call_attach_text, 400, _NOT_RECOGNISED, suffix=": not an OpenPGP or CMS signature"
    ),
    "attach_without_freeze": _Case(_setup_not_frozen, _call_attach_cms, 400, _NO_FREEZE),
    "attach_rebuilt_after_freeze": _Case(_setup_rebuilt, _call_attach_cms, 400, _REBUILT),
    "attach_unknown_slot": _Case(_setup_frozen, _call_attach_to_unknown_slot, 404, _NO_SLOT),
    "attach_public_key_not_a_pgp_block": _Case(_setup_frozen, _call_attach_with_bad_key, 400, _NOT_A_KEY),
    "recheck_without_signature": _Case(_setup_frozen, _call_recheck, 404, _NO_SIGNATURE),
    "recheck_public_key_not_a_pgp_block": _Case(_setup_attached_cms, _call_recheck_with_bad_key, 400, _NOT_A_KEY),
    "complete_chain_without_signature": _Case(_setup_frozen, _call_complete_chain, 404, _NO_SIGNATURE),
}


@pytest.mark.parametrize("lang", ["ru", "en"])
@pytest.mark.parametrize("case", _CASES.values(), ids=list(_CASES))
async def test__api__attach_signature__errors__status_and_text_unchanged(
    test_app: AsyncClient, tmp_path: Path, case: _Case, lang: str
) -> None:
    project_id = await case.setup(test_app, tmp_path)

    resp = await case.call(test_app, project_id, lang)

    assert resp.status_code == case.status, resp.text
    expected = case.text(lang) if callable(case.text) else _text(case.text, lang)
    assert resp.json()["detail"] == expected + case.suffix


@pytest.mark.parametrize("lang", ["ru", "en"])
async def test__api__attach_signature__rebuilt_after_freeze_keeps_stored_signature_listed(
    test_app: AsyncClient, tmp_path: Path, lang: str
) -> None:
    project_id, pdf, frozen = await _frozen_project(test_app, tmp_path / "proj")
    assert (await _post_attach(test_app, project_id, make_detached_cms(make_identity(), frozen))).status_code == 200
    _make_pdf(pdf, "annotation, rebuilt")

    resp = await _post_recheck(test_app, project_id, lang)

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == _text(_REBUILT, lang)
    stored = (await _signature_state(test_app, project_id))[_DOC][_SLOT]
    assert stored["current"] is False


@pytest.mark.parametrize("lang", ["ru", "en"])
async def test__api__complete_chain__not_cms__400_with_localized_text(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture, lang: str
) -> None:
    project_id, _, _ = await _frozen_project(test_app, tmp_path / "proj")
    _pgp_unknown_key(mocker)
    resp = await _post_attach(test_app, project_id, _PGP_SIGNATURE)
    assert resp.status_code == 200, resp.text
    assert resp.json()["signature"]["format"] == "openpgp"

    resp = await _post_complete_chain(test_app, project_id, lang)

    assert resp.status_code == 400, resp.text
    expected = ("Цепочку можно достраивать только для подписи CMS/CAdES", "Only CMS/CAdES signatures have a chain")
    assert resp.json()["detail"] == _text(expected, lang)


@pytest.mark.parametrize("lang", ["ru", "en"])
async def test__api__attach_signature__gpg_missing__no_gpg_text(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture, lang: str
) -> None:
    _without_gpg(mocker)
    project_id, _, _ = await _frozen_project(test_app, tmp_path / "proj")

    resp = await _post_attach(test_app, project_id, _PGP_SIGNATURE, lang)

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == _text(_NO_GPG, lang)
    # Ни подпись, ни ее файл не сохраняются, если проверить ее нечем.
    assert await _signature_state(test_app, project_id) == {}


@pytest.mark.parametrize("lang", ["ru", "en"])
async def test__api__attach_signature__gpg_missing_on_public_key_import__no_gpg_text(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture, lang: str
) -> None:
    _without_gpg(mocker)
    project_id, _, frozen = await _frozen_project(test_app, tmp_path / "proj")

    resp = await _post_attach(
        test_app, project_id, make_detached_cms(make_identity(), frozen), lang, public_key=_PGP_PUBLIC_KEY
    )

    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == _text(_NO_GPG, lang)


@pytest.mark.parametrize("lang", ["ru", "en"])
async def test__api__sign_in_studio__unknown_identity__404(test_app: AsyncClient, tmp_path: Path, lang: str) -> None:
    project_id, _, _ = await _frozen_project(test_app, tmp_path / "proj")
    identity_id = uuid4()

    resp = await test_app.post(
        _BASE.format(pid=project_id) + "/sign", json={"identity_id": str(identity_id)}, headers=_headers(lang)
    )

    assert resp.status_code == 404, resp.text
    expected = (f"Ключ подписи {identity_id} не найден", f"Signing key {identity_id} not found")
    assert resp.json()["detail"] == _text(expected, lang)


# --- достройка цепочки -----------------------------------------------------


async def test__api__complete_chain__fake_transport__fetches_and_rechecks(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture
) -> None:
    project_id, _, frozen = await _frozen_project(test_app, tmp_path / "proj")
    sig, root_der = _rsa_chain(_ISSUER_URL, frozen)
    first = await _post_attach(test_app, project_id, sig)
    assert first.status_code == 200, first.text
    assert first.json()["signature"]["verdict"] == "valid"
    assert "chain_incomplete" in first.json()["signature"]["notes"]
    requested = _fake_network(mocker, root_der)
    fingerprint = hashlib.sha256(root_der).hexdigest()

    resp = await _post_complete_chain(test_app, project_id)

    assert resp.status_code == 200, resp.text
    out = resp.json()["signature"]
    assert requested == [_ISSUER_URL]
    # Корень скачан в кэш цепочек, и повторная проверка уже видит всю цепочку, но не доверяет ей.
    assert (tmp_path / "data" / "chain_cache" / f"{fingerprint}.cer").read_bytes() == root_der
    assert "chain_incomplete" not in out["notes"]
    assert "chain_untrusted_root" in out["notes"]
    assert out["verdict"] == "valid"
    assert out["current"] is True
    assert out["root_fingerprint"] == fingerprint
    assert out["root_subject"] == "Test Root"
    stored = (await _signature_state(test_app, project_id))[_DOC][_SLOT]
    assert stored["root_fingerprint"] == fingerprint
    assert "chain_incomplete" not in stored["notes"]


async def test__api__complete_chain__private_host__nothing_fetched_chain_stays_incomplete(
    test_app: AsyncClient, tmp_path: Path, mocker: MockerFixture
) -> None:
    project_id, _, frozen = await _frozen_project(test_app, tmp_path / "proj")
    sig, _ = _rsa_chain("http://127.0.0.1/root.cer", frozen)
    assert (await _post_attach(test_app, project_id, sig)).status_code == 200
    requested: list[str] = []
    mocker.patch.object(chain_fetcher.httpx, "get", side_effect=lambda url, **kw: requested.append(url))

    resp = await _post_complete_chain(test_app, project_id)

    assert resp.status_code == 200, resp.text
    assert requested == []
    assert "chain_incomplete" in resp.json()["signature"]["notes"]
    assert not (tmp_path / "data" / "chain_cache").exists()


# --- плашка подписанта -----------------------------------------------------


async def test__api__sign_in_studio__plate_mismatch_note(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project_with_pdf(test_app, tmp_path / "proj")
    await _enable_detached_slot(test_app, project_id)
    expected = make_identity("Кротов Владимир Николаевич")
    resp = await test_app.post(
        f"/api/v1/projects/{project_id}/signatures/slots/{_SLOT}/signer/file",
        files={"file": ("cert.cer", expected.cert_der, "application/pkix-cert")},
    )
    assert resp.status_code == 200, resp.text
    await _freeze(test_app, project_id)
    resp = await test_app.post(
        "/api/v1/signing-identities/self-signed", json={"label": "My Cert", "subject_cn": "Ivan Ivanov"}
    )
    assert resp.status_code == 201, resp.text

    resp = await test_app.post(_BASE.format(pid=project_id) + "/sign", json={"identity_id": resp.json()["id"]})

    assert resp.status_code == 200, resp.text
    sig = resp.json()["signature"]
    assert sig["format"] == "cms"
    assert sig["origin"] == "studio"
    assert "plate_signer_mismatch" in sig["notes"]
    stored = (await _signature_state(test_app, project_id))[_DOC][_SLOT]
    assert "plate_signer_mismatch" in stored["notes"]


async def test__api__attach_signature__plate_mismatch_note(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _ = await _project_with_pdf(test_app, tmp_path / "proj")
    await _enable_detached_slot(test_app, project_id)
    expected = make_identity("Кротов Владимир Николаевич")
    resp = await test_app.post(
        f"/api/v1/projects/{project_id}/signatures/slots/{_SLOT}/signer/file",
        files={"file": ("cert.cer", expected.cert_der, "application/pkix-cert")},
    )
    assert resp.status_code == 200, resp.text
    await _freeze(test_app, project_id)
    frozen = await _frozen_bytes(test_app, project_id)

    other = await _post_attach(test_app, project_id, make_detached_cms(make_identity("Другой Человек"), frozen))
    assert "plate_signer_mismatch" in other.json()["signature"]["notes"]
    # Перепроверка записанной подписи заметку не теряет: подпись по-прежнему чужая.
    again = await _post_recheck(test_app, project_id)
    assert again.status_code == 200, again.text
    assert "plate_signer_mismatch" in again.json()["signature"]["notes"]
    # Подпись ожидаемого человека заметки не получает и заменяет прежнюю.
    ok = await _post_attach(test_app, project_id, make_detached_cms(expected, frozen))
    assert "plate_signer_mismatch" not in ok.json()["signature"]["notes"]


# --- настоящий gpg ---------------------------------------------------------


@needs_gpg
async def test__api__openpgp__unknown_key_import_recheck_and_expired(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _, frozen = await _frozen_project(test_app, tmp_path / "proj")
    with _foreign_ring(tmp_path, "adviser") as ring:
        sig, public, fingerprint = _sign_with_foreign_key(ring, tmp_path, frozen, "Adviser")

    # Ключа подписанта в связке Студии нет: подпись хранится как unknown_key и ждет ключ.
    resp = await _post_attach(test_app, project_id, sig)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["signature"]["verdict"] == "unknown_key"
    assert out["signature"]["format"] == "openpgp"
    assert out["missing_key_id"] == fingerprint[-16:]
    stored = (await _signature_state(test_app, project_id))[_DOC][_SLOT]
    assert stored["verdict"] == "unknown_key"
    assert stored["file_name"].endswith(".asc")

    # Перепроверка без ключа ничего не меняет.
    resp = await _post_recheck(test_app, project_id)
    assert resp.status_code == 200, resp.text
    assert resp.json()["signature"]["verdict"] == "unknown_key"
    assert resp.json()["missing_key_id"] == fingerprint[-16:]

    # Ключ приложен к перепроверке: подпись становится валидной, ключ остается в связке.
    resp = await _post_recheck(test_app, project_id, public_key=public)
    assert resp.status_code == 200, resp.text
    out = resp.json()
    assert out["signature"]["verdict"] == "valid"
    assert out["signature"]["signer_id"] == fingerprint
    assert "adviser@example.org" in out["signature"]["signer"]
    assert out["missing_key_id"] is None
    resp = await _post_recheck(test_app, project_id)
    assert resp.json()["signature"]["verdict"] == "valid"
    keys = (await test_app.get("/api/v1/signing-identities/openpgp/keys")).json()["keys"]
    assert fingerprint in [k["fingerprint"] for k in keys]


@needs_gpg
async def test__api__openpgp__public_key_with_attach__valid_at_once(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _, frozen = await _frozen_project(test_app, tmp_path / "proj")
    with _foreign_ring(tmp_path, "reviewer") as ring:
        sig, public, fingerprint = _sign_with_foreign_key(ring, tmp_path, frozen, "Reviewer")

    resp = await _post_attach(test_app, project_id, sig, public_key=public)

    assert resp.status_code == 200, resp.text
    assert resp.json()["signature"]["verdict"] == "valid"
    assert resp.json()["signature"]["signer_id"] == fingerprint
    assert resp.json()["missing_key_id"] is None


@needs_gpg
async def test__api__openpgp__signature_of_another_file__invalid(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _, _ = await _frozen_project(test_app, tmp_path / "proj")
    with _foreign_ring(tmp_path, "other") as ring:
        sig, public, _ = _sign_with_foreign_key(ring, tmp_path, b"%PDF some other file", "Other")

    resp = await _post_attach(test_app, project_id, sig, public_key=public)

    assert resp.status_code == 200, resp.text
    assert resp.json()["signature"]["verdict"] == "invalid"


@needs_gpg
async def test__api__openpgp__expired_key__valid_with_key_expired_note(test_app: AsyncClient, tmp_path: Path) -> None:
    project_id, _, frozen = await _frozen_project(test_app, tmp_path / "proj")
    with _foreign_ring(tmp_path, "expired") as ring:
        # Ключ жил сутки в 2020 году и подписал файл, пока был действителен.
        past = ["--faked-system-time", "20200101T120000"]
        ring._run(
            [*past, "--quick-generate-key", "Expired <expired@example.org>", "ed25519", "sign", "1d"], passphrase=""
        )  # noqa: SLF001
        key = next(k for k in ring.list_keys() if k.has_secret)
        doc = tmp_path / "expired.pdf"
        doc.write_bytes(frozen)
        out = tmp_path / "expired.pdf.asc"
        args = ["--armor", "--local-user", f"{key.fingerprint}!", "--output", str(out), "--detach-sign", str(doc)]
        ring._run([*past, *args], passphrase="")  # noqa: SLF001
        sig, public = out.read_bytes(), ring.export_public(key.fingerprint)

    resp = await _post_attach(test_app, project_id, sig, public_key=public)

    assert resp.status_code == 200, resp.text
    out_sig = resp.json()["signature"]
    assert out_sig["verdict"] == "valid"
    assert "key_expired" in out_sig["notes"]
    assert out_sig["signer_id"] == key.fingerprint
    assert out_sig["not_after"].startswith("2020-01-02")
    assert out_sig["signed_at"].startswith("2020-01-01")
