"""Юнит-тесты v2-суффикс-резолвера bundle-раскладки (см. template_renderer).

Отдельный файл от test_template_renderer.py: v1-оверлеи и их тесты не
затрагиваются.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.infra.project_init.template_renderer import (
    _split_lang_qualifier,
    collect_sources_suffixed,
)

LANGS = ("ru", "en")


@pytest.mark.parametrize(
    ("rel", "expected"),
    [
        ("operator_manual/operator_manual.ru.tex", ("operator_manual/operator_manual.tex", "ru")),
        ("operator_manual/operator_manual.en.tex", ("operator_manual/operator_manual.tex", "en")),
        ("operator_manual/ieee_1063.tex", ("operator_manual/ieee_1063.tex", "")),
        ("presentation/pptx/presentation.en.pptx", ("presentation/pptx/presentation.pptx", "en")),
        # предпоследний сегмент не из langs — не квалификатор
        ("common/meta.tex.j2", ("common/meta.tex.j2", "")),
        ("nda/nda.tex", ("nda/nda.tex", "")),
        ("top_level.ru.tex", ("top_level.tex", "ru")),
        # «de» не объявлен — имя остаётся литеральным, группа не трогается
        ("thesis/thesis.de.tex", ("thesis/thesis.de.tex", "")),
    ],
)
def test__split_lang_qualifier__parses_declared_codes_only(rel: str, expected: tuple[str, str]) -> None:
    assert _split_lang_qualifier(rel, LANGS) == expected


def _touch(root: Path, rel: str, content: str = "x") -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


def test__collect__picks_project_lang_with_default_fallback(tmp_path: Path) -> None:
    _touch(tmp_path, "doc/doc.ru.tex", "RU")
    _touch(tmp_path, "doc/doc.en.tex", "EN")
    _touch(tmp_path, "doc/only_ru.ru.tex", "RU-ONLY")
    _touch(tmp_path, "doc/neutral.tex", "NEUTRAL")

    en = collect_sources_suffixed(tmp_path, LANGS, "en")
    assert en["doc/doc.tex"].read_text(encoding="utf-8") == "EN"
    # нет en-редакции → фолбэк на дефолт (первый в langs)
    assert en["doc/only_ru.tex"].read_text(encoding="utf-8") == "RU-ONLY"
    assert en["doc/neutral.tex"].read_text(encoding="utf-8") == "NEUTRAL"

    ru = collect_sources_suffixed(tmp_path, LANGS, "ru")
    assert ru["doc/doc.tex"].read_text(encoding="utf-8") == "RU"


def test__collect__bare_file_serves_all_langs_and_doc_yaml_excluded(tmp_path: Path) -> None:
    _touch(tmp_path, "operator_manual/ieee_1063.tex", "IEEE")
    _touch(tmp_path, "operator_manual/doc.yaml", "id: operator_manual")

    for lang in ("ru", "en"):
        sources = collect_sources_suffixed(tmp_path, LANGS, lang)
        # ISO/IEEE-вариант без суффикса достаётся ЛЮБОМУ языку (lossless-переключение)
        assert sources["operator_manual/ieee_1063.tex"].read_text(encoding="utf-8") == "IEEE"
        # манифест bundle в проект не копируется
        assert "operator_manual/doc.yaml" not in sources


def test__collect__binary_pptx_resolved_like_text(tmp_path: Path) -> None:
    _touch(tmp_path, "presentation/pptx/presentation.ru.pptx", "RU-PPTX")
    _touch(tmp_path, "presentation/pptx/presentation.en.pptx", "EN-PPTX")

    en = collect_sources_suffixed(tmp_path, LANGS, "en")
    assert en["presentation/pptx/presentation.pptx"].read_text(encoding="utf-8") == "EN-PPTX"
    ru = collect_sources_suffixed(tmp_path, LANGS, "ru")
    assert ru["presentation/pptx/presentation.pptx"].read_text(encoding="utf-8") == "RU-PPTX"


def test__collect__orphan_translation_is_deterministic(tmp_path: Path) -> None:
    # Только en-редакция (нет ни дефолта, ни bare): ru-проект получает её же —
    # детерминированный фолбэк, «сироту» помечает pack lint.
    _touch(tmp_path, "doc/orphan.en.tex", "EN")
    ru = collect_sources_suffixed(tmp_path, LANGS, "ru")
    assert ru["doc/orphan.tex"].read_text(encoding="utf-8") == "EN"
