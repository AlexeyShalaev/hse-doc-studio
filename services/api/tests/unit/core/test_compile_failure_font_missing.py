from __future__ import annotations

from hse_doc_studio.core.compile.failure import FONT_MISSING, CompileFailure
from hse_doc_studio.core.enums import Lang


def test__font_missing__texts_point_to_settings_fonts_and_the_admin_options() -> None:
    failure = CompileFailure(FONT_MISSING, "Arial")

    ru = failure.message(Lang.ru)
    en = failure.message(Lang.en)

    assert "Настройки → Шрифты" in ru
    assert "HSE_RUNNER__FONTS_DIR" in ru
    assert "Settings → Fonts" in en
    assert "fonts_claim" in en
