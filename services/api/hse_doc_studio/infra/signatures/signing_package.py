"""Files that travel with a frozen PDF: signature files, public keys and a README.

Тексты и имена перенесены в core.signatures.package_text; здесь остается тонкая
обертка со старыми сигнатурами (PackageSignature с путем на диске, keyring).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from hse_doc_studio.core.signatures import package_text
from hse_doc_studio.core.signatures.package_text import (
    build_readme,
    build_sign_instructions,
    signature_arcname,
    slug,
)
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring


@dataclass(frozen=True)
class PackageSignature(package_text.PackageSignature):
    file: Path  # on disk


def public_key_files(keyring: GpgKeyring, sigs: Sequence[PackageSignature]) -> dict[str, bytes]:
    """`<name>.pub.asc` per distinct OpenPGP signer whose public key the keyring holds."""
    return package_text.public_key_files(keyring.export_public, sigs)


__all__ = [
    "PackageSignature",
    "build_readme",
    "build_sign_instructions",
    "public_key_files",
    "signature_arcname",
    "slug",
]
