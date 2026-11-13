from __future__ import annotations

from dataclasses import replace

from hse_doc_studio.core.enums import DetachedFormat
from hse_doc_studio.core.signatures.package_text import (
    GuideDocument,
    GuideSignature,
    build_verify_guide,
    detached_signature_name,
    signer_display_name,
    version_date,
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


def test__verify_guide__document_from_pinned_version__version_line_under_its_pdf() -> None:
    doc = GuideDocument(
        pdf="Заявка.pdf",
        sha256="f" * 64,
        signatures=(GuideSignature("pades", "Научный руководитель", "Петров"),),
        version_date=version_date("2026-11-10T14:32:00+00:00"),
        version_sha256="a" * 64,
    )

    ru = build_verify_guide("ru", [doc]).splitlines()
    en = build_verify_guide("en", [replace(doc, pdf="Application.pdf")]).splitlines()

    at = ru.index("Заявка.pdf")
    assert ru[at + 1 : at + 3] == [
        f"  SHA-256: {'f' * 64}",
        f"  Версия от 10.11.2026, SHA-256 исходного PDF {'a' * 64}",
    ]
    assert f"  Version of 10.11.2026, SHA-256 of the source PDF {'a' * 64}" in en


def test__verify_guide__document_without_pinned_version__no_version_line() -> None:
    doc = GuideDocument(pdf="Заявка.pdf", sha256="f" * 64, signatures=(GuideSignature("pades", "Руководитель", ""),))

    assert "Версия от" not in build_verify_guide("ru", [doc])


def test__version_date__iso_utc_to_day_and_unparsable_kept() -> None:
    assert version_date("2026-11-10T14:32:00Z") == "10.11.2026"
    assert version_date("10 ноября") == "10 ноября"


def test__version_date__moscow_day_not_utc_day() -> None:
    """Версия, снятая в 23:30 по Москве (20:30 UTC), и снятая после полуночи по Москве (21:30 UTC прошлого дня
    по UTC): дата как в интерфейсе, по московскому времени."""
    assert version_date("2026-11-10T20:30:00+00:00") == "10.11.2026"
    assert version_date("2026-11-10T21:30:00+00:00") == "11.11.2026"
    assert version_date("2026-11-10T21:30:00") == "11.11.2026"


def test__verify_guide__date_on_the_page_and_signing_time_under_the_signature() -> None:
    """Дата на странице это согласие, время подписи из самой ЭП: видно, что подпись поставлена позже (14.8)."""
    doc = GuideDocument(
        pdf="Описание.pdf",
        sha256="f" * 64,
        signatures=(
            GuideSignature("image", "Научный руководитель", "Петров", page_date="13.11.2026"),
            GuideSignature(
                "detached",
                "Автор",
                "Иванов",
                "Описание.Иванов.openpgp.asc",
                DetachedFormat.openpgp,
                "Описание.pdf",
                page_date="13.11.2026",
                signing_time="14.11.2026 10:05",
            ),
            GuideSignature("pades", "Академический руководитель", "Сидоров", signing_time="15.11.2026 09:00"),
            GuideSignature("skipped", "Соруководитель", ""),
        ),
    )

    ru = build_verify_guide("ru", [doc]).splitlines()
    en = build_verify_guide("en", [doc]).splitlines()

    at = ru.index("  - Автор: открепленная ЭП, подписант: Иванов")
    assert ru[at + 1 : at + 4] == [
        "    дата на странице: 13.11.2026",
        "    время подписи: 14.11.2026 10:05",
        "    файл подписи: Описание.Иванов.openpgp.asc, относится к: Описание.pdf",
    ]
    image = ru.index("  - Научный руководитель: графическая подпись (картинка, не ЭП), подписант: Петров")
    assert ru[image + 1] == "    дата на странице: 13.11.2026"
    skipped = ru.index("  - Соруководитель: не требуется (пропущено автором)")
    assert not ru[skipped + 1].startswith("    дата")
    assert "    date on the page: 13.11.2026" in en
    assert "    signing time: 15.11.2026 09:00" in en
