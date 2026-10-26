from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from hse_doc_studio.infra.git_sync.ssh_keys import Ed25519KeyGenerator, public_key_fingerprint


def test__generate__public_line_is_authorized_keys_ed25519_with_comment() -> None:
    key = Ed25519KeyGenerator().generate("hse-doc-studio:laptop")

    kind, blob, comment = key.public_key.split(" ", 2)
    assert kind == "ssh-ed25519"
    assert blob.startswith("AAAAC3NzaC1lZDI1NTE5")
    assert comment == "hse-doc-studio:laptop"


def test__generate__private_key_is_openssh_pem_and_masked() -> None:
    key = Ed25519KeyGenerator().generate("x")

    pem = key.private_key.reveal()
    assert pem.startswith("-----BEGIN OPENSSH PRIVATE KEY-----\n")
    assert pem.endswith("-----END OPENSSH PRIVATE KEY-----\n")
    assert "OPENSSH" not in repr(key.private_key)
    assert "OPENSSH" not in repr(key)


def test__generate__fingerprint_is_sha256_without_padding() -> None:
    key = Ed25519KeyGenerator().generate("x")

    assert key.fingerprint_sha256.startswith("SHA256:")
    assert "=" not in key.fingerprint_sha256
    assert key.fingerprint_sha256 == public_key_fingerprint(key.public_key)
    assert len(key.fingerprint_sha256) == len("SHA256:") + 43


def test__generate__two_keys__differ() -> None:
    generator = Ed25519KeyGenerator()

    assert generator.generate("a").fingerprint_sha256 != generator.generate("a").fingerprint_sha256


def test__public_key_fingerprint__known_vector() -> None:
    # Публичный ключ и отпечаток получены ssh-keygen -lf на сгенерированном им же ключе.
    line = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIATzhGjYARNap1dF23nQx1QuI1hWqGWpsmWgWN/kF19P test"

    assert public_key_fingerprint(line) == "SHA256:R2rLSnmfBmmTJwCCdQh9mwNm1EaGxUnaiiJ9dudKfNo"


@pytest.mark.skipif(shutil.which("ssh-keygen") is None, reason="ssh-keygen is not installed")
def test__generate__matches_ssh_keygen(tmp_path: Path) -> None:
    key = Ed25519KeyGenerator().generate("cross-check")
    private = tmp_path / "id_ed25519"
    private.write_text(key.private_key.reveal(), encoding="utf-8")
    private.chmod(0o600)
    pub = tmp_path / "id_ed25519.pub"
    pub.write_text(key.public_key + "\n", encoding="utf-8")

    fingerprint = subprocess.run(  # noqa: S603 — аргументы свои, ssh-keygen найден через which
        ["ssh-keygen", "-lf", str(pub)], capture_output=True, text=True, check=True
    ).stdout.split()[1]
    derived = subprocess.run(  # noqa: S603
        ["ssh-keygen", "-y", "-f", str(private)], capture_output=True, text=True, check=True
    ).stdout.split()[:2]

    assert fingerprint == key.fingerprint_sha256
    assert derived == key.public_key.split()[:2]
