"""Рендер предпросмотра в песочнице: копия пака без ссылок, синтетический проект тем же кодом, что создание проекта."""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.pack_studio.errors import PackStudioError
from hse_doc_studio.core.pack_studio.paths import VersionRef
from hse_doc_studio.core.pack_studio.preview import (
    MaterializeRequest,
    PreviewExample,
    PreviewRenderError,
    auto_examples,
    parse_example,
    resolve_combination,
    switches_for,
    synthetic_project,
)
from hse_doc_studio.infra.pack_studio.preview_renderer import PackPreviewRenderer, PreviewRenderLimits
from hse_doc_studio.infra.pack_studio.preview_worker import (
    StageLimits,
    VersionDirs,
    describe_version,
    materialize_preview,
)

LIMITS = StageLimits(max_bytes=10 * 1024 * 1024, max_files=1000)
TODAY = date(2026, 11, 15)

_VERSION = """\
id: "1.0.0"
langs: [ru, en]
supported_staffing: [solo, team]
meta_fields:
  stage: { type: select, label: { ru: "Этап" }, options: ["Первый", "Второй"] }
dynamic_includes:
  - { template: common/meta.tex.j2, output: common/meta.tex }
documents:
  - { id: report, name: { ru: "Отчёт" }, source_file: report/report.tex, output_file: report/report.pdf }
  - id: personal
    name: { ru: "Личный" }
    source_file: personal/personal.tex
    output_file: personal/personal.pdf
    scope: personal
"""

_META = (
    "title={{ project.name | texesc }}\n"
    "stage={{ project.meta.stage }}\n"
    "author={{ author.name }}\n"
    "lang={{ project.lang }}\n"
)


def _pack(root: Path, *, pack_dir: str = "pack-dir", version_yaml: str = _VERSION) -> VersionDirs:
    version = root / pack_dir / "templates" / "tpl" / "versions" / "1.0.0"
    files = {
        root / pack_dir / "pack.yaml": "id: demo\n",
        root / pack_dir / "templates" / "tpl" / "template.yaml": "id: report\n",
        version / "version.yaml": version_yaml,
        version / "files" / "common" / "meta.tex.j2": _META,
        version / "files" / "report" / "report.tex": "\\documentclass{article}\n% {{ project.name }}\n",
        version / "files" / "personal" / "personal.tex": "\\documentclass{article}\n",
        root / pack_dir / "templates" / "tpl" / "examples" / "mine.yaml": 'name: "Своя тема"\nstaffing: team2\n',
        root / pack_dir / "templates" / "tpl" / "examples" / "bomb.yaml": (
            "a: &a [x, x, x, x, x, x, x, x, x, x]\nb: &b [*a, *a, *a, *a, *a, *a, *a, *a, *a, *a]\n"
            "c: &c [*b, *b, *b, *b, *b, *b, *b, *b, *b, *b]\nd: &d [*c, *c, *c, *c, *c, *c, *c, *c, *c, *c]\n"
            "e: [*d, *d, *d, *d, *d, *d, *d, *d, *d, *d]\n"
        ),
    }
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return VersionDirs(str(root), pack_dir, "tpl", "1.0.0")


def _request(dirs: VersionDirs, stage: Path, def_id: str = "report", **combo: str) -> MaterializeRequest:
    desc = describe_version(dirs, str(stage / "describe"), LIMITS)
    example = next(e for e in auto_examples(desc.version) if e.id == "auto:normal")
    project = synthetic_project(
        desc.version, example, resolve_combination(switches_for(desc.version), combo), date(2026, 11, 15)
    )
    return MaterializeRequest(desc.pack_id, desc.template_id, desc.version.version, def_id, project, uuid4())


def test__describe__ids_from_manifests_and_examples_bounded(tmp_path: Path) -> None:
    dirs = _pack(tmp_path / "packs")

    desc = describe_version(dirs, str(tmp_path / "stage"), LIMITS)

    assert (desc.pack_id, desc.template_id, desc.version.version) == ("demo", "report", "1.0.0")
    examples = {e.id: e for e in desc.examples}
    assert parse_example(examples["mine"].data).defaults == {"staffing": "team2"}
    assert examples["bomb"].data is None
    assert examples["bomb"].error == "пример слишком большой"


def test__materialize__renders_dynamic_includes_and_resolves_source(tmp_path: Path) -> None:
    dirs = _pack(tmp_path / "packs")
    dest = tmp_path / "work"

    doc = materialize_preview(
        dirs, str(tmp_path / "stage"), LIMITS, _request(dirs, tmp_path, **{"meta.stage": "Второй"}), str(dest)
    )

    assert (doc.doc_id, doc.source_file, doc.engine, doc.needs_compile) == (
        "report",
        "report/report.tex",
        "xelatex",
        True,
    )
    meta = (dest / "common" / "meta.tex").read_text(encoding="utf-8")
    assert "stage=Второй\n" in meta
    assert "author=Иванов Иван Иванович\n" in meta
    assert "Контур согласования" in (dest / "report" / "report.tex").read_text(encoding="utf-8")
    assert doc.warnings == ()


def test__materialize__team_personal_document_lives_in_author_base(tmp_path: Path) -> None:
    dirs = _pack(tmp_path / "packs")
    dest = tmp_path / "work"

    doc = materialize_preview(
        dirs, str(tmp_path / "stage"), LIMITS, _request(dirs, tmp_path, "personal", staffing="team2"), str(dest)
    )

    slug = doc.source_file.split("/", 1)[0]
    assert doc.doc_id == f"personal--{slug}"
    assert doc.base_dir == slug
    assert (dest / slug / "common" / "meta.tex").is_file()
    assert (dest / "shared" / "report" / "report.tex").is_file()


def test__materialize__jinja_error__copied_as_is_with_a_warning(tmp_path: Path) -> None:
    dirs = _pack(tmp_path / "packs")
    report = Path(dirs.version_dir) / "files" / "report" / "report.tex"
    report.write_text("{{ project.name ", encoding="utf-8")

    doc = materialize_preview(dirs, str(tmp_path / "stage"), LIMITS, _request(dirs, tmp_path), str(tmp_path / "w"))

    assert any("jinja2 syntax error" in line for line in doc.warnings)


@pytest.mark.skipif(sys.platform == "win32", reason="символьные ссылки")
def test__materialize__symlinks_in_the_pack_are_not_followed(tmp_path: Path) -> None:
    dirs = _pack(tmp_path / "packs")
    secret = tmp_path / "secret.txt"
    secret.write_text("TOKEN", encoding="utf-8")
    os.symlink(secret, Path(dirs.version_dir) / "files" / "report" / "leak.tex")
    dest = tmp_path / "work"

    materialize_preview(dirs, str(tmp_path / "stage"), LIMITS, _request(dirs, tmp_path), str(dest))

    assert not (dest / "report" / "leak.tex").exists()
    assert all("TOKEN" not in p.read_text(encoding="utf-8", errors="ignore") for p in dest.rglob("*") if p.is_file())


def test__stage__manifest_id_with_path_parts__rejected(tmp_path: Path) -> None:
    dirs = _pack(tmp_path / "packs")
    (Path(dirs.pack_dir) / "pack.yaml").write_text("id: ../../escape\n", encoding="utf-8")

    with pytest.raises(ValueError, match="недопустимый id"):
        describe_version(dirs, str(tmp_path / "stage"), LIMITS)


def test__stage__too_large_version__rejected(tmp_path: Path) -> None:
    dirs = _pack(tmp_path / "packs")

    with pytest.raises(ValueError, match="слишком большой"):
        describe_version(dirs, str(tmp_path / "stage"), StageLimits(max_bytes=10, max_files=1000))


def _renderer(tmp_path: Path, *, timeout_s: float = 30.0) -> PackPreviewRenderer:
    limits = PreviewRenderLimits(
        describe_timeout_s=timeout_s, materialize_timeout_s=timeout_s, memory_bytes=512 * 1024 * 1024, stage=LIMITS
    )
    return PackPreviewRenderer(tmp_path / "tmp", limits)


async def test__renderer__isolated_process_round_trip_and_cleans_its_stage(tmp_path: Path) -> None:
    root = tmp_path / "packs"
    _pack(root)
    ref = VersionRef("pack-dir", "tpl", "1.0.0")
    renderer = _renderer(tmp_path)

    desc = await renderer.describe(root, ref)
    example = PreviewExample("mine", "file", None, parse_example({"name": "Тема"}))
    project = synthetic_project(desc.version, example, resolve_combination(switches_for(desc.version), {}), TODAY)
    request = MaterializeRequest(desc.pack_id, desc.template_id, "1.0.0", "report", project, uuid4())
    doc = await renderer.materialize(root, ref, request, tmp_path / "work")

    assert doc.source_file == "report/report.tex"
    assert list((tmp_path / "tmp").iterdir()) == []


async def test__renderer__unreadable_version_and_failed_render_are_typed(tmp_path: Path) -> None:
    root = tmp_path / "packs"
    dirs = _pack(root)
    ref = VersionRef("pack-dir", "tpl", "1.0.0")
    renderer = _renderer(tmp_path)
    desc = await renderer.describe(root, ref)
    example = next(e for e in auto_examples(desc.version) if e.id == "auto:normal")
    project = synthetic_project(desc.version, example, resolve_combination(switches_for(desc.version), {}), TODAY)
    (Path(dirs.version_dir) / "files" / "report" / "report.tex").unlink()

    with pytest.raises(PreviewRenderError, match="исходник документа"):
        await renderer.materialize(
            root, ref, MaterializeRequest("demo", "report", "1.0.0", "report", project, uuid4()), tmp_path / "w"
        )
    (Path(dirs.version_dir) / "version.yaml").write_text("id: [\n", encoding="utf-8")
    with pytest.raises(PackStudioError) as caught:
        await renderer.describe(root, ref)
    assert caught.value.code.value == "version_unreadable"


async def test__renderer__inputs__hash_files_and_skip_links(tmp_path: Path) -> None:
    root = tmp_path / "packs"
    dirs = _pack(root)
    ref = VersionRef("pack-dir", "tpl", "1.0.0")
    renderer = _renderer(tmp_path)

    first = await renderer.inputs(root, ref)
    (Path(dirs.template_dir) / "examples" / "mine.yaml").write_text("name: x\n", encoding="utf-8")
    second = await renderer.inputs(root, ref)

    assert "files/report/report.tex" in first.files
    assert first.files == second.files
    assert first.tree != second.tree
    assert any(item.startswith("pack.yaml:") for item in first.extra)
