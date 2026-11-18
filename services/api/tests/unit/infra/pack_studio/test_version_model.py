"""Модель версии для форм (срезы T11 и T12): находки лоадера и схемы, перевод, копия заготовки."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
from hse_doc_studio.core.pack_studio.model import ModelAction, ModelActionKind, ModelEditError
from hse_doc_studio.infra.pack_studio.version_model import PackVersionModel, _new_problems, _retarget_doc

VDIR = "p/templates/t/versions/2026.1.1"

_VERSION = """\
id: "2026.1.1"
langs: [ru, en]
documents:
  - report
meta_fields:
  year: { type: string, label: { ru: Год } }
forms:
  - id: survey
    sections:
      - id: main
        fields:
          - { id: q1, type: text }
"""


def _pack(root: Path, version: str = _VERSION) -> Path:
    vdir = root / VDIR
    (vdir / "files/report").mkdir(parents=True)
    (vdir / "version.yaml").write_text(version, encoding="utf-8")
    (vdir / "files/report/doc.yaml").write_text(
        "name: { ru: Отчёт }\nsource_file: report/main.tex\n", encoding="utf-8", newline="\n"
    )
    (vdir / "files/report/main.ru.tex").write_text("ru\n", encoding="utf-8")
    (vdir / "files/report/logo.png").write_bytes(b"\x89PNG")
    return root


def test__new_problems__shifted_indices_are_not_new() -> None:
    old = ["/forms/0/sections/0: the loader drops the section"]
    new = ["/forms/1/sections/0: the loader drops the section", "/meta_fields/x: bad"]

    assert _new_problems(old, new) == ["/meta_fields/x: bad"]


def test__check_edit__old_problems_do_not_block(tmp_path: Path) -> None:
    broken = _VERSION.replace("type: string", "type: number")
    root = _pack(tmp_path, broken)
    model = PackVersionModel()

    model.check_edit(root, VDIR, "version.yaml", broken, broken.replace("Год }", "Год, en: Year }"))

    with pytest.raises(ModelEditError, match="forms"):
        model.check_edit(root, VDIR, "version.yaml", broken, broken.replace("type: text", "type: slider"))


def test__check_edit__doc_manifest_schema(tmp_path: Path) -> None:
    root = _pack(tmp_path)
    before = (root / VDIR / "files/report/doc.yaml").read_text(encoding="utf-8")

    with pytest.raises(ModelEditError, match="scope"):
        PackVersionModel().check_edit(root, VDIR, "files/report/doc.yaml", before, before + "scope: team\n")


def test__describe__counts_loader_problems(tmp_path: Path) -> None:
    root = _pack(tmp_path, _VERSION.replace("type: string", "type: number"))

    model = PackVersionModel().describe(root, VDIR)

    assert any(p.startswith("/meta_fields/year") for p in model.problems)
    assert [(f.path, f.lang) for f in model.documents[0].files] == [
        ("report/logo.png", ""),
        ("report/main.ru.tex", "ru"),
    ]


def test__translation__binary_shared_file_on_request(tmp_path: Path) -> None:
    root = _pack(tmp_path)
    action = ModelAction(ModelActionKind.add_translation, document="report", lang="en", files=("report/logo.png",))

    changes = PackVersionModel().plan(root, VDIR, action)

    assert [(c.path.removeprefix(VDIR + "/"), c.content) for c in changes] == [
        ("files/report/logo.ru.png", b"\x89PNG"),
        ("files/report/logo.en.png", b"\x89PNG"),
        ("files/report/logo.png", None),
    ]


def test__retarget_doc__paths_of_the_copied_folder_and_variants() -> None:
    text = (
        "# Презентация\nid: pres\nname: { ru: П }\nsource_file: pres/beamer/p.tex\n"
        "variants:\n- id: pptx\n  source_file: pres/pptx/p.pptx\n  output_file: other/p.pptx\n"
    )

    out = _retarget_doc(text, "pres", "slides", {"ru": "Слайды"})

    assert out == (
        "# Презентация\nid: slides\nname: { ru: Слайды }\nsource_file: slides/beamer/p.tex\n"
        "variants:\n- id: pptx\n  source_file: slides/pptx/p.pptx\n  output_file: other/p.pptx\n"
    )


def test__add_document__source_outside_a_version_refused(tmp_path: Path) -> None:
    root = _pack(tmp_path)
    action = ModelAction(ModelActionKind.add_document, document="copy", source="p/templates/t")

    with pytest.raises(ModelEditError, match="not a document folder"):
        PackVersionModel().plan(root, VDIR, action)


_ASCII_PROBE = """
import sys
from pathlib import Path
from hse_doc_studio.core.pack_studio.model import ModelAction, ModelActionKind
from hse_doc_studio.infra.pack_studio.version_model import PackVersionModel

root, vdir = Path(sys.argv[1]), sys.argv[2]
model = PackVersionModel()
assert model.describe(root, vdir).documents
model.plan(root, vdir, ModelAction(ModelActionKind.add_translation, document="report", lang="en"))
"""


def test__model__reads_a_pack_with_cyrillic_in_a_non_utf8_locale(tmp_path: Path) -> None:
    """Windows (cp1252) и C-локаль: модель обязана читать паки в UTF-8, а не в кодировке системы."""
    root = _pack(tmp_path)
    env = {
        "PATH": "",
        "PYTHONUTF8": "0",
        "PYTHONCOERCECLOCALE": "0",
        "LC_ALL": "C",
        "PYTHONIOENCODING": "ascii",
    }
    done = subprocess.run(  # noqa: S603
        [sys.executable, "-X", "utf8=0", "-c", _ASCII_PROBE, str(root), VDIR],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert done.returncode == 0, done.stderr
