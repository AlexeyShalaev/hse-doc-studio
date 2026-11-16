"""Чистая логика предпросмотра (template-studio.md, 6.1, 6.2, 6.3): переключатели, наборы, проект и ключ кэша."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from hse_doc_studio.core.catalog import DocumentDefinition, TemplateVersion
from hse_doc_studio.core.enums import PersonRole, ProjectKind, ProjectStaffing
from hse_doc_studio.core.pack_studio.outcome.predicates import document_in_scope
from hse_doc_studio.core.pack_studio.preview import (
    AUTO_EMPTY,
    AUTO_LONG,
    AUTO_NORMAL,
    ExampleFormatError,
    PreviewExample,
    PreviewInputError,
    SyntheticProject,
    auto_examples,
    combination_query,
    document_digest,
    parse_example,
    preview_cache_key,
    resolve_combination,
    switches_for,
    synthetic_project,
)
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository

TODAY = date(2026, 11, 15)

_VERSION = """\
id: "1.0.0"
status: beta
langs: [ru, en]
supported_staffing: [solo, team]
author_group_placeholder: "МСПИН261"
nda: { source_dir: nda }
meta_fields:
  nda: { type: bool, label: { ru: "NDA" } }
  stage: { type: select, label: { ru: "Этап" }, options: ["Первый", "Второй"], default: "Второй" }
  topic_en: { type: string, label: { ru: "Тема" }, placeholder: "Topic", required_at: finalize }
  code: { type: string, label: { ru: "Код" }, default: "09.04.04", required_at: create }
  public: { type: bool, label: { ru: "Публично" }, default: true }
  f1: { type: bool, label: { ru: "1" } }
  f2: { type: bool, label: { ru: "2" } }
  f3: { type: bool, label: { ru: "3" } }
  f4: { type: bool, label: { ru: "4" } }
documents:
  - { id: report, name: { ru: "Отчёт" }, source_file: report/report.tex, output_file: report/report.pdf }
  - id: memo
    name: { ru: "Записка" }
    source_file: memo/memo.tex
    output_file: memo/memo.pdf
    supported_kinds: [project]
    supported_staffing: [team]
"""


@pytest.fixture(scope="module")
def version(tmp_path_factory: pytest.TempPathFactory) -> TemplateVersion:
    root: Path = tmp_path_factory.mktemp("packs")
    (root / "p" / "templates" / "t" / "versions" / "1.0.0").mkdir(parents=True)
    (root / "p" / "pack.yaml").write_text("id: p\n", encoding="utf-8")
    (root / "p" / "templates" / "t" / "template.yaml").write_text("id: t\n", encoding="utf-8")
    (root / "p" / "templates" / "t" / "versions" / "1.0.0" / "version.yaml").write_text(_VERSION, encoding="utf-8")
    loaded = YamlTemplateRepository(root).get_version("p", "t", "1.0.0")
    assert loaded is not None
    return loaded


def _example(version: TemplateVersion, example_id: str = AUTO_NORMAL) -> PreviewExample:
    return next(e for e in auto_examples(version) if e.id == example_id)


def test__switches__fixed_then_nda_then_five_meta_fields(version: TemplateVersion) -> None:
    switches = {s.id: s for s in switches_for(version)}

    assert switches["lang"].values == ("ru", "en")
    assert switches["kind"].values == ("research", "project")
    assert switches["staffing"].values == ("solo", "team2", "team3")
    assert switches["supervisor"].values == ("university", "company", "none")
    assert switches["nda"].values == ("no", "yes")
    meta = [s.id for s in switches_for(version) if s.id.startswith("meta.")]
    # `nda` идёт своим переключателем, строковые поля в переключатели не попадают, полей не больше пяти.
    assert meta == ["meta.stage", "meta.public", "meta.f1", "meta.f2", "meta.f3"]
    assert switches["meta.stage"].default == "Второй"
    assert switches["meta.public"].default == "yes"


def test__resolve_combination__request_then_example_then_default(version: TemplateVersion) -> None:
    switches = switches_for(version)

    combo = resolve_combination(switches, {"lang": "en"}, {"staffing": "team3", "lang": "ru", "kind": "bogus"})

    assert combo["lang"] == "en"
    assert combo["staffing"] == "team3"
    assert combo["kind"] == "research"
    assert combination_query(combo).startswith("academic_supervisor=yes&co_supervisor=no&kind=research")


@pytest.mark.parametrize(
    ("raw", "field"), [({"bogus": "x"}, "combination.bogus"), ({"lang": "de"}, "combination.lang")]
)
def test__resolve_combination__unknown_switch_or_value__rejected(
    version: TemplateVersion, raw: dict[str, str], field: str
) -> None:
    with pytest.raises(PreviewInputError) as caught:
        resolve_combination(switches_for(version), raw)

    assert caught.value.field == field


def test__synthetic__default_combination__solo_with_university_supervisor(version: TemplateVersion) -> None:
    combo = resolve_combination(switches_for(version), {})

    project = synthetic_project(version, _example(version), combo, TODAY)

    assert project.staffing is ProjectStaffing.solo
    assert project.kind is ProjectKind.research
    assert [a.group for a in project.authors] == ["МСПИН261"]
    assert project.supervisor is not None
    assert project.supervisor.role is PersonRole.university
    assert project.co_supervisor is None
    assert project.academic_supervisor is not None
    assert project.meta["nda"] is False
    assert project.meta["stage"] == "Второй"
    assert project.meta["public"] is True
    assert project.meta["topic_en"] == "Topic"


def test__synthetic__every_branch_switch_lands_in_the_project(version: TemplateVersion) -> None:
    raw = {
        "lang": "en",
        "kind": "project",
        "staffing": "team3",
        "supervisor": "company",
        "co_supervisor": "yes",
        "academic_supervisor": "no",
        "nda": "yes",
        "meta.stage": "Первый",
        "meta.public": "no",
    }
    combo = resolve_combination(switches_for(version), raw)

    project = synthetic_project(version, _example(version), combo, TODAY)

    assert project.lang.value == "en"
    assert project.kind is ProjectKind.project
    assert project.staffing is ProjectStaffing.team
    assert len(project.authors) == 3
    assert len({a.slug for a in project.authors}) == 3
    assert all(a.slug for a in project.authors)
    assert project.supervisor is not None
    assert project.supervisor.role is PersonRole.company
    assert project.co_supervisor is not None
    assert project.academic_supervisor is None
    assert project.meta["nda"] is True
    assert project.meta["stage"] == "Первый"
    assert project.meta["public"] is False
    assert project.name.startswith("An Approval Gate")


def test__synthetic__no_supervisor(version: TemplateVersion) -> None:
    combo = resolve_combination(switches_for(version), {"supervisor": "none"})

    assert synthetic_project(version, _example(version), combo, TODAY).supervisor is None


def test__auto_examples__long_triples_strings_and_empty_keeps_only_create_fields(version: TemplateVersion) -> None:
    combo = resolve_combination(switches_for(version), {})
    normal = synthetic_project(version, _example(version), combo, TODAY)
    long = synthetic_project(version, _example(version, AUTO_LONG), combo, TODAY)
    empty = synthetic_project(version, _example(version, AUTO_EMPTY), combo, TODAY)

    assert len(long.name) == 3 * len(normal.name) + 2
    assert long.meta["topic_en"] == "Topic Topic Topic"
    assert long.meta["stage"] == "Второй"  # select не удлиняется: значение обязано быть из списка
    assert long.authors[0].name.count(normal.authors[0].name) == 3
    assert "topic_en" not in empty.meta
    assert empty.meta["code"] == "09.04.04"
    assert empty.authors[0].group is None
    assert empty.supervisor is not None
    assert empty.supervisor.title is None


def test__parse_example__people_meta_and_defaults() -> None:
    data = parse_example(
        {
            "label": {"ru": "Мой"},
            "name": {"ru": "Тема", "en": "Topic"},
            "staffing": "team2",
            "authors": [{"name": "Иванов И. И.", "group": "Г1"}, {"name": ""}, "Петров П. П."],
            "supervisor": {"name": "Сидоров С. С.", "position": "доцент", "role": "company"},
            "meta": {"stage": "Первый", "nested": {"x": 1}, "flag": True},
            "unknown": 1,
        }
    )

    assert data.name == {"ru": "Тема", "en": "Topic"}
    assert [a.name for a in data.authors] == ["Иванов И. И.", "Петров П. П."]
    assert data.supervisor is not None
    assert data.supervisor.role is PersonRole.company
    assert data.supervisor.title == "доцент"
    assert data.meta == {"stage": "Первый", "flag": True}
    assert data.defaults == {"staffing": "team2"}


@pytest.mark.parametrize("raw", [[1, 2], {"authors": 5}, {"meta": [1]}, {"supervisor": 3}])
def test__parse_example__wrong_shape__rejected(raw: object) -> None:
    with pytest.raises(ExampleFormatError):
        parse_example(raw)


def test__example_people__override_samples_but_switches_decide_roles(version: TemplateVersion) -> None:
    example = PreviewExample(
        "mine",
        "file",
        None,
        parse_example({"supervisor": {"name": "Сидоров С. С.", "role": "company"}, "name": "Своя тема"}),
    )
    combo = resolve_combination(switches_for(version), {"supervisor": "university"})

    project = synthetic_project(version, example, combo, TODAY)

    assert project.name == "Своя тема"
    assert project.supervisor is not None
    assert project.supervisor.name == "Сидоров С. С."
    assert project.supervisor.role is PersonRole.university


def _present(doc: DocumentDefinition, project: SyntheticProject) -> bool:
    return document_in_scope(doc.supported_kinds, doc.supported_staffing, project.kind.value, project.staffing.value)


def test__document_scope__by_kind_and_staffing(version: TemplateVersion) -> None:
    memo = next(d for d in version.documents if d.id == "memo")
    switches = switches_for(version)
    solo = synthetic_project(version, _example(version), resolve_combination(switches, {"kind": "project"}), TODAY)
    team = synthetic_project(
        version, _example(version), resolve_combination(switches, {"kind": "project", "staffing": "team2"}), TODAY
    )

    assert not _present(memo, solo)
    assert _present(memo, team)


def test__document_digest__other_document_edit_keeps_it_common_edit_changes_it(version: TemplateVersion) -> None:
    files = {
        "version.yaml": "v1",
        "files/common/meta.tex.j2": "c1",
        "files/report/report.tex": "r1",
        "files/memo/memo.tex": "m1",
    }
    base = document_digest(files, version, "report")

    assert document_digest({**files, "files/memo/memo.tex": "m2"}, version, "report") == base
    assert document_digest({**files, "files/report/report.tex": "r2"}, version, "report") != base
    assert document_digest({**files, "files/common/meta.tex.j2": "c2"}, version, "report") != base
    assert document_digest(files, version, "report", ("pack.yaml:x",)) != base


def test__cache_key__depends_on_project_not_on_other_examples(version: TemplateVersion) -> None:
    combo = resolve_combination(switches_for(version), {})
    project = synthetic_project(version, _example(version), combo, TODAY)
    other = synthetic_project(version, _example(version), {**combo, "lang": "en"}, TODAY)

    key = preview_cache_key(doc_digest="d", def_id="report", project=project, engine="xelatex")

    assert key == preview_cache_key(doc_digest="d", def_id="report", project=project, engine="xelatex")
    assert key != preview_cache_key(doc_digest="d", def_id="report", project=other, engine="xelatex")
    assert key != preview_cache_key(doc_digest="e", def_id="report", project=project, engine="xelatex")
    assert key != preview_cache_key(
        doc_digest="d",
        def_id="report",
        project=synthetic_project(version, _example(version), combo, date(2027, 1, 1)),
        engine="xelatex",
    )
