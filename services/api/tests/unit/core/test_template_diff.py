"""Классификатор изменений версии шаблона: таблица 7.2 template-studio.md построчно на парах каталогов."""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import yaml
from hse_doc_studio.core.enums import TemplateUpdateClass
from hse_doc_studio.core.template_diff import classify_change

PATCH, MINOR, MAJOR = TemplateUpdateClass.patch, TemplateUpdateClass.minor, TemplateUpdateClass.major

_BASE_MANIFEST: dict[str, Any] = {
    "id": "2026.1.0",
    "released_at": "2026-09-01",
    "status": "stable",
    "summary": {"ru": "Курсовой", "en": "Course project"},
    "changes": {"ru": ["Первая версия"], "en": ["First version"]},
    "supported_kinds": ["project", "research"],
    "supported_staffing": ["solo"],
    "engine": {"default": "xelatex", "passes": 3},
    "latex_packages": ["fontspec"],
    "langs": ["ru", "en"],
    "documents": ["report"],
    "dynamic_includes": [{"template": "common/meta.tex.j2", "output": "common/meta.tex"}],
    "meta_groups": [{"id": "study", "label": {"ru": "Учёба", "en": "Studies"}}],
    "meta_fields": {
        "year": {"type": "string", "group": "study", "label": {"ru": "Год", "en": "Year"}, "required_at": "create"},
        "city": {"type": "string", "group": "study", "required_at": "never", "default": "Москва"},
    },
    "forms": [{"id": "code_link", "title": {"ru": "Ссылка", "en": "Link"}, "required_for_pack": True}],
    "signatures": {
        "slots": [
            {"id": "author", "label": {"ru": "Автор", "en": "Author"}, "applies_to": ["report"]},
            {
                "id": "supervisor",
                "label": {"ru": "Руководитель", "en": "Supervisor"},
                "applies_to": ["report"],
                "default_placement": {"page": 1, "x_mm": 110, "y_mm": 130, "width_mm": 40},
            },
        ]
    },
    "pack_submission": {
        "profiles": [
            {
                "id": "final",
                "name": {"ru": "Защита", "en": "Defence"},
                "items": [{"doc_id": "report", "signatures": ["author"]}],
            },
            {"id": "pre", "name": {"ru": "Предзащита", "en": "Pre-defence"}, "items": []},
        ]
    },
    "checks_version": {"disabled_categories": [], "disabled": [], "severity_override": {}},
}

_DOC = {
    "name": {"ru": "Отчёт", "en": "Report"},
    "source_file": "report/report.tex",
    "output_file": "report/report.pdf",
    "required": True,
    "supported_langs": ["ru", "en"],
    "scope": "personal",
}

_CHECKS = {
    "label": {"ru": "ГОСТ", "en": "GOST"},
    "ref": {"ru": "ГОСТ 7.32", "en": "GOST 7.32"},
    "rules": [
        {
            "id": "gost/abstract",
            "title": {"ru": "Реферат", "en": "Abstract"},
            "description": {"ru": "Нужен реферат", "en": "An abstract is required"},
            "category": "structure",
            "applies_to": ["report"],
            "default_severity": "err",
            "engine": "regex",
            "params": {"pattern": "реферат"},
        }
    ],
}

_FILES = {
    "files/report/report.ru.tex": "\\section{Введение}\n",
    "files/report/report.en.tex": "\\section{Introduction}\n",
    "files/common/meta.tex.j2": "\\newcommand{\\hseYear}{ {{ project.meta.year }} }\n",
}


def _dump(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8", newline="\n")


class _Version:
    def __init__(self) -> None:
        self.manifest = copy.deepcopy(_BASE_MANIFEST)
        self.docs: dict[str, dict[str, Any]] = {"report": copy.deepcopy(_DOC)}
        self.checks: dict[str, dict[str, Any]] = {"gost.yaml": copy.deepcopy(_CHECKS)}
        self.files: dict[str, str] = dict(_FILES)

    def write(self, version_dir: Path) -> Path:
        _dump(version_dir / "version.yaml", self.manifest)
        for doc_id, doc in self.docs.items():
            _dump(version_dir / "files" / doc_id / "doc.yaml", doc)
        for name, data in self.checks.items():
            _dump(version_dir / "checks" / name, data)
        for rel, text in self.files.items():
            (version_dir / rel).parent.mkdir(parents=True, exist_ok=True)
            (version_dir / rel).write_text(text, encoding="utf-8", newline="\n")
        return version_dir


def _classify(tmp_path: Path, mutate: Callable[[_Version], None], new_id: str = "2026.1.1"):  # noqa: ANN202
    base = _Version().write(tmp_path / "versions" / "2026.1.0")
    new = _Version()
    new.manifest["id"] = new_id
    mutate(new)
    return classify_change(base, new.write(tmp_path / "versions" / new_id))


def _slot(version: _Version, slot_id: str) -> dict[str, Any]:
    return next(s for s in version.manifest["signatures"]["slots"] if s["id"] == slot_id)


def _profile(version: _Version, profile_id: str = "final") -> dict[str, Any]:
    return next(p for p in version.manifest["pack_submission"]["profiles"] if p["id"] == profile_id)


def _set(path: str, value: Any) -> Callable[[_Version], None]:
    """Мутация манифеста по пути `a.b.c` (словари)."""

    def mutate(version: _Version) -> None:
        node = version.manifest
        *head, last = path.split(".")
        for key in head:
            node = node.setdefault(key, {})
        node[last] = value

    return mutate


def _add_doc(version: _Version) -> None:
    version.manifest["documents"].append("application")
    version.docs["application"] = {"name": {"ru": "Заявление", "en": "Application"}, "source_file": "application/a.tex"}
    version.files["files/application/a.tex"] = "Заявление\n"


def _remove_doc(version: _Version) -> None:
    version.manifest["documents"] = []
    version.docs = {}
    for rel in [r for r in version.files if r.startswith("files/report/")]:
        del version.files[rel]


# ── не влияет ──


def test__notes_status_and_comments__change_nothing(tmp_path: Path) -> None:
    def mutate(version: _Version) -> None:
        version.manifest.update(
            released_at="2026-11-14",
            status="deprecated",
            summary={"ru": "Новое описание", "en": "New summary"},
            changes={"ru": ["Исправления"], "en": ["Fixes"]},
            breaking_changes={"ru": [], "en": []},
            release={"kind": "patch", "note": "объяснение"},
        )

    report = _classify(tmp_path, mutate)

    assert report.reasons == ()
    assert report.minimum is PATCH
    assert report.suggested is PATCH
    assert report.headline("ru") == "patch: изменений нет"
    assert report.headline("en") == "patch: no changes"


def test__yaml_comments_and_layout__change_nothing(tmp_path: Path) -> None:
    base = _Version().write(tmp_path / "versions" / "2026.1.0")
    new = _Version().write(tmp_path / "versions" / "2026.1.1")
    text = (new / "version.yaml").read_text(encoding="utf-8")
    (new / "version.yaml").write_text("# комментарий\n" + text.replace("\n", "\r\n"), encoding="utf-8")

    assert classify_change(base, new).reasons == ()


# ── исключение patch: заготовки подписания и подсказки сроков (жёсткое) ──


@pytest.mark.parametrize(
    "mutate",
    [
        lambda v: _slot(v, "supervisor").update(placements={"report": {"page": 1, "x_mm": 80, "y_mm": 139}}),
        lambda v: _slot(v, "supervisor").update(
            default_placement={"page": 1, "x_mm": 100, "y_mm": 130, "width_mm": 40}
        ),
        lambda v: _slot(v, "author").update(default_dates={"report": [{"anchor": "author.date_numeric"}]}),
        lambda v: _profile(v).update(signing_slots=[{"doc_id": "report", "slot_id": "supervisor"}]),
        lambda v: v.manifest["signatures"].update(route=[["author"], ["supervisor"]]),
        lambda v: v.manifest["signatures"].update(anchor_macros=["hseSignField"]),
        lambda v: _profile(v).update(signing_route=[["author"], ["supervisor"]]),
        lambda v: _profile(v).update(deadline_hint={"ru": "Обычно в июне", "en": "Usually in June"}),
    ],
    ids=[
        "placements",
        "default_placement",
        "default_dates",
        "signing_slots",
        "route",
        "anchor_macros",
        "signing_route",
        "deadline_hint",
    ],
)
def test__patch_exception_keys__are_a_hard_patch(tmp_path: Path, mutate: Callable[[_Version], None]) -> None:
    report = _classify(tmp_path, mutate)

    assert len(report.reasons) == 1
    (reason,) = report.reasons
    assert reason.hard
    assert reason.exception
    assert (reason.minimum, reason.suggested) == (PATCH, PATCH)
    assert report.exception_only


# ── мягкие правила ──


@pytest.mark.parametrize(
    ("mutate", "code", "suggested"),
    [
        (
            lambda v: v.files.update({"files/report/report.ru.tex": "\\section{Введение}\nНовый абзац\n"}),
            "file_changed",
            PATCH,
        ),
        (lambda v: v.files.update({"files/common/anchors.tex": "% якоря\n"}), "file_added", PATCH),
        (lambda v: v.files.pop("files/common/meta.tex.j2"), "file_removed", MINOR),
        (lambda v: v.checks["gost.yaml"]["rules"][0].update(default_severity="warn"), "check_tuning", PATCH),
        (lambda v: v.checks["gost.yaml"]["rules"][0]["params"].update(pattern="(?i)реферат"), "check_tuning", PATCH),
        (lambda v: v.checks["gost.yaml"].update(rules=[]), "check_rule_removed", PATCH),
        (lambda v: v.manifest["checks_version"].update(disabled=["gost/abstract"]), "check_tuning", PATCH),
        (lambda v: v.docs["report"].update(source_file="report/main.tex"), "document_source", PATCH),
        (lambda v: _profile(v)["items"][0].update(methods={"author": ["image"]}), "methods", MINOR),
        (_set("meta_fields.city.default", "Пермь"), "field_default", MINOR),
        (_set("meta_fields.city_en", {"type": "string", "required_at": "never"}), "optional_field_added", PATCH),
    ],
    ids=[
        "file_content",
        "helper_file_added",
        "file_removed",
        "check_severity",
        "check_params",
        "check_rule_removed",
        "checks_version",
        "doc_source_file",
        "methods",
        "field_default",
        "optional_field",
    ],
)
def test__soft_rules__keep_patch_minimum_and_suggest(
    tmp_path: Path, mutate: Callable[[_Version], Any], code: str, suggested: TemplateUpdateClass
) -> None:
    report = _classify(tmp_path, mutate)

    assert [r.code for r in report.reasons] == [code]
    (reason,) = report.reasons
    assert not reason.hard
    assert report.minimum is PATCH
    assert report.suggested is suggested


# ── тексты (исправления) ──


@pytest.mark.parametrize(
    "mutate",
    [
        _set("meta_fields.year.label", {"ru": "Учебный год", "en": "Academic year"}),
        _set("meta_fields.year.help", {"ru": "Подсказка", "en": "Hint"}),
        lambda v: _profile(v).update(name={"ru": "Защита КП", "en": "Defence"}),
        lambda v: v.docs["report"].update(name={"ru": "Отчёт о КП", "en": "Report"}),
        lambda v: v.checks["gost.yaml"]["rules"][0].update(description={"ru": "Реферат", "en": "Abstract"}),
        lambda v: v.checks["gost.yaml"].update(ref={"ru": "ГОСТ 7.32-2017", "en": "GOST 7.32-2017"}),
        lambda v: v.manifest["forms"][0].update(title={"ru": "Репозиторий", "en": "Repository"}),
    ],
    ids=["field_label", "field_help", "profile_name", "doc_name", "rule_description", "check_ref", "form_title"],
)
def test__texts__are_a_hard_patch_with_one_reason_per_text(tmp_path: Path, mutate: Callable[[_Version], Any]) -> None:
    report = _classify(tmp_path, mutate)

    assert [r.code for r in report.reasons] == ["text"]
    assert report.suggested is PATCH


def test__text_split_by_an_unquoted_comma__fixed_with_quotes_is_a_text_patch(tmp_path: Path) -> None:
    # `{ ru: Шрифт (код, листинги), en: Mono }`: YAML дал ru «Шрифт (код» и ключ «листинги)» без значения.
    base = _Version()
    base.manifest["meta_fields"]["year"]["label"] = {"ru": "Шрифт (код", "листинги)": None, "en": "Mono"}
    base.write(tmp_path / "versions" / "2026.1.0")
    new = _Version()
    new.manifest["id"] = "2026.1.1"
    new.manifest["meta_fields"]["year"]["label"] = {"ru": "Шрифт (код, листинги)", "en": "Mono"}

    report = classify_change(tmp_path / "versions" / "2026.1.0", new.write(tmp_path / "versions" / "2026.1.1"))

    assert [(r.code, r.path) for r in report.reasons] == [("text", "meta_fields.year.label")]
    assert report.minimum is PATCH


# ── новая поверхность: minor (жёсткое) ──


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (_add_doc, "document_added"),
        (_set("meta_fields.name_en", {"type": "string", "required_at": "finalize"}), "field_added"),
        (_set("meta_fields.lang_note", {"type": "string", "required_at": "never", "default": "нет"}), "field_added"),
        (_set("meta_fields.year2", {"type": "string", "required_at": "never", "auto": "academic_year"}), "field_added"),
        (_set("meta_fields.no_required_at", {"type": "string"}), "field_added"),
        (
            lambda v: v.manifest["meta_groups"].append({"id": "title", "label": {"ru": "Титул", "en": "Title"}}),
            "group_added",
        ),
        (lambda v: v.manifest["forms"].append({"id": "nda", "title": {"ru": "NDA", "en": "NDA"}}), "form_added"),
        (lambda v: v.manifest["pack_submission"]["profiles"].append({"id": "cp1", "items": []}), "profile_added"),
        (lambda v: _profile(v, "pre")["items"].append({"doc_id": "report", "signatures": []}), "item_added"),
        (
            lambda v: v.manifest["signatures"]["slots"].append({"id": "co_supervisor", "applies_to": ["report"]}),
            "slot_added",
        ),
        (
            lambda v: v.checks["gost.yaml"]["rules"].append({"id": "gost/toc", "category": "structure"}),
            "check_rule_added",
        ),
        (
            lambda v: v.checks.update({"typography.yaml": {"label": {"ru": "Т", "en": "T"}, "rules": []}}),
            "check_file_added",
        ),
        (_set("langs", ["ru", "en", "kk"]), "version_scope"),
        (_set("supported_kinds", ["project"]), "version_scope"),
        (_set("supported_staffing", ["solo", "team"]), "version_scope"),
        (lambda v: _profile(v).update(extra_items=[{"source": ".hse-studio/forms/code_link.json"}]), "extra_items"),
        (lambda v: _slot(v, "author").update(required=True), "slot_required"),
        (lambda v: _slot(v, "author").update(applies_to=["report", "application"]), "slot_scope"),
        (lambda v: _profile(v)["items"][0].update(signatures=["author", "supervisor"]), "item_signatures"),
        (_set("meta_fields.city.required_at", "create"), "required_stricter"),
        (_set("meta_fields.city.type", "select"), "field_type"),
        (lambda v: v.docs["report"].update(supported_langs=["ru"]), "document_scope"),
        (
            lambda v: (
                v.files.update({"files/report/report.kk.tex": "Кіріспе\n"})
                or v.manifest.update(langs=["ru", "en", "kk"])
            ),
            "version_scope",
        ),
    ],
    ids=[
        "document",
        "required_field",
        "field_with_default",
        "field_with_auto",
        "field_required_by_default",
        "field_group",
        "form",
        "profile",
        "checkpoint_item",
        "slot",
        "check_rule",
        "check_file",
        "langs",
        "supported_kinds",
        "supported_staffing",
        "extra_items",
        "slot_required",
        "slot_applies_to",
        "item_signatures",
        "field_required_at",
        "field_type",
        "doc_supported_langs",
        "language_edition",
    ],
)
def test__new_surface__is_a_hard_minor(tmp_path: Path, mutate: Callable[[_Version], Any], code: str) -> None:
    report = _classify(tmp_path, mutate)

    assert code in {r.code for r in report.reasons}
    assert report.minimum is MINOR
    assert all(r.hard for r in report.reasons if r.code == code)


@pytest.mark.parametrize(
    "key",
    ["engine", "latex_packages", "dynamic_includes", "requirements", "nda", "manifest_format", "min_studio"],
)
def test__build_setup__is_a_hard_minor(tmp_path: Path, key: str) -> None:
    report = _classify(tmp_path, _set(key, {"changed": True}))

    assert [r.code for r in report.reasons] == ["build_setup"]
    assert report.minimum is MINOR


def test__new_document_source_without_a_new_document__is_a_hard_minor(tmp_path: Path) -> None:
    def mutate(version: _Version) -> None:
        version.docs["report"]["variants"] = [{"id": "short", "source_file": "report/short.tex"}]
        version.files["files/report/short.tex"] = "Краткий отчёт\n"

    report = _classify(tmp_path, mutate)

    assert {r.code for r in report.reasons} == {"variant_added", "document_file_added"}
    assert report.minimum is MINOR


def test__new_document__does_not_list_its_files_separately(tmp_path: Path) -> None:
    report = _classify(tmp_path, _add_doc)

    assert [(r.code, r.path) for r in report.reasons] == [("document_added", "documents[application]")]


# ── удаление: minor, предлагается major ──


@pytest.mark.parametrize(
    "mutate",
    [
        _remove_doc,
        lambda v: v.manifest["meta_fields"].pop("city"),
        lambda v: v.manifest["pack_submission"]["profiles"].pop(),
        lambda v: v.manifest["signatures"]["slots"].pop(),
        lambda v: v.manifest.update(forms=[]),
        lambda v: v.manifest.update(meta_groups=[]),
    ],
    ids=["document", "field", "profile", "slot", "form", "group"],
)
def test__removal__is_minor_and_suggests_major(tmp_path: Path, mutate: Callable[[_Version], Any]) -> None:
    report = _classify(tmp_path, mutate)

    assert "removed" in {r.code for r in report.reasons}
    assert report.minimum is MINOR
    assert report.suggested is MAJOR


# ── порядок, ослабление, неизвестное, номер ──


def test__reordering__is_a_patch(tmp_path: Path) -> None:
    def mutate(version: _Version) -> None:
        version.manifest["pack_submission"]["profiles"].reverse()

    report = _classify(tmp_path, mutate)

    assert [(r.code, r.path) for r in report.reasons] == [("order", "pack_submission.profiles")]
    assert report.suggested is PATCH


def test__relaxed_requirement__is_a_patch(tmp_path: Path) -> None:
    report = _classify(tmp_path, _set("meta_fields.year.required_at", "finalize"))

    assert [r.code for r in report.reasons] == ["required_looser"]
    assert report.minimum is PATCH


def test__unknown_key__is_a_hard_minor(tmp_path: Path) -> None:
    report = _classify(tmp_path, _set("future_key", {"x": 1}))

    assert [(r.code, r.path, r.change) for r in report.reasons] == [("unclassified", "future_key", "added")]
    assert report.minimum is MINOR


def test__year_in_the_number__is_major_by_number(tmp_path: Path) -> None:
    report = _classify(tmp_path, lambda v: None, new_id="2027.1.0")

    assert report.by_number is MAJOR
    assert report.minimum is PATCH


# ── отчёт ──


def test__report__machine_and_human_forms(tmp_path: Path) -> None:
    def mutate(version: _Version) -> None:
        _profile(version)["items"][0]["methods"] = {"author": ["image"]}
        _profile(version)["deadline_hint"] = {"ru": "Обычно в июне", "en": "Usually in June"}
        version.files["files/report/report.ru.tex"] = "Изменено\n"

    report = _classify(tmp_path, mutate)
    data = json.loads(json.dumps(report.to_dict(), ensure_ascii=False))

    assert data["minimum"] == "patch"
    assert data["suggested"] == "minor"
    assert data["by_number"] == "patch"
    assert data["exception_only"] is False
    assert {r["code"] for r in data["reasons"]} == {"methods", "deadline_hint", "file_changed"}
    assert all(r["message"]["ru"] and r["message"]["en"] for r in data["reasons"])
    assert report.headline("ru") == "minor: способы подписи, подсказки сроков, файлы шаблона"
    assert report.headline("en") == "minor: signing methods, deadline hints, template files"
    ru, en = report.render("ru"), report.render("en")
    assert "Минимум patch, предлагается minor" in ru
    assert "По номеру 2026.1.0 > 2026.1.1: patch" in ru
    assert "pack_submission.profiles[final].items[report].methods" in ru
    assert "Minimum patch, suggested minor" in en
    assert "[patch, suggested minor; soft]" in en
    assert [r.code for r in report.above(PATCH)] == []
    assert [r.code for r in report.suggested_above(PATCH)] == ["methods"]


def test__broken_manifest__raises_value_error(tmp_path: Path) -> None:
    base = _Version().write(tmp_path / "a")
    new = _Version().write(tmp_path / "b")
    (new / "version.yaml").write_text("key: [unclosed\n", encoding="utf-8")

    with pytest.raises(ValueError, match="не читается"):
        classify_change(base, new)
