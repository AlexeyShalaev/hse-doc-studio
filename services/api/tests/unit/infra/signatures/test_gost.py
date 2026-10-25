from __future__ import annotations

import base64
from pathlib import Path

from asn1crypto import core, csr
from hse_doc_studio.infra.signatures import gost

# Sample PKCS#10 request from RFC 9215 (GOST R 34.10-2012 256, paramSetA).
_CSR_FILE = Path(__file__).with_name("rfc9215_csr_256.b64")


def test_streebog_known_answer() -> None:
    assert gost.streebog(b"abc", 256).hex() == "4e2919cf137ed41ec4fb6270c61826cc4fffb660341e0af3688cd0626d23b481"


def _csr_parts() -> tuple[bytes, bytes, bytes, str]:
    req = csr.CertificationRequest.load(base64.b64decode(_CSR_FILE.read_bytes()))
    info = req["certification_request_info"]
    spki = core.Sequence.load(info["subject_pk_info"].dump())
    alg = core.Sequence.load(spki[0].dump())
    curve = core.Sequence.load(alg[1].dump())[0].dotted
    pub = core.OctetString.load(spki[1].contents[1:]).native
    return info.dump(), pub, req["signature"].native, curve


def test_verifies_rfc9215_request() -> None:
    data, pub, sig, curve = _csr_parts()
    assert gost.verify_gost3410(256, curve, pub, gost.streebog(data, 256), sig) is True


def test_rejects_tampered_request() -> None:
    data, pub, sig, curve = _csr_parts()
    assert gost.verify_gost3410(256, curve, pub, gost.streebog(data + b"x", 256), sig) is False


def test_cryptopro_exchange_curves_alias_the_signature_curves() -> None:
    # A real КриптоПро УКЭП names its key curve XchA although it is CryptoPro-A.
    assert gost._CURVES["1.2.643.2.2.36.0"] == gost._CURVES["1.2.643.2.2.35.1"]
    assert gost._CURVES["1.2.643.2.2.36.1"] == gost._CURVES["1.2.643.2.2.35.3"]
