from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path, PurePosixPath, PureWindowsPath

from hse_doc_studio.core.signatures.plan import DocFacts
from hse_doc_studio.core.signatures.stamps import (
    Stamp,
    legacy_stamps_digest,
    stamps_digest,
    stamps_digest_matches,
)

# Значения посчитаны на коде до переноса Stamp в core: repr и прежний дайджест нельзя менять, иначе у каждой
# фиксации, сделанной до перехода на относительные пути, сменится stamps_digest и плашка станет устаревшей.
_GOLDEN_REPR = (
    "[Stamp(page=1, x_mm=10.5, y_mm=20.0, width_mm=40.0, png_path=PosixPath('signatures/sup.png'), "
    "aspect_ratio=0.4, text=None, details=(), subtitle='', date_label='', date_text='12.05.2026'), "
    "Stamp(page=2, x_mm=15.0, y_mm=30.25, width_mm=80.0, png_path=None, aspect_ratio=0.4, "
    "text='Подписано с помощью открепленной электронной подписи', "
    "details=(('Сертификат', 'ABC123'), ('Владелец', 'Иванов Иван')), "
    "subtitle='Усиленная квалифицированная электронная подпись', date_label='Дата подписания', "
    "date_text='12.05.2026')]"
)
_GOLDEN_LEGACY_DIGEST = "a4335f262bf62b8696c6fbb3ca08baefb4fc2e3fb24cd47f4d7b4417eb8fc52a"
# Отпечаток тех же меток, когда картинка лежит в проекте по пути signatures/sup.png. Он не зависит ни от ОС, ни от
# того, где лежит папка проекта; менять его тоже нельзя, иначе устареют фиксации, сделанные с ним.
_GOLDEN_DIGEST = "264b873f5a2131557614554d1320b24f8cc4886a245f3816a914892ae30f0b91"


def _stamps(png: Path | PurePosixPath | PureWindowsPath | None) -> list[Stamp]:
    return [
        Stamp(
            page=1,
            x_mm=10.5,
            y_mm=20.0,
            width_mm=40.0,
            png_path=png,  # type: ignore[arg-type]  # чистые пути Windows и POSIX нужны для проверки на любой ОС
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


def test__stamp__repr_and_legacy_digest__golden_value_unchanged() -> None:
    stamps = _stamps(Path("signatures/sup.png"))

    assert repr(stamps).replace("WindowsPath", "PosixPath") == _GOLDEN_REPR  # класс пути зависит от ОС
    if sys.platform != "win32":  # прежний дайджест берётся от repr(), где класс пути зависит от ОС
        assert legacy_stamps_digest(stamps) == _GOLDEN_LEGACY_DIGEST


def test__stamps_digest__golden_value_on_this_os(tmp_path: Path) -> None:
    root = tmp_path / "project"

    assert stamps_digest(_stamps(root / "signatures" / "sup.png"), root) == _GOLDEN_DIGEST


def test__stamps_digest__windows_and_posix_projects__same_digest() -> None:
    # Проверяется на любой ОС: разделители и буква диска Windows не попадают в отпечаток.
    win_root = PureWindowsPath("C:/Users/student/Documents/proj")
    posix_root = PurePosixPath("/var/lib/hse-doc-studio/projects/1dfc2e05")

    on_windows = stamps_digest(_stamps(win_root / "signatures" / "sup.png"), win_root)
    on_posix = stamps_digest(_stamps(posix_root / "signatures" / "sup.png"), posix_root)

    assert on_windows == on_posix == _GOLDEN_DIGEST


def test__stamps_digest__project_moved__digest_unchanged_legacy_changed(tmp_path: Path) -> None:
    old_root, new_root = tmp_path / "home" / "proj", tmp_path / "data" / "projects" / "1dfc"
    before, after = _stamps(old_root / "signatures" / "sup.png"), _stamps(new_root / "signatures" / "sup.png")

    assert stamps_digest(before, old_root) == stamps_digest(after, new_root)
    assert legacy_stamps_digest(before) != legacy_stamps_digest(after)


def test__stamps_digest__other_image_or_position__digest_changes(tmp_path: Path) -> None:
    stamps = _stamps(tmp_path / "signatures" / "sup.png")
    base = stamps_digest(stamps, tmp_path)

    assert stamps_digest(_stamps(tmp_path / "signatures" / "author.png"), tmp_path) != base
    assert stamps_digest([replace(stamps[0], x_mm=11.0), stamps[1]], tmp_path) != base
    assert stamps_digest([stamps[0], replace(stamps[1], details=())], tmp_path) != base


def test__stamps_digest_matches__legacy_form_of_unmoved_project__accepted(tmp_path: Path) -> None:
    stamps = _stamps(tmp_path / "signatures" / "sup.png")

    assert stamps_digest_matches(legacy_stamps_digest(stamps), stamps, tmp_path)
    assert stamps_digest_matches(stamps_digest(stamps, tmp_path), stamps, tmp_path)
    assert stamps_digest_matches("", stamps, tmp_path)  # фиксации до появления отпечатков


def test__stamps_digest_matches__changed_marks__rejected_in_both_forms(tmp_path: Path) -> None:
    stamps = _stamps(tmp_path / "signatures" / "sup.png")
    changed = _stamps(tmp_path / "signatures" / "other.png")

    assert not stamps_digest_matches(legacy_stamps_digest(stamps), changed, tmp_path)
    assert not stamps_digest_matches(stamps_digest(stamps, tmp_path), changed, tmp_path)


def test__doc_facts__marks_match__accepts_current_legacy_and_empty_only() -> None:
    facts = DocFacts(compiled_sha256=None, marks_digest="n" * 64, legacy_marks_digest="l" * 64)

    assert facts.marks_match("n" * 64)
    assert facts.marks_match("l" * 64)
    assert facts.marks_match("")
    assert not facts.marks_match("x" * 64)
    assert not DocFacts(compiled_sha256=None, marks_digest="n" * 64).marks_match("l" * 64)
