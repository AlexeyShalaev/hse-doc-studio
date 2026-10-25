from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.core.enums import TemplateUpdateClass
from hse_doc_studio.infra.template.releases import (
    check_template,
    freeze,
    load_releases,
    main,
    version_digest,
)

_REPO_PACKS = Path(__file__).resolve().parents[6] / "packs"


def _make_template(tmp_path: Path, status: str = "stable") -> Path:
    template_dir = tmp_path / "tmpl"
    version_dir = template_dir / "versions" / "2026.1"
    (version_dir / "files" / "doc").mkdir(parents=True)
    (version_dir / "version.yaml").write_text(f'id: "2026.1"\nstatus: {status}\n', encoding="utf-8", newline="\n")
    (version_dir / "files" / "doc" / "doc.tex").write_text("\\section{Введение}\n", encoding="utf-8", newline="\n")
    return template_dir


def test__version_digest__ignores_line_endings_of_text_files(tmp_path: Path) -> None:
    template_dir = _make_template(tmp_path)
    version_dir = template_dir / "versions" / "2026.1"
    before = version_digest(version_dir)

    tex = version_dir / "files" / "doc" / "doc.tex"
    tex.write_bytes(tex.read_bytes().replace(b"\n", b"\r\n"))

    assert version_digest(version_dir) == before


def test__version_digest__changes_with_content_and_ignores_junk(tmp_path: Path) -> None:
    version_dir = _make_template(tmp_path) / "versions" / "2026.1"
    before = version_digest(version_dir)

    (version_dir / ".DS_Store").write_bytes(b"\x00junk")
    assert version_digest(version_dir) == before

    (version_dir / "files" / "doc" / "doc.tex").write_text("\\section{Intro}\n", encoding="utf-8", newline="\n")
    assert version_digest(version_dir) != before


def test__freeze__then_check_detects_in_place_edit(tmp_path: Path) -> None:
    template_dir = _make_template(tmp_path)

    entry = freeze(template_dir, "2026.1", TemplateUpdateClass.major)

    assert load_releases(template_dir) == {"2026.1": entry}
    assert check_template(template_dir) == []

    (template_dir / "versions" / "2026.1" / "files" / "doc" / "doc.tex").write_text(
        "правка\n", encoding="utf-8", newline="\n"
    )
    errors = check_template(template_dir)
    assert len(errors) == 1
    assert "изменён" in errors[0]


def test__freeze__refuses_beta_and_double_release(tmp_path: Path) -> None:
    beta = _make_template(tmp_path / "beta", status="beta")
    with pytest.raises(ValueError, match="stable"):
        freeze(beta, "2026.1")

    stable = _make_template(tmp_path / "stable")
    freeze(stable, "2026.1")
    with pytest.raises(ValueError, match="уже выпущена"):
        freeze(stable, "2026.1")


def test__check__missing_released_dir_is_an_error(tmp_path: Path) -> None:
    template_dir = _make_template(tmp_path)
    freeze(template_dir, "2026.1")
    (template_dir / "versions" / "2026.1" / "version.yaml").unlink()
    (template_dir / "versions" / "2026.1" / "files" / "doc" / "doc.tex").unlink()
    (template_dir / "versions" / "2026.1" / "files" / "doc").rmdir()
    (template_dir / "versions" / "2026.1" / "files").rmdir()
    (template_dir / "versions" / "2026.1").rmdir()

    assert "отсутствует" in check_template(template_dir)[0]


def test__cli__check_exit_code(tmp_path: Path) -> None:
    template_dir = _make_template(tmp_path)
    assert main(["freeze", str(template_dir), "2026.1"]) == 0
    assert main(["check", str(template_dir)]) == 0
    (template_dir / "versions" / "2026.1" / "version.yaml").write_text(
        'id: "2026.1"\n# правка\n', encoding="utf-8", newline="\n"
    )
    assert main(["check", str(template_dir)]) == 1


def test__repository_packs__released_versions_are_unchanged() -> None:
    """Выпущенные версии паков репозитория не правят на месте.

    Падение здесь значит: каталог версии из releases.yaml изменён. Проекты
    студентов читают его манифест вживую — правка молча поменяла бы их
    требования. Верните каталог и выпустите исправление новой версией.
    """
    template_dirs = sorted(p for p in _REPO_PACKS.glob("*/templates/*") if p.is_dir())
    assert template_dirs, "в репозитории не найдено ни одного шаблона"
    errors = [error for template_dir in template_dirs for error in check_template(template_dir)]
    assert errors == []
