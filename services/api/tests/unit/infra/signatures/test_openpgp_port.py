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
