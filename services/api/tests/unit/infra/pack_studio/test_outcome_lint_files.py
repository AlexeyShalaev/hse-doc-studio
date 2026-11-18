"""Правила линтера результата по файлам (срез O8): `jinja-fail-open` и `jinja-unknown-meta-key`.

Шаблон, который падает при рендере, загрузчик проекта молча копирует как есть; правило ловит это строгим рендером на
пробах «пусто» и «непусто». Реальные паки репозитория чисты."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.pack_studio.outcome.lint import LintFinding
from hse_doc_studio.core.pack_studio.paths import VersionRef
from hse_doc_studio.infra.pack_studio.outcome_lint_files import JinjaProbeLimits, PackJinjaProbe, jinja_findings
from hse_doc_studio.infra.pack_studio.preview_worker import StageLimits
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository

from tests.unit.use_cases.pack_studio.outcome.synthetic import load_synthetic

TODAY = date(2026, 11, 16)
_PACKS = Path(__file__).resolve().parents[6] / "packs"
_EMPTY_SUPERVISOR = "{{ 1 // (project.supervisor.name | length) }}\n"


def _setup(tmp_path: Path, files: dict[str, str]) -> tuple[Path, TemplateVersion]:
    """Синтетическая версия с файлами шаблонов; возвращает папку паков и версию (манифест перечитан после правок)."""
    root = tmp_path / "packs"
    load_synthetic(root)
    version_dir = root / "p" / "templates" / "t" / "versions" / "1.0.0"
    for rel, text in files.items():
        path = version_dir / "files" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    version = YamlTemplateRepository(root).get_version("p", "t", "1.0.0")
    assert version is not None
    return root, version


def _run(tmp_path: Path, files: dict[str, str]) -> list[LintFinding]:
    root, version = _setup(tmp_path, files)
    return list(jinja_findings(root / "p" / "templates" / "t" / "versions" / "1.0.0", version, TODAY))


def test__clean_templates__give_nothing(tmp_path: Path) -> None:
    files = {"report/report.tex": "\\title{ {{ project.name }} } {{ project.supervisor.name | default('') }}\n"}

    assert _run(tmp_path, files) == []


def test__fail_open__a_template_that_breaks_on_an_empty_value_is_an_error(tmp_path: Path) -> None:
    (item,) = _run(tmp_path, {"report/report.tex": "ok\n" + _EMPTY_SUPERVISOR})

    assert (item.rule_id, item.severity, item.file) == ("jinja-fail-open", "error", "files/report/report.tex")
    assert "без руководителей" in item.message
    assert "ZeroDivisionError" in item.message
    assert item.hint
    assert item.line == 2


def test__fail_open__a_template_that_only_fails_on_a_filled_value_is_caught_too(tmp_path: Path) -> None:
    files = {"report/report.tex": "((* if project.authors | length > 0 *)){{ 1 // 0 }}((* endif *))\n"}

    assert [(f.rule_id, f.file) for f in _run(tmp_path, files)] == [("jinja-fail-open", "files/report/report.tex")]


def test__fail_open__one_finding_per_file_however_many_probes_fail(tmp_path: Path) -> None:
    found = _run(tmp_path, {"a/a.tex": "{{ 1 // 0 }}\n", "b/b.tex": "{{ 1 // 0 }}\n"})

    assert sorted(f.file or "" for f in found) == ["files/a/a.tex", "files/b/b.tex"]


def test__fail_open__a_dynamic_include_is_rendered_strictly_as_well(tmp_path: Path) -> None:
    root, _ = _setup(tmp_path, {"common/meta.tex.j2": "{{ 1 // 0 }}\n"})
    manifest = root / "p" / "templates" / "t" / "versions" / "1.0.0" / "version.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8")
        + "dynamic_includes:\n  - { template: common/meta.tex.j2, output: common/meta.tex }\n",
        encoding="utf-8",
    )
    version = YamlTemplateRepository(root).get_version("p", "t", "1.0.0")
    assert version is not None

    found = jinja_findings(manifest.parent, version, TODAY)

    assert [(f.rule_id, f.file) for f in found] == [("jinja-fail-open", "files/common/meta.tex.j2")]


def test__unknown_meta_key__a_template_reads_a_field_the_version_does_not_declare(tmp_path: Path) -> None:
    files = {"report/report.tex": "{{ project.meta.ghost }} {{ project.meta.year }} {{ project.supervisor.name }}\n"}

    (item,) = _run(tmp_path, files)

    assert item.rule_id == "jinja-unknown-meta-key"
    assert item.severity == "warning"
    assert "ghost" in item.message
    assert "year" not in item.message
    assert item.elements[0].id == "ghost"


def test__text_without_jinja_markers__is_not_rendered(tmp_path: Path) -> None:
    assert _run(tmp_path, {"report/report.tex": "\\textbf{ordinary latex}\n"}) == []


@pytest.mark.parametrize(
    "ref",
    [("hse-cs-se", "vkr", "2026.1.2"), ("hse-cs-se", "pp", "2026.1.1"), ("hse-cs-sse", "coursework", "2026.1.6")],
    ids=lambda r: "/".join(r),
)
def test__real_packs__have_no_jinja_findings(ref: tuple[str, str, str]) -> None:
    version = YamlTemplateRepository(_PACKS).get_version(*ref)
    assert version is not None

    found = jinja_findings(_PACKS / ref[0] / "templates" / ref[1] / "versions" / ref[2], version, TODAY)

    assert found == ()


async def test__probe__runs_in_an_isolated_process_and_gives_the_same_findings(tmp_path: Path) -> None:
    root, _ = _setup(tmp_path, {"report/report.tex": _EMPTY_SUPERVISOR})
    probe = PackJinjaProbe(tmp_path / "tmp", JinjaProbeLimits(60.0, 2 * 1024**3, StageLimits(10**9, 10_000)))

    found = await probe.probe(root, VersionRef("p", "t", "1.0.0"), TODAY)

    assert [(f.rule_id, f.file) for f in found] == [("jinja-fail-open", "files/report/report.tex")]
