"""Files that travel with a frozen PDF: signature files, public keys and a README."""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass
from pathlib import Path

from hse_doc_studio.core.enums import DetachedFormat
from hse_doc_studio.infra.signatures.openpgp import GpgKeyring


@dataclass(frozen=True)
class PackageSignature:
    slot_label: str
    file: Path  # on disk
    arcname: str  # name inside the package
    format: DetachedFormat
    signer: str
    signer_id: str


def slug(text: str) -> str:
    cleaned = re.sub(r"[^\w.\-]+", "_", text, flags=re.UNICODE).strip("_")
    return cleaned or "signature"


def signature_arcname(pdf_name: str, slot_label: str, ext: str) -> str:
    """`Заявка.pdf` + «Научный руководитель» + `.asc` → `Заявка.Научный_руководитель.asc`."""
    stem = pdf_name.rsplit(".", 1)[0] if "." in pdf_name else pdf_name
    return f"{stem}.{slug(slot_label)}{ext}"


def public_key_files(keyring: GpgKeyring, sigs: list[PackageSignature]) -> dict[str, bytes]:
    """`<name>.pub.asc` per distinct OpenPGP signer whose public key the keyring holds."""
    files: dict[str, bytes] = {}
    seen: set[str] = set()
    for s in sigs:
        if s.format is not DetachedFormat.openpgp or s.signer_id in seen:
            continue
        seen.add(s.signer_id)
        blob = b""
        with contextlib.suppress(Exception):
            blob = keyring.export_public(s.signer_id)
        if blob:
            files[f"public-key.{slug(s.signer or s.signer_id[-16:])}.asc"] = blob
    return files


_RU = {
    "title": "Открепленные электронные подписи",
    "intro": (
        "Подпись относится к PDF-файлу побайтово. Любое изменение файла, даже пересохранение,\n"
        "делает подпись недействительной."
    ),
    "files": "Файлы:",
    "sha": "SHA-256 PDF:",
    "pgp": "Проверка подписей OpenPGP (.asc / .sig):",
    "pgp_hint": "  Открытые ключи подписантов лежат рядом (public-key.*.asc).",
    "cms": "Проверка подписей CAdES / CMS (.p7s):",
    "cms_hint": (
        "  Подписи с ГОСТ Р 34.10-2012 проверяют в КриптоАРМ, КриптоПро или на портале Госуслуг\n"
        "  (раздел проверки электронной подписи: файл и файл подписи)."
    ),
    "signer": "подписант",
}
_EN = {
    "title": "Detached electronic signatures",
    "intro": (
        "Each signature covers the PDF byte for byte. Any change to the file, even re-saving it,\n"
        "invalidates the signatures."
    ),
    "files": "Files:",
    "sha": "SHA-256 of the PDF:",
    "pgp": "Verifying OpenPGP signatures (.asc / .sig):",
    "pgp_hint": "  The signers' public keys are included (public-key.*.asc).",
    "cms": "Verifying CAdES / CMS signatures (.p7s):",
    "cms_hint": (
        "  GOST R 34.10-2012 signatures are checked in CryptoARM, CryptoPro or the Gosuslugi\n"
        "  e-signature verification service (the file and the signature file)."
    ),
    "signer": "signer",
}


def build_readme(lang: str, pdf_name: str, pdf_sha256: str, sigs: list[PackageSignature], keys: list[str]) -> str:
    t = _EN if lang == "en" else _RU
    lines = [t["title"], "=" * len(t["title"]), "", t["intro"], "", t["sha"], f"  {pdf_sha256}", "", t["files"]]
    lines.append(f"  {pdf_name}")
    for s in sigs:
        who = f" ({t['signer']}: {s.signer})" if s.signer else ""
        lines.append(f"  {s.arcname}{who}")
    lines.extend(f"  {k}" for k in keys)
    lines.append("")
    if any(s.format is DetachedFormat.openpgp for s in sigs):
        lines += [t["pgp"], "  gpg --import public-key.*.asc"]
        lines += [f'  gpg --verify "{s.arcname}" "{pdf_name}"' for s in sigs if s.format is DetachedFormat.openpgp]
        lines += [t["pgp_hint"], ""]
    if any(s.format is DetachedFormat.cms for s in sigs):
        lines += [t["cms"]]
        lines += [
            f'  openssl cms -verify -inform DER -binary -noverify -in "{s.arcname}" -content "{pdf_name}"'
            " -out /dev/null"
            for s in sigs
            if s.format is DetachedFormat.cms
        ]
        lines += [t["cms_hint"], ""]
    return "\n".join(lines) + "\n"


def build_sign_instructions(lang: str, pdf_name: str, pdf_sha256: str) -> str:
    """README for whoever has to sign the frozen PDF outside the Studio."""
    if lang == "en":
        lines = [
            "Signing the PDF",
            "===============",
            "",
            f"File: {pdf_name}",
            f"SHA-256: {pdf_sha256}",
            "",
            "Create a DETACHED signature of this exact file and send the signature file back.",
            "Do not open and re-save the PDF: the signature covers it byte for byte.",
            "",
            "OpenPGP (GnuPG):",
            f'  gpg --armor --detach-sign "{pdf_name}"        # produces {pdf_name}.asc',
            "",
            "Qualified / non-qualified e-signature (CryptoARM, CryptoPro):",
            "  sign the file as a DETACHED signature (CMS / CAdES, a separate .sig file),",
            "  with the 'Detached signature' option enabled.",
            "",
        ]
    else:
        lines = [
            "Подпись PDF",
            "===========",
            "",
            f"Файл: {pdf_name}",
            f"SHA-256: {pdf_sha256}",
            "",
            "Нужно создать ОТКРЕПЛЕННУЮ подпись именно этого файла и вернуть файл подписи.",
            "Не открывайте и не пересохраняйте PDF: подпись покрывает файл побайтово.",
            "",
            "OpenPGP (GnuPG):",
            f'  gpg --armor --detach-sign "{pdf_name}"        # получится {pdf_name}.asc',
            "",
            "Усиленная квалифицированная или неквалифицированная ЭП (КриптоАРМ, КриптоПро):",
            "  подпишите файл как ОТКРЕПЛЕННУЮ подпись (CMS / CAdES, отдельный файл .sig),",
            "  с включенной опцией «Открепленная подпись».",
            "",
        ]
    return "\n".join(lines) + "\n"
