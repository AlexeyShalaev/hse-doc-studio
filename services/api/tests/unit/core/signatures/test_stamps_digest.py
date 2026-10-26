from __future__ import annotations

from pathlib import Path

from hse_doc_studio.core.signatures.stamps import Stamp, stamps_digest

# Значения посчитаны на коде до переноса Stamp в core: repr и дайджест нельзя менять,
# иначе у каждого зафиксированного документа сменится stamps_digest и плашка станет устаревшей.
_GOLDEN_REPR = (
    "[Stamp(page=1, x_mm=10.5, y_mm=20.0, width_mm=40.0, png_path=PosixPath('signatures/sup.png'), "
    "aspect_ratio=0.4, text=None, details=(), subtitle='', date_label='', date_text='12.05.2026'), "
    "Stamp(page=2, x_mm=15.0, y_mm=30.25, width_mm=80.0, png_path=None, aspect_ratio=0.4, "
    "text='Подписано с помощью открепленной электронной подписи', "
    "details=(('Сертификат', 'ABC123'), ('Владелец', 'Иванов Иван')), "
    "subtitle='Усиленная квалифицированная электронная подпись', date_label='Дата подписания', "
    "date_text='12.05.2026')]"
)
_GOLDEN_DIGEST = "a4335f262bf62b8696c6fbb3ca08baefb4fc2e3fb24cd47f4d7b4417eb8fc52a"


def test__stamp__repr_and_stamps_digest__golden_value_unchanged() -> None:
    stamps = [
        Stamp(
            page=1,
            x_mm=10.5,
            y_mm=20.0,
            width_mm=40.0,
            png_path=Path("signatures/sup.png"),
            aspect_ratio=0.4,
            date_text="12.05.2026",
        ),
        Stamp(
            page=2,
            x_mm=15.0,
            y_mm=30.25,
            width_mm=80.0,
            png_path=None,
            aspect_ratio=0.4,
            text="Подписано с помощью открепленной электронной подписи",
            details=(("Сертификат", "ABC123"), ("Владелец", "Иванов Иван")),
            subtitle="Усиленная квалифицированная электронная подпись",
            date_label="Дата подписания",
            date_text="12.05.2026",
        ),
    ]

    assert repr(stamps) == _GOLDEN_REPR
    assert stamps_digest(stamps) == _GOLDEN_DIGEST
