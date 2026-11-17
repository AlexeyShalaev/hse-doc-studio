"""Правила линтера результата по файлам шаблонов: Jinja (раздел 6.1 дизайна результата, срез O8).

Два правила читают файлы версии, а не манифест, поэтому живут в infra и запускаются по кнопке (и в `pack check`):

* `jinja-fail-open` (ошибка): шаблон пака (`.tex`, `.md`, `.html`, `.txt`, `.cls`, `.sty`, `.bib`, исходники
  динамических инклудов `.j2`, слайды `.pptx`) падает при рендере, а загрузчик проекта молча копирует файл как есть, и в
  PDF попадают сырые `{{ ... }}`. Рендер идёт строгим режимом (`render_text_strict`, `TemplateRenderError`) на пробах:
  «пусто» (набор `auto:empty`, нет руководителей) и «непусто» (набор `auto:normal`, команда) по языкам и видам работы
  версии. Рендер в песочнице Jinja (`pack_environment`), в процессе api он идёт только через `PackJinjaProbe`:
  отдельный процесс с пределами времени и памяти над копией пака.
* `jinja-unknown-meta-key` (предупреждение): шаблон читает `project.meta.<ключ>`, а такого поля нет в `meta_fields`:
  значение всегда пустое. Разбор текстовый (`core/meta_usage.referenced_keys`).
"""

from __future__ import annotations

import asyncio
import re
import shutil
import tempfile
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import structlog.testing

from hse_doc_studio.core.catalog import PackInfo, TemplateInfo, TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.meta_usage import PERSON_KEYS, referenced_keys
from hse_doc_studio.core.pack_studio.outcome.inputs import input_specs, normalize_inputs
from hse_doc_studio.core.pack_studio.outcome.lint import LintFinding, finding
from hse_doc_studio.core.pack_studio.outcome.model import ElementRef
from hse_doc_studio.core.pack_studio.paths import VersionRef
from hse_doc_studio.core.pack_studio.preview import (
    AUTO_EMPTY,
    AUTO_NORMAL,
    SWITCH_ACADEMIC,
    SWITCH_CO_SUPERVISOR,
    SWITCH_KIND,
    SWITCH_LANG,
    SWITCH_STAFFING,
    SWITCH_SUPERVISOR,
    PreviewRenderError,
    auto_examples,
    synthetic_project,
)
from hse_doc_studio.core.team import project_bases
from hse_doc_studio.infra.pack_studio.preview_worker import StageLimits, VersionDirs, stage_version
from hse_doc_studio.infra.project_init.template_renderer import (
    TemplateRenderError,
    build_context,
    collect_sources_suffixed,
    render_text_strict,
)
from hse_doc_studio.infra.template.jinja_sandbox import IsolatedRenderError, IsolationLimits, call_isolated
from hse_doc_studio.infra.template.yaml_template_repository import (
    YamlTemplateRepository,
    parse_pack_manifest,
    parse_template_manifest,
)
from hse_doc_studio.use_cases.pack_studio.synthetic_project import synthetic_core_project

_TEXT_SUFFIXES = frozenset({".tex", ".md", ".html", ".txt", ".cls", ".sty", ".bib", ".j2"})
_SLIDE_XML = re.compile(r"^ppt/slides/slide\d+\.xml$")
_MARKERS = ("{{", "((*", "((#")
# Файлов, зашедших в рендер, и находок не больше этого: чужой пак не должен занять процесс надолго.
MAX_FILES = 400
MAX_FILE_BYTES = 1_000_000
_NEUTRAL_KEYS = frozenset({"nda"})


@dataclass(frozen=True, slots=True)
class _Probe:
    """Проба рендера: проект и подпись для сообщения (набор данных, язык, вид, состав, руководители)."""

    label: str
    project: Project


@dataclass(frozen=True, slots=True)
class _Source:
    rel: str
    text: str


def _combo(version: TemplateVersion, overrides: dict[str, str], defaults: dict[str, str]) -> dict[str, str]:
    return normalize_inputs(input_specs(version), overrides, defaults)


def _kinds_and_langs(version: TemplateVersion) -> tuple[list[str], list[str]]:
    specs = {spec.id: spec for spec in input_specs(version)}
    return list(specs[SWITCH_KIND].values), list(specs[SWITCH_LANG].values)


def _probes(version: TemplateVersion, today: date) -> Iterator[_Probe]:
    """Пробы: «пусто» и «непусто» по языкам и видам работы версии, плюс команда и проект без руководителей."""
    examples = {e.id: e for e in auto_examples(version)}
    normal, empty = examples[AUTO_NORMAL], examples[AUTO_EMPTY]
    kinds, langs = _kinds_and_langs(version)
    staffing = [spec for spec in input_specs(version) if spec.id == SWITCH_STAFFING][0].values
    team = next((value for value in staffing if value != "solo"), None)
    nobody = {SWITCH_SUPERVISOR: "none", SWITCH_CO_SUPERVISOR: "no", SWITCH_ACADEMIC: "no"}
    pairs = [(lang, kind) for lang in langs for kind in kinds]
    for lang, kind in pairs:
        base = {SWITCH_LANG: lang, SWITCH_KIND: kind}
        yield _probe("непусто", normal, {**base, SWITCH_STAFFING: staffing[0]}, version, today)
        yield _probe("пусто, без руководителей", empty, {**base, **nobody}, version, today)
    # Остальные пробы (пустой набор с руководителями, команда) на одной паре языка и вида: ветки шаблона от них
    # зависят слабо, а каждая проба это полный рендер всех файлов версии.
    base = {SWITCH_LANG: pairs[0][0], SWITCH_KIND: pairs[0][1]}
    yield _probe("пусто", empty, {**base, SWITCH_STAFFING: staffing[0]}, version, today)
    if team is not None:
        yield _probe("непусто, команда", normal, {**base, SWITCH_STAFFING: team}, version, today)


def _probe(label: str, example: Any, overrides: dict[str, str], version: TemplateVersion, today: date) -> _Probe:
    defaults = dict(example.data.defaults) if example.data is not None else {}
    combo = _combo(version, overrides, defaults)
    synthetic = synthetic_project(version, example, combo, today)
    project = synthetic_core_project(version.pack_id, version.template_id, version, synthetic)
    where = f"{label}; язык {combo[SWITCH_LANG]}, вид {combo[SWITCH_KIND]}, состав {combo[SWITCH_STAFFING]}"
    return _Probe(where, project)


def _is_text(path: Path) -> bool:
    return path.suffix.lower() in _TEXT_SUFFIXES


def _sources(files_dir: Path, version: TemplateVersion) -> list[_Source]:
    """Тексты файлов версии с Jinja: все языковые редакции и исходники динамических инклудов."""
    codes = version.langs or ("ru",)
    found: dict[str, Path] = {}
    for lang in codes:
        for path in collect_sources_suffixed(files_dir, tuple(codes), lang).values():
            found.setdefault(path.relative_to(files_dir).as_posix(), path)
    sources: list[_Source] = []
    for rel, path in sorted(found.items()):
        if len(sources) >= MAX_FILES:
            break
        text = _read(path)
        if text is not None and any(marker in text for marker in _MARKERS):
            sources.append(_Source(rel, text))
    sources.extend(_slides(found, files_dir))
    return sources


def _read(path: Path) -> str | None:
    try:
        if not _is_text(path) or path.stat().st_size > MAX_FILE_BYTES:
            return None
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _slides(found: dict[str, Path], files_dir: Path) -> Iterator[_Source]:
    """Слайды `.pptx` с плейсхолдерами Jinja: каждый слайд как отдельный шаблон (`файл.pptx!слайд`)."""
    for rel, path in sorted(found.items()):
        if path.suffix.lower() != ".pptx" or path.stat().st_size > MAX_FILE_BYTES * 20:
            continue
        try:
            with zipfile.ZipFile(path) as archive:
                for name in archive.namelist():
                    if _SLIDE_XML.match(name):
                        text = archive.read(name).decode("utf-8")
                        if any(marker in text for marker in _MARKERS):
                            yield _Source(f"{rel}!{name}", text)
        except (OSError, zipfile.BadZipFile, UnicodeDecodeError):
            continue


def _template_line(exc: BaseException) -> int | None:
    """Строка шаблона, где упал рендер: у синтаксической ошибки она в ошибке, у остальных в кадре `<template>`."""
    line = getattr(exc, "lineno", None)
    if isinstance(line, int):
        return line
    tb = exc.__traceback__
    found: int | None = None
    while tb is not None:
        if tb.tb_frame.f_code.co_filename in {"<template>", "<unknown>"}:
            found = tb.tb_lineno
        tb = tb.tb_next
    return found


def _contexts(probe: _Probe, version: TemplateVersion, infos: _Infos) -> Iterator[dict[str, Any]]:
    for _base_dir, author in project_bases(probe.project):
        yield build_context(probe.project, infos.pack, infos.template, version, author=author)


@dataclass(frozen=True, slots=True)
class _Infos:
    """Описание пака и шаблона для контекста рендера (`pack.id`, `template.id`)."""

    pack: PackInfo
    template: TemplateInfo


def _infos(version_dir: Path, version: TemplateVersion) -> _Infos:
    """Пак и шаблон версии по их манифестам (без загрузки остальных паков каталога)."""
    pack_dir, template_dir = version_dir.parents[3], version_dir.parents[1]
    with structlog.testing.capture_logs():
        pack = parse_pack_manifest(pack_dir / "pack.yaml") if (pack_dir / "pack.yaml").is_file() else None
        template = (
            parse_template_manifest(template_dir / "template.yaml", version.pack_id)
            if (template_dir / "template.yaml").is_file()
            else None
        )
    return _Infos(
        pack or PackInfo(version.pack_id, {}, {}, {}, "", ()),
        template or TemplateInfo(version.pack_id, version.template_id, {}, {}, {}, "", 0, version.version),
    )


def _fail_open(
    sources: Iterable[_Source], probes: Iterable[_Probe], version: TemplateVersion, infos: _Infos
) -> list[LintFinding]:
    """Первый провал каждого файла: дальше пробы по нему не идут, находка одна на файл."""
    failed: dict[str, LintFinding] = {}
    todo = list(sources)
    for probe in probes:
        contexts = list(_contexts(probe, version, infos))
        for source in todo:
            if source.rel in failed:
                continue
            for context in contexts:
                try:
                    render_text_strict(source.text, context, Path(source.rel))
                except TemplateRenderError as exc:
                    failed[source.rel] = _fail_finding(source, probe, exc)
                    break
    return list(failed.values())


def _fail_finding(source: _Source, probe: _Probe, exc: TemplateRenderError) -> LintFinding:
    cause = exc.cause
    reason = f"{type(cause).__name__}: {str(cause).splitlines()[0][:200] if str(cause) else ''}"
    file = f"files/{source.rel.split('!')[0]}"
    return LintFinding(
        "jinja-fail-open",
        "error",
        f"Шаблон {file} не рендерится ({probe.label}): {reason}. Сборка проекта в этом случае молча копирует файл "
        "как есть, и в PDF попадают сырые {{ ... }} (пустая страница или ошибка TeX вместо понятной причины).",
        "Исправьте выражение или защитите значение: `| default('')`, проверку `if`; пустая строка, отсутствие "
        "руководителя и команда не должны ронять рендер.",
        file,
        None,
        _template_line(cause),
    )


def _meta_findings(sources: Iterable[_Source], version: TemplateVersion) -> list[LintFinding]:
    declared = set(version.meta_fields) | set(PERSON_KEYS) | _NEUTRAL_KEYS
    found: list[LintFinding] = []
    for source in sources:
        unknown = sorted(referenced_keys(source.text) - declared)
        if unknown:
            file = f"files/{source.rel.split('!')[0]}"
            found.append(
                finding(
                    "jinja-unknown-meta-key",
                    "warning",
                    f"Шаблон {file} читает project.meta.{', project.meta.'.join(unknown)}, а такого поля нет в "
                    "meta_fields версии: значение всегда пустое.",
                    "Объявите поле в meta_fields или поправьте имя в шаблоне.",
                    file,
                    None,
                    ElementRef("meta", unknown[0]),
                )
            )
    return found


def jinja_findings(version_dir: Path, version: TemplateVersion, today: date) -> tuple[LintFinding, ...]:
    """Находки по файлам версии (каталог версии на диске). Версия без `files/` ничего не даёт."""
    files_dir = version_dir / "files"
    if not files_dir.is_dir():
        return ()
    sources = _sources(files_dir, version)
    with structlog.testing.capture_logs():
        failures = _fail_open(sources, _probes(version, today), version, _infos(version_dir, version))
    return (*failures, *_meta_findings(sources, version))


# ── Рендер в отдельном процессе (Студия) ─────────────────────────────────────


def probe_jinja(dirs: VersionDirs, stage: str, limits: StageLimits, today: date) -> tuple[LintFinding, ...]:
    """Цель `call_isolated`: копия пака без ссылок, лоадер и находки по файлам версии."""
    packs, pack_id, template_id, version_id = stage_version(dirs, Path(stage), limits)
    version = YamlTemplateRepository(packs).get_version(pack_id, template_id, version_id)
    if version is None:
        raise ValueError("version.yaml не разобран: проверьте манифест линтером")
    version_dir = packs / pack_id / "templates" / template_id / "versions" / version_id
    return jinja_findings(version_dir, version, today)


@dataclass(frozen=True)
class JinjaProbeLimits:
    timeout_s: float
    memory_bytes: int
    stage: StageLimits


class PackJinjaProbe:
    """Порт `IPackJinjaProbe`: рендер шаблонов чужого пака в отдельном процессе с пределами времени и памяти."""

    def __init__(self, tmp_dir: Path, limits: JinjaProbeLimits) -> None:
        self._tmp_dir = tmp_dir
        self._limits = limits

    async def probe(self, root: Path, ref: VersionRef, today: date) -> tuple[LintFinding, ...]:
        """Находки по файлам версии рабочего дерева; сбой процесса рендера это `PreviewRenderError`."""
        dirs = VersionDirs(str(root), ref.pack, ref.template, ref.version)
        try:
            return await asyncio.to_thread(self._run, dirs, today)
        except IsolatedRenderError as exc:
            raise PreviewRenderError(str(exc)) from exc

    def _run(self, dirs: VersionDirs, today: date) -> tuple[LintFinding, ...]:
        self._tmp_dir.mkdir(parents=True, exist_ok=True)
        stage = tempfile.mkdtemp(prefix="jinja-", dir=self._tmp_dir)
        limits = IsolationLimits(timeout_seconds=self._limits.timeout_s, memory_bytes=self._limits.memory_bytes)
        try:
            return call_isolated(probe_jinja, (dirs, stage, self._limits.stage, today), limits=limits)
        finally:
            shutil.rmtree(stage, ignore_errors=True)


__all__ = ["JinjaProbeLimits", "PackJinjaProbe", "jinja_findings", "probe_jinja"]
