from __future__ import annotations

from hse_doc_studio.core.enums import DetachedFormat
from hse_doc_studio.core.signatures.package_text import (
    GuideDocument,
    GuideSignature,
    build_verify_guide,
    detached_signature_name,
    signer_display_name,
)


def test__detached_signature_name__document_signer_format() -> None:
    assert detached_signature_name("Заявка.pdf", "Петров Пётр", DetachedFormat.openpgp, ".asc") == (
        "Заявка.Петров_Пётр.openpgp.asc"
    )
    assert detached_signature_name("Заявка.pdf", "Petrov", DetachedFormat.cms, ".p7s") == "Заявка.Petrov.cades.p7s"
    assert signer_display_name("Иван Иванов <ivan@example.org>") == "Иван Иванов"


def test__verify_guide__mixed_document__graphic_marked_and_prefix_command() -> None:
    doc = GuideDocument(
        pdf="Заявка.pdf",
        sha256="f" * 64,
        base="Заявка.для-открепленных-подписей.pdf",
        base_sha256="b" * 64,
        base_size=1234,
        keys=("public-key.Иван_Иванов.asc",),
        signatures=(
            GuideSignature("image", "Академический руководитель", "Сидоров"),
            GuideSignature(
                "detached",
                "Автор",
                "Иван Иванов",
                "Заявка.для-открепленных-подписей.Иван_Иванов.openpgp.asc",
                DetachedFormat.openpgp,
                "Заявка.для-открепленных-подписей.pdf",
            ),
            GuideSignature("pades", "Научный руководитель", "Петров"),
        ),
    )

    text = build_verify_guide("ru", [doc])

    assert "Академический руководитель: графическая подпись (картинка, не ЭП), подписант: Сидоров" in text
    assert 'cmp -n 1234 "Заявка.для-открепленных-подписей.pdf" "Заявка.pdf"' in text
    assert 'gpg --verify "Заявка.для-открепленных-подписей.Иван_Иванов.openpgp.asc"' in text
    assert 'pyhanko sign validate --pretty-print "Заявка.pdf"' in text
    assert "f" * 64 in text
    assert "b" * 64 in text


def test__verify_guide__english() -> None:
    doc = GuideDocument(
        pdf="Application.pdf",
        sha256="",
        signatures=(GuideSignature("image", "Supervisor", "Petrov"),),
    )

    text = build_verify_guide("en", [doc])

    assert text.startswith("How to verify")
    assert "graphic signature (image, not an e-signature)" in text
    assert "SHA-256: \n" not in text
