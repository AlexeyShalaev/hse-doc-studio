"""Тексты и имена файлов, которые едут вместе с зафиксированным PDF: подписи, ключи, README."""

from __future__ import annotations

import contextlib
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from hse_doc_studio.core.enums import DetachedFormat


@dataclass(frozen=True)
class PackageSignature:
    slot_label: str
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


def public_key_files(export_public: Callable[[str], bytes], sigs: Sequence[PackageSignature]) -> dict[str, bytes]:
    """`<name>.pub.asc` per distinct OpenPGP signer whose public key the exporter returns."""
    files: dict[str, bytes] = {}
    seen: set[str] = set()
    for s in sigs:
        if s.format is not DetachedFormat.openpgp or s.signer_id in seen:
            continue
        seen.add(s.signer_id)
        blob = b""
        with contextlib.suppress(Exception):
            blob = export_public(s.signer_id)
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


def build_readme(
    lang: str, pdf_name: str, pdf_sha256: str, sigs: Sequence[PackageSignature], keys: Sequence[str]
) -> str:
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


def embedded_note(lang: str, final_name: str, final_sha256: str, base_name: str, base_size: int) -> str:
    """Абзац README пакета, когда на PDF есть встроенные подписи PAdES: какой файл итоговый, какой для открепленных."""
    if lang == "en":
        lines = [
            "Embedded signatures (PAdES)",
            f"  {final_name}: the final PDF with embedded electronic signatures.",
            f"  SHA-256: {final_sha256}",
            f"  {base_name}: the same bytes before the embedded signatures (the first {base_size} bytes",
            f"  of {final_name}); detached signatures cover this file.",
            "  The embedded signatures are checked in the Adobe Acrobat Reader signature panel or with",
            f'  pyhanko sign validate --pretty-print "{final_name}"',
            f'  cmp -n {base_size} "{base_name}" "{final_name}"',
        ]
    else:
        lines = [
            "Встроенные подписи (PAdES)",
            f"  {final_name}: итоговый PDF со встроенными электронными подписями.",
            f"  SHA-256: {final_sha256}",
            f"  {base_name}: те же байты до встроенных подписей (первые {base_size} байт {final_name}),",
            "  открепленные подписи относятся к нему.",
            "  Встроенные подписи проверяют в панели подписей Adobe Acrobat Reader или командой",
            f'  pyhanko sign validate --pretty-print "{final_name}"',
            f'  cmp -n {base_size} "{base_name}" "{final_name}"',
        ]
    return "\n".join(lines) + "\n"


# --- КАК_ПРОВЕРИТЬ.txt: одна инструкция на весь комплект (docs/design/signature-plan.md, раздел 8) ---------------

VERIFY_GUIDE_NAME = {"ru": "КАК_ПРОВЕРИТЬ.txt", "en": "HOW_TO_VERIFY.txt"}
BASE_SUFFIX = {"ru": "для-открепленных-подписей", "en": "for-detached-signatures"}
FORMAT_TOKEN = {DetachedFormat.openpgp: "openpgp", DetachedFormat.cms: "cades"}


@dataclass(frozen=True)
class GuideSignature:
    kind: str  # "image" | "detached" | "pades"
    label: str  # слот («Научный руководитель»)
    signer: str
    file: str = ""  # файл открепленной подписи; пусто у картинки и PAdES
    format: DetachedFormat | None = None
    covers: str = ""  # PDF, к которому относится открепленная подпись


@dataclass(frozen=True)
class GuideDocument:
    pdf: str  # итоговый PDF в комплекте
    sha256: str
    signatures: tuple[GuideSignature, ...]
    base: str = ""  # PDF для открепленных подписей, когда он отличается от итогового
    base_sha256: str = ""
    base_size: int = 0
    keys: tuple[str, ...] = ()


def signer_display_name(raw: str) -> str:
    """Имя подписанта без адреса почты: «Иван Иванов <ivan@example.org>» → «Иван Иванов» (uid OpenPGP)."""
    return raw.split("<", 1)[0].strip() or raw.strip()


def signer_file_token(name: str) -> str:
    """«Петров Пётр Петрович» → «Петров_Пётр_Петрович» для имени файла подписи."""
    return slug(name)


def detached_signature_name(pdf_name: str, signer: str, fmt: DetachedFormat, ext: str) -> str:
    """`Заявка.pdf` + «Петров П. П.» + OpenPGP → `Заявка.Петров_П._П.openpgp.asc`: документ, подписант, формат."""
    stem = pdf_name.rsplit(".", 1)[0] if "." in pdf_name else pdf_name
    return f"{stem}.{signer_file_token(signer)}.{FORMAT_TOKEN[fmt]}{ext}"


_GUIDE_RU = {
    "title": "Как проверить подписи комплекта",
    "intro": (
        "Электронные подписи (ЭП) проверяются без Студии стандартными средствами. Графическая подпись это\n"
        "картинка на странице: она не является электронной подписью и криптографически не проверяется.\n"
        "Любое изменение PDF, даже пересохранение, делает электронные подписи недействительными."
    ),
    "sha": "SHA-256",
    "image": "графическая подпись (картинка, не ЭП)",
    "detached": "открепленная ЭП",
    "pades": "встроенная ЭП (PAdES) внутри PDF",
    "signer": "подписант",
    "file": "файл подписи",
    "covers": "относится к",
    "base": (
        "{base} это исходные байты {pdf} до встроенных подписей: открепленные подписи относятся к нему.\n"
        "  Его содержимое совпадает с началом {pdf} (первые {size} байт):"
    ),
    "pgp": "Открепленные OpenPGP (.asc):",
    "cms": "Открепленные CAdES/CMS (.p7s, .sig); ГОСТ проверяют в КриптоАРМ, КриптоПро или на Госуслугах:",
    "pades_tools": "Встроенные подписи PAdES: панель подписей Adobe Acrobat Reader или pyHanko (pyhanko-cli):",
}
_GUIDE_EN = {
    "title": "How to verify the signatures of this submission",
    "intro": (
        "Electronic signatures are verified without the Studio with standard tools. A graphic signature is\n"
        "an image on the page: it is not an electronic signature and cannot be checked cryptographically.\n"
        "Any change to a PDF, even re-saving it, invalidates its electronic signatures."
    ),
    "sha": "SHA-256",
    "image": "graphic signature (image, not an e-signature)",
    "detached": "detached e-signature",
    "pades": "embedded e-signature (PAdES) inside the PDF",
    "signer": "signer",
    "file": "signature file",
    "covers": "covers",
    "base": (
        "{base} holds the bytes of {pdf} before the embedded signatures: detached signatures cover it.\n"
        "  Its content equals the beginning of {pdf} (the first {size} bytes):"
    ),
    "pgp": "Detached OpenPGP (.asc):",
    "cms": "Detached CAdES/CMS (.p7s, .sig); GOST is verified in CryptoARM, CryptoPro or the Gosuslugi portal:",
    "pades_tools": (
        "Embedded PAdES signatures: the signature panel of Adobe Acrobat Reader or pyHanko (pip install pyhanko-cli):"
    ),
}


def _doc_lines(t: dict[str, str], doc: GuideDocument) -> list[str]:
    lines = [doc.pdf] + ([f"  {t['sha']}: {doc.sha256}"] if doc.sha256 else [])
    if doc.base:
        lines.append(f"  {doc.base}")
        lines.append(f"  {t['sha']}: {doc.base_sha256}")
    for sig in doc.signatures:
        who = f", {t['signer']}: {sig.signer}" if sig.signer else ""
        lines.append(f"  - {sig.label}: {t[sig.kind]}{who}")
        if sig.file:
            lines.append(f"    {t['file']}: {sig.file}, {t['covers']}: {sig.covers}")
    if doc.base:
        lines.append("  " + t["base"].format(base=doc.base, pdf=doc.pdf, size=doc.base_size))
        lines.append(f'    cmp -n {doc.base_size} "{doc.base}" "{doc.pdf}"')
    return lines


def build_verify_guide(lang: str, docs: Sequence[GuideDocument]) -> str:
    t = _GUIDE_EN if lang == "en" else _GUIDE_RU
    lines = [t["title"], "=" * len(t["title"]), "", t["intro"], ""]
    for doc in docs:
        lines += [*_doc_lines(t, doc), ""]
    sigs = [s for d in docs for s in d.signatures]
    keys = sorted({k for d in docs for k in d.keys})
    pgp = [s for s in sigs if s.format is DetachedFormat.openpgp]
    if pgp:
        lines.append(t["pgp"])
        lines += [f'  gpg --import "{k}"' for k in keys]
        lines += [f'  gpg --verify "{s.file}" "{s.covers}"' for s in pgp]
        lines.append("")
    cms = [s for s in sigs if s.format is DetachedFormat.cms]
    if cms:
        lines.append(t["cms"])
        lines += [
            f'  openssl cms -verify -inform DER -binary -noverify -in "{s.file}" -content "{s.covers}" -out /dev/null'
            for s in cms
        ]
        lines.append("")
    pades_docs = [d.pdf for d in docs if any(s.kind == "pades" for s in d.signatures)]
    if pades_docs:
        lines.append(t["pades_tools"])
        lines += [f'  pyhanko sign validate --pretty-print "{pdf}"' for pdf in pades_docs]
        lines.append("")
    return "\n".join(lines)
