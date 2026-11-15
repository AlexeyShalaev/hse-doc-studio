"""Пак и шаблон с нуля (template-studio.md, раздел 8): заготовка «Минимальный» проходит лоадер и линтер, копия
получает новые id и черновой манифест, ссылки в источнике отвергаются, отказ на полпути ничего не оставляет."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.scaffold import (
    Maintainer,
    NewPack,
    NewTemplate,
    ScaffoldSource,
    SourceOrigin,
    check_pack_id,
    check_template_id,
    clean_localized,
)
from hse_doc_studio.infra.pack_studio.check import check_version
from hse_doc_studio.infra.pack_studio.scaffold import PackScaffolder
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository

TODAY = date(2026, 11, 15)
_PACK = NewPack(
    id="my-pack",
    name={"ru": "Мой пак", "en": "My pack"},
    template=NewTemplate(id="report", name={"ru": "Отчёт", "en": "Report"}),
    maintainer=Maintainer("Автор Паков", "author@example.org"),
    source="https://git.example.org/packs",
)


def _scaffolder(max_files: int = 1000) -> PackScaffolder:
    return PackScaffolder(max_files=max_files, max_bytes=10 * 1024 * 1024)


def _source_pack(root: Path) -> Path:
    version = root / "src" / "templates" / "tpl" / "versions" / "2026.1.3"
    files = {
        root / "src" / "pack.yaml": 'id: src\nname: { ru: "Источник", en: "Source" }\nlicense: MIT\n'
        "maintainer: { name: Сопровождающий }\n",
        root
        / "src"
        / "templates"
        / "tpl"
        / "template.yaml": 'id: tpl\nicon: Book\naccent_hue: 30\nname: { ru: "Ш" }\n',
        root / "src" / "templates" / "tpl" / "examples" / "normal.yaml": 'name: "Тема"\n',
        version / "version.yaml": (
            '# комментарий источника\nid: "2026.1.3"\nreleased_at: 2026-01-01\nstatus: stable\n'
            "release:\n  kind: patch\nchanges:\n  ru: [старое]\n  en: [old]\ndocuments: [report]\n"
        ),
        version / "files" / "report" / "doc.yaml": "source_file: report/main.tex\n",
        version / "files" / "report" / "main.ru.tex": "\\documentclass{article}\n",
        version / "files" / "report" / ".DS_Store": "junk",
    }
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return version


def test__minimal__loads_and_passes_the_linter(tmp_path: Path) -> None:
    result = _scaffolder().create_pack(tmp_path, _PACK, version="2026.1", today=TODAY, source=None)

    version_dir = tmp_path / result.ref.dir
    assert check_version(version_dir).errors == 0
    repo = YamlTemplateRepository(tmp_path)
    version = repo.get_version("my-pack", "report", "2026.1")
    assert version is not None
    assert [d.id for d in version.documents] == ["report"]
    assert result.main_file == f"{result.ref.dir}/files/report/report.tex"
    manifest = yaml.safe_load((version_dir / "version.yaml").read_text(encoding="utf-8"))
    assert manifest["released_at"] == TODAY
    assert manifest["meta_fields"]["year"]["placeholder"] == "2027"
    pack = yaml.safe_load((tmp_path / "my-pack" / "pack.yaml").read_text(encoding="utf-8"))
    assert pack["source"] == "https://git.example.org/packs"
    assert pack["created_at"] == TODAY


def test__copy__new_ids_draft_manifest_examples_and_attribution(tmp_path: Path) -> None:
    _source_pack(tmp_path)
    scaffolder = _scaffolder()
    source = scaffolder.workspace_source(tmp_path, ScaffoldSource(SourceOrigin.workspace, "SRC", "tpl", "2026.1.3"))

    result = scaffolder.create_pack(tmp_path, _PACK, version="2026.1", today=TODAY, source=source)

    template_dir = tmp_path / "my-pack" / "templates" / "report"
    version_dir = template_dir / "versions" / "2026.1"
    text = (version_dir / "version.yaml").read_text(encoding="utf-8")
    manifest = yaml.safe_load(text)
    assert text.startswith("# комментарий источника\n")
    assert (manifest["id"], manifest["status"], manifest["released_at"]) == ("2026.1", "beta", TODAY)
    assert "release" not in manifest
    assert manifest["changes"]["ru"] == ["Первая версия шаблона: копия src/tpl 2026.1.3."]
    assert not (version_dir / "files" / "report" / ".DS_Store").exists()
    assert (template_dir / "examples" / "normal.yaml").is_file()
    template = yaml.safe_load((template_dir / "template.yaml").read_text(encoding="utf-8"))
    assert (template["icon"], template["accent_hue"], template["id"]) == ("Book", 30, "report")
    pack_text = (tmp_path / "my-pack" / "pack.yaml").read_text(encoding="utf-8")
    assert "лицензия MIT, сопровождающий Сопровождающий" in pack_text
    assert result.main_file == f"{result.ref.dir}/files/report/main.ru.tex"
    assert result.source == ScaffoldSource(SourceOrigin.workspace, "src", "tpl", "2026.1.3")


def test__copy__symlink_in_the_source__rejected_and_nothing_left(tmp_path: Path) -> None:
    version = _source_pack(tmp_path)
    (version / "files" / "secret").symlink_to("/etc")
    scaffolder = _scaffolder()
    source = scaffolder.workspace_source(tmp_path, ScaffoldSource(SourceOrigin.workspace, "src", "tpl", "2026.1.3"))

    with pytest.raises(PackStudioError) as caught:
        scaffolder.create_pack(tmp_path, _PACK, version="2026.1", today=TODAY, source=source)

    assert caught.value.code is PackStudioErrorCode.path_not_allowed
    assert sorted(p.name for p in tmp_path.iterdir()) == ["src"]


def test__copy__too_many_files__workspace_too_large(tmp_path: Path) -> None:
    _source_pack(tmp_path)
    scaffolder = _scaffolder(max_files=2)
    source = scaffolder.workspace_source(tmp_path, ScaffoldSource(SourceOrigin.workspace, "src", "tpl", "2026.1.3"))

    with pytest.raises(PackStudioError) as caught:
        scaffolder.create_template(
            tmp_path, "src", NewTemplate("other", {"ru": "Д"}), version="2026.1", today=TODAY, source=source
        )

    assert caught.value.code is PackStudioErrorCode.workspace_too_large
    assert sorted(p.name for p in (tmp_path / "src" / "templates").iterdir()) == ["tpl"]


def test__ids_taken_case_insensitively(tmp_path: Path) -> None:
    _source_pack(tmp_path)
    scaffolder = _scaffolder()
    pack = NewPack(id="src", name={"ru": "П", "en": "P"}, template=NewTemplate("t", {"ru": "Ш"}))

    with pytest.raises(PackStudioError) as pack_taken:
        scaffolder.create_pack(tmp_path, pack, version="2026.1", today=TODAY, source=None)
    with pytest.raises(PackStudioError) as template_taken:
        scaffolder.create_template(
            tmp_path, "src", NewTemplate("TPL", {"ru": "Ш"}), version="2026.1", today=TODAY, source=None
        )

    assert pack_taken.value.code is PackStudioErrorCode.pack_id_taken
    assert template_taken.value.code is PackStudioErrorCode.template_id_taken


@pytest.mark.parametrize("raw", ["", "My-Pack", "a--b", "-a", "a b", "a_b", "x" * 65, "../a"])
def test__pack_id__invalid(raw: str) -> None:
    with pytest.raises(PackStudioError) as caught:
        check_pack_id(raw)

    assert caught.value.code is PackStudioErrorCode.id_invalid


def test__template_id__underscore_allowed_and_names_fill_the_other_language() -> None:
    assert check_template_id(" vkr_2 ") == "vkr_2"
    assert clean_localized({"ru": "", "en": "Report"}, required=True, field_name="name") == {
        "ru": "Report",
        "en": "Report",
    }
    assert clean_localized({"ru": " "}, required=False, field_name="description") is None
