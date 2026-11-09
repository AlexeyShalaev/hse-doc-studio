"""GpgKeyring как реализация порта IOpenPgpKeyImporter: проверки, которым не нужен настоящий gpg."""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.signatures.errors import GpgUnavailableError
from hse_doc_studio.infra.signatures import openpgp
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring


@pytest.fixture
def keyring_without_gpg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> GpgKeyring:
    monkeypatch.setattr(openpgp.shutil, "which", lambda *_a, **_kw: None)
    return GpgKeyring(tmp_path / "gnupg")


def test_looks_like_public_key__armored_public_block__true_private_and_junk__false(
    keyring_without_gpg: GpgKeyring,
) -> None:
    assert keyring_without_gpg.looks_like_public_key(b"\n -----BEGIN PGP PUBLIC KEY BLOCK-----\nx\n")
    assert not keyring_without_gpg.looks_like_public_key(b"-----BEGIN PGP PRIVATE KEY BLOCK-----\n")
    assert not keyring_without_gpg.looks_like_public_key(b"")


def test_import_public_key__no_gpg_binary__raises_gpg_unavailable(keyring_without_gpg: GpgKeyring) -> None:
    with pytest.raises(GpgUnavailableError):
        keyring_without_gpg.import_public_key(b"-----BEGIN PGP PUBLIC KEY BLOCK-----\nx\n")


_LISTING_V4 = """\
# off=0 ctb=88 tag=2 hlen=2 plen=145
:signature packet: algo 22, keyid 4E837FAF7DA89AC2
\tversion 4, created 1794205765, md5len 0, sigclass 0x00
\tdigest algo 10, begin of digest e3 f8
\thashed subpkt 33 len 21 (issuer fpr v4 99DD8A3F7FE692616BF5EF864E837FAF7DA89AC2)
\thashed subpkt 2 len 4 (sig created 2026-11-09)
\tsubpkt 16 len 8 (issuer key ID 4E837FAF7DA89AC2)
\tdata: [255 bits]
"""

_LISTING_KEY_ID_ONLY = """\
# off=0 ctb=89 tag=2 hlen=3 plen=284
:signature packet: algo 1, keyid a69c068edaa6150c
\tversion 4, created 1700000000, md5len 0, sigclass 0x00
\tsubpkt 16 len 8 (issuer key ID A69C068EDAA6150C)
# off=287 ctb=89 tag=2 hlen=3 plen=284
:signature packet: algo 1, keyid 0000000000000000
\tversion 4, created 1700000000, md5len 0, sigclass 0x00
"""


def test__parse_signature_issuers__fingerprint_subpacket__fingerprint_wins_over_key_id() -> None:
    assert openpgp.parse_signature_issuers(_LISTING_V4) == ["99DD8A3F7FE692616BF5EF864E837FAF7DA89AC2"]


def test__parse_signature_issuers__no_fingerprint__long_key_id_upper_and_wildcard_skipped() -> None:
    assert openpgp.parse_signature_issuers(_LISTING_KEY_ID_ONLY) == ["A69C068EDAA6150C"]


def test__parse_signature_issuers__several_packets_and_junk__each_issuer_once() -> None:
    listing = _LISTING_V4 + _LISTING_V4 + _LISTING_KEY_ID_ONLY

    assert openpgp.parse_signature_issuers(listing) == [
        "99DD8A3F7FE692616BF5EF864E837FAF7DA89AC2",
        "A69C068EDAA6150C",
    ]
    assert openpgp.parse_signature_issuers("gpg: no valid OpenPGP data found.\n") == []


def test__export_public_keys__no_gpg_binary__empty(keyring_without_gpg: GpgKeyring) -> None:
    assert keyring_without_gpg.export_public_keys(["A69C068EDAA6150C"]) == b""
