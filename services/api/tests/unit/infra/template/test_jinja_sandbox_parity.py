"""Песочница Jinja не меняет ни байта вывода реальных паков.

Каждый текстовый файл, XML каждого слайда pptx и шаблон вывода каждой анкеты всех версий всех паков
репозитория рендерится прежним обычным `Environment` (его настройки повторены здесь дословно) и
песочным окружением Студии на нескольких наборах данных проекта. Исход обязан совпасть: тот же текст
или то же исключение (тогда оба рендера уходят в verbatim-копию).
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
import yaml
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import EngineType, Lang, PersonRole, ProjectKind, ProjectStaffing
from hse_doc_studio.core.value_objects import Author, Person, ProjectLock
from hse_doc_studio.infra.project_init.template_renderer import build_context
from hse_doc_studio.infra.template.jinja_sandbox import (
    SandboxedTemplateEnvironment,
    form_environment,
    pack_environment,
    texesc,
    xmlesc,
)
from hse_doc_studio.use_cases.forms.render_form import _build_context as build_form_context
from jinja2 import ChainableUndefined, Environment, Template

PACKS_ROOT = Path(__file__).resolve().parents[6] / "packs"
_RENDERED_SUFFIXES = {".tex", ".md", ".html", ".txt", ".cls", ".sty", ".bib", ".j2"}
_SLIDE_RE = re.compile(r"^ppt/slides/slide\d+\.xml$")
_NOW = datetime(2026, 12, 31, 22, 30, tzinfo=UTC)
# Спецсимволы LaTeX, XML и самой Jinja в данных: экранирование обязано совпасть.
_NASTY = ' & 50% _x_ {y} \\ ~ ^ # $ <b a="q">'


def _old_pack_env() -> Environment:
    env = Environment(  # noqa: S701 — прежнее окружение, эталон сравнения
        undefined=ChainableUndefined,
        keep_trailing_newline=True,
        block_start_string="((*",
        block_end_string="*))",
        comment_start_string="((#",
        comment_end_string="#))",
    )
    env.filters["texesc"] = texesc
    env.filters["xmlesc"] = xmlesc
    return env


def _old_form_env() -> Environment:
    return Environment(undefined=ChainableUndefined, keep_trailing_newline=True)  # noqa: S701


# ── Наборы данных проекта ───────────────────────────────────────

_META_KEYS = (
    *("author_name_en", "city", "city_en", "course", "department", "doc_code_base", "faculty", "faculty_en"),
    *("font_main", "font_mono", "font_sans", "form_year", "name_en", "name_ru", "name_short", "program_code"),
    *("specialization", "supervisor_department", "udc", "university_en"),
)


def _meta(prefix: str) -> dict[str, Any]:
    meta: dict[str, Any] = {key: f"{prefix} {key}{_NASTY}" for key in _META_KEYS}
    meta |= {
        "year": "2026/2027",
        "nda": True,
        "manuals": "both",
        "proposal_stage": "Доработка",
        "report_margins": "ВШЭ, Прил",
    }
    return meta


def _project(**overrides: Any) -> Project:
    fields: dict[str, Any] = {
        "id": uuid4(),
        "name": "",
        "folder": Path("/nonexistent"),
        "lock": ProjectLock(pack_id="p", template_id="t", version="1", engine=EngineType.xelatex),
        "kind": ProjectKind.research,
        "staffing": ProjectStaffing.solo,
        "lang": Lang.ru,
        "authors": [],
        "meta": {},
        "supervisor": None,
        "co_supervisor": None,
        "documents": [],
        "created_at": datetime(2026, 9, 1, tzinfo=UTC),
        "updated_at": datetime(2026, 9, 1, tzinfo=UTC),
    }
    fields.update(overrides)
    return Project(**fields)


def _author(name: str, slug: str | None = None) -> Author:
    return Author(
        name=name,
        group="БПИ231",
        email=f"{slug or 'solo'}@edu.hse.ru",
        slug=slug,
        topic=f"Тема {name}{_NASTY}",
        meta={"doc_code_base": f"RU.{slug or 'solo'}", "name_en": f"Topic of {name}"},
    )


def _people(lang_name: str) -> dict[str, Any]:
    return {
        "supervisor": Person(name=f"{lang_name} Руков", role=PersonRole.company, title="CTO & co", degree="к.т.н."),
        "co_supervisor": Person(name="Петров П. П.", role=PersonRole.university, title="доцент", degree=None),
        "academic_supervisor": Person(name="Шершаков С. А.", role=PersonRole.university, title="Академрук"),
    }


@dataclass(frozen=True)
class _Dataset:
    name: str
    project: Project
    author: Author | None  # владелец рендеримой базы; None у solo это «единственный автор», у team общая база


def _datasets() -> list[_Dataset]:
    full = _project(
        name=f"Система учёта{_NASTY}",
        authors=[_author("Иванов Иван Иванович")],
        meta=_meta("ru"),
        **_people("Сидоров С. С."),
    )
    team_authors = [_author("Алексеев А. А.", "alekseev"), _author("Борисов Б. Б.", "borisov"), Author(name="  ")]
    team = _project(
        name="Командная система",
        kind=ProjectKind.project,
        staffing=ProjectStaffing.team,
        authors=team_authors,
        meta=_meta("team"),
        **_people("Сидоров С. С."),
    )
    en = _project(
        name="Accounting System",
        lang=Lang.en,
        authors=[_author("Ivan Ivanov")],
        meta=_meta("en"),
        **_people("John Smith"),
    )
    return [
        _Dataset("empty", _project(), None),
        _Dataset("full", full, None),
        _Dataset("team-personal", team, team_authors[0]),
        _Dataset("team-shared", team, None),
        _Dataset("en", en, None),
    ]


def _pack_contexts() -> list[tuple[str, dict[str, Any]]]:
    info = SimpleNamespace(id="hse-cs-sse")
    version = SimpleNamespace(version="2026.1.5")
    return [
        (ds.name, build_context(ds.project, info, info, version, author=ds.author, now=_NOW))  # type: ignore[arg-type]
        for ds in _datasets()
    ]


_FULL_ANSWERS: dict[str, Any] = {
    "access": f"Открытый{_NASTY}",
    "branch": "main",
    "details": f"Подробности{_NASTY}",
    "pct": 30,
    "repo_url": "https://git.cs.hse.ru/x/y",
    "used_ai": "yes",
    "usage_table": [{"tool": "Claude", "version": "4", "scope": "код", "kind": "генерация"}, {}],
}


def _form_contexts() -> list[tuple[str, dict[str, Any]]]:
    return [
        (f"{ds.name}/{label}", build_form_context(ds.project, answers, ds.author))
        for ds in _datasets()
        for label, answers in (("no-answers", {}), ("answers", _FULL_ANSWERS))
    ]


# ── Шаблоны паков ───────────────────────────────────────────────


def _version_dirs() -> list[Path]:
    dirs = sorted(p for p in PACKS_ROOT.glob("*/templates/*/versions/*") if p.is_dir())
    assert dirs, f"в {PACKS_ROOT} не найдено ни одной версии шаблона"
    return dirs


def _pack_sources(version_dir: Path) -> Iterator[tuple[str, str]]:
    """(имя, исходник) каждого файла, который Студия пропускает через Jinja пака."""
    for path in sorted(version_dir.rglob("*")):
        rel = path.relative_to(version_dir).as_posix()
        if path.is_file() and path.suffix.lower() in _RENDERED_SUFFIXES:
            yield rel, path.read_text(encoding="utf-8")
        elif path.is_file() and path.suffix.lower() == ".pptx":
            with zipfile.ZipFile(path) as zf:
                for member in zf.namelist():
                    if _SLIDE_RE.match(member):
                        yield f"{rel}:{member}", zf.read(member).decode("utf-8")


def _form_sources(version_dir: Path) -> Iterator[tuple[str, str]]:
    manifest = yaml.safe_load((version_dir / "version.yaml").read_text(encoding="utf-8")) or {}
    for form in manifest.get("forms") or []:
        output = form.get("output") or {}
        if output.get("template"):
            yield output["template"], (version_dir / output["template"]).read_text(encoding="utf-8")


def _outcome(render: Callable[[], str]) -> tuple[str, str]:
    try:
        return ("ok", render())
    except Exception as exc:  # noqa: BLE001 — исход сравнивается вместе с типом ошибки
        return ("error", type(exc).__name__)


def _compile(env: Environment, source: str) -> Template | str:
    try:
        return env.from_string(source)
    except Exception as exc:  # noqa: BLE001
        return type(exc).__name__


def _compare(
    sources: Iterator[tuple[str, str]],
    contexts: list[tuple[str, dict[str, Any]]],
    old_env: Environment,
    new_env: SandboxedTemplateEnvironment,
) -> int:
    rendered = 0
    for name, source in sources:
        old_tmpl, new_tmpl = _compile(old_env, source), _compile(new_env, source)
        if isinstance(old_tmpl, str) or isinstance(new_tmpl, str):
            assert old_tmpl == new_tmpl, f"{name}: разбор разошёлся"
            continue
        for ctx_name, ctx in contexts:
            old = _outcome(lambda t=old_tmpl, c=ctx: t.render(c))
            new = _outcome(lambda t=new_tmpl, c=ctx: new_env.render_with_limits(t, c))
            assert new == old, f"{name} [{ctx_name}]: вывод песочницы отличается от прежнего"
            rendered += old[0] == "ok"
    return rendered


@pytest.mark.parametrize("version_dir", _version_dirs(), ids=lambda p: f"{p.parts[-5]}/{p.parts[-3]}/{p.parts[-1]}")
def test_pack_files_render_byte_for_byte(version_dir: Path) -> None:
    rendered = _compare(_pack_sources(version_dir), _pack_contexts(), _old_pack_env(), pack_environment())
    assert rendered > 0


@pytest.mark.parametrize("version_dir", _version_dirs(), ids=lambda p: f"{p.parts[-5]}/{p.parts[-3]}/{p.parts[-1]}")
def test_form_outputs_render_byte_for_byte(version_dir: Path) -> None:
    _compare(_form_sources(version_dir), _form_contexts(), _old_form_env(), form_environment())


def test_contexts_reach_branches() -> None:
    """Наборы данных не вырождены: полный и пустой дают разный титул, en отличается от ru."""
    meta = next(PACKS_ROOT.glob("hse-cs-sse/templates/coursework/versions/*/files/common/meta.tex.j2"))
    template = pack_environment().from_string(meta.read_text(encoding="utf-8"))
    outputs = {name: pack_environment().render_with_limits(template, ctx) for name, ctx in _pack_contexts()}
    assert len(set(outputs.values())) == len(outputs)
