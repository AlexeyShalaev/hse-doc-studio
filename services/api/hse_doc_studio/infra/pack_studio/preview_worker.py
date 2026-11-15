"""Работа предпросмотра внутри отдельного процесса (docs/design/template-studio.md, 6.3 и раздел 9).

Функции этого модуля вызывает `call_isolated` (spawn, предел времени и памяти): разбор YAML чужого пака и рендер
его шаблонов в процессе api не идут никогда. Пак сначала копируется во временную папку, и только обычные файлы:
символьные ссылки, служебное git и лишний объём отбрасываются, так что шаблон не дотянется ни до чего вне каталога
версии. Дальше работает тот же код, что создаёт проект: лоадер паков, `instantiate_base`,
`regenerate_dynamic_includes`, `instantiate_nda` (Jinja только в песочнице `pack_environment`).
"""

from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any

import structlog.testing
import yaml

from hse_doc_studio.core.catalog import TemplateVersion
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.enums import EngineType
from hse_doc_studio.core.meta_defaults import apply_meta_defaults
from hse_doc_studio.core.pack_studio.errors import PackStudioError
from hse_doc_studio.core.pack_studio.paths import (
    PACK_MANIFEST,
    RELEASES_FILE,
    TEMPLATE_MANIFEST,
    TEMPLATES_DIR,
    VERSIONS_DIR,
    validate_rel_path,
)
from hse_doc_studio.core.pack_studio.preview import (
    MaterializedDoc,
    MaterializeRequest,
    RawExample,
    VersionDescription,
)
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.team import doc_base_dir, project_bases
from hse_doc_studio.core.value_objects import ProjectLock
from hse_doc_studio.infra.project_init.template_renderer import (
    TemplateRenderer,
    instantiate_base,
    instantiate_nda,
    regenerate_dynamic_includes,
)
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.use_cases.projects.create_project import _build_documents

EXAMPLES_DIR = "examples"
_SKIP_NAMES = frozenset({".git", ".DS_Store", "Thumbs.db", "desktop.ini", "__pycache__"})
_EXAMPLE_SUFFIXES = (".yaml", ".yml")
# Узлов в разобранном примере не больше этого: YAML с якорями разворачивается в огромные структуры.
_EXAMPLE_NODES = 20_000


@dataclass(frozen=True)
class StageLimits:
    max_bytes: int
    max_files: int
    max_example_bytes: int = 64 * 1024
    max_examples: int = 50


@dataclass(frozen=True)
class VersionDirs:
    """Папки версии в рабочем пространстве (имена папок, как их видит дерево)."""

    root: str
    pack: str
    template: str
    version: str

    @property
    def pack_dir(self) -> Path:
        return Path(self.root) / self.pack

    @property
    def template_dir(self) -> Path:
        return self.pack_dir / TEMPLATES_DIR / self.template

    @property
    def version_dir(self) -> Path:
        return self.template_dir / VERSIONS_DIR / self.version


# ── Копия пака без ссылок ──────────────────────────────────────────────────


class _Budget:
    def __init__(self, limits: StageLimits) -> None:
        self.bytes_left = limits.max_bytes
        self.files_left = limits.max_files

    def take(self, size: int) -> None:
        self.bytes_left -= size
        self.files_left -= 1
        if self.bytes_left < 0 or self.files_left < 0:
            raise ValueError("каталог версии слишком большой для предпросмотра")


def regular_files(directory: Path) -> Iterator[tuple[str, Path, int]]:
    """Обычные файлы под папкой: (путь от папки, полный путь, размер). Ссылки и служебное git пропускаются."""
    for current, dirs, files in os.walk(directory, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in _SKIP_NAMES and not (Path(current) / d).is_symlink())
        base = Path(current)
        for name in sorted(files):
            if name in _SKIP_NAMES:
                continue
            full = base / name
            try:
                info = full.lstat()
            except OSError:
                continue
            if stat.S_ISREG(info.st_mode):
                yield full.relative_to(directory).as_posix(), full, info.st_size


def _copy_file(src: Path, dst: Path, budget: _Budget) -> None:
    try:
        info = src.lstat()
    except OSError:
        return
    if not stat.S_ISREG(info.st_mode):
        return
    budget.take(info.st_size)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst, follow_symlinks=False)


def _copy_tree(src: Path, dst: Path, budget: _Budget) -> None:
    for rel, full, size in regular_files(src):
        budget.take(size)
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(full, target, follow_symlinks=False)


def _manifest_id(path: Path, fallback: str) -> str:
    """`id` манифеста как имя папки копии: одна часть пути без `..` и разделителей, иначе `ValueError`."""
    regular = path.is_file() and not path.is_symlink()
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if regular else None
    raw = data.get("id") if isinstance(data, dict) else None
    value = str(raw) if raw not in (None, "") else fallback
    try:
        checked = validate_rel_path(value)
    except PackStudioError:
        raise ValueError(f"недопустимый id в {path.name}: {value!r}") from None
    if "/" in checked:
        raise ValueError(f"недопустимый id в {path.name}: {value!r}")
    return checked


def stage_version(dirs: VersionDirs, stage: Path, limits: StageLimits) -> tuple[Path, str, str, str]:
    """Копия манифестов пака и шаблона, реестра выпусков и каталога версии в раскладке по id.

    Лоадер и рендер ищут файлы версии по `<пак>/templates/<шаблон>/versions/<версия>` с id из манифестов, а папки
    в рабочем пространстве могут называться иначе. Возвращает папку паков копии и id пака, шаблона и версии.
    """
    if not dirs.version_dir.is_dir() or dirs.version_dir.is_symlink():
        raise ValueError("каталог версии не найден")
    pack_id = _manifest_id(dirs.pack_dir / PACK_MANIFEST, dirs.pack)
    template_id = _manifest_id(dirs.template_dir / TEMPLATE_MANIFEST, dirs.template)
    version_id = _manifest_id(dirs.version_dir / "version.yaml", dirs.version)
    packs = stage / "packs"
    template_dst = packs / pack_id / TEMPLATES_DIR / template_id
    budget = _Budget(limits)
    _copy_file(dirs.pack_dir / PACK_MANIFEST, packs / pack_id / PACK_MANIFEST, budget)
    _copy_file(dirs.template_dir / TEMPLATE_MANIFEST, template_dst / TEMPLATE_MANIFEST, budget)
    _copy_file(dirs.template_dir / RELEASES_FILE, template_dst / RELEASES_FILE, budget)
    _copy_tree(dirs.version_dir, template_dst / VERSIONS_DIR / version_id, budget)
    return packs, pack_id, template_id, version_id


# ── Примеры ────────────────────────────────────────────────────────────────


class _NodeBudget:
    def __init__(self) -> None:
        self.left = _EXAMPLE_NODES

    def plain(self, value: Any, depth: int = 0) -> Any:
        """Копия из словарей, списков и скаляров с пределом узлов и глубины: якоря YAML не разворачиваются."""
        self.left -= 1
        if self.left < 0 or depth > 20:  # noqa: PLR2004 — глубина примера
            raise ValueError("пример слишком большой")
        if isinstance(value, dict):
            return {str(k): self.plain(v, depth + 1) for k, v in value.items()}
        if isinstance(value, list):
            return [self.plain(v, depth + 1) for v in value]
        if value is None or isinstance(value, bool | int | float | str):
            return value
        return str(value)


def _read_example(path: Path, limits: StageLimits) -> RawExample:
    name = path.stem
    try:
        if path.stat().st_size > limits.max_example_bytes:
            return RawExample(name, None, "файл примера слишком большой")
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return RawExample(name, _NodeBudget().plain(raw))
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return RawExample(name, None, str(exc).splitlines()[0][:300] if str(exc) else type(exc).__name__)


def read_examples(dirs: VersionDirs, limits: StageLimits) -> tuple[RawExample, ...]:
    folder = dirs.template_dir / EXAMPLES_DIR
    if not folder.is_dir() or folder.is_symlink():
        return ()
    found = [
        full
        for rel, full, _size in regular_files(folder)
        if "/" not in rel and full.suffix.lower() in _EXAMPLE_SUFFIXES
    ]
    return tuple(_read_example(path, limits) for path in found[: limits.max_examples])


# ── Точки входа процесса ───────────────────────────────────────────────────


def describe_version(dirs: VersionDirs, stage: str, limits: StageLimits) -> VersionDescription:
    """Модель версии тем же лоадером, что у Студии, и сырые примеры шаблона."""
    packs, pack_id, template_id, version_id = stage_version(dirs, Path(stage), limits)
    version = YamlTemplateRepository(packs).get_version(pack_id, template_id, version_id)
    if version is None:
        raise ValueError("version.yaml не разобран: проверьте манифест линтером")
    return VersionDescription(pack_id, template_id, version, read_examples(dirs, limits))


def materialize_preview(
    dirs: VersionDirs, stage: str, limits: StageLimits, request: MaterializeRequest, dest: str
) -> MaterializedDoc:
    """Синтетический проект в `dest` тем же путём, что создание проекта, и что собирать."""
    return _materialize(dirs, Path(stage), limits, request, Path(dest))


def _warning_line(event: Mapping[str, Any]) -> str:
    extra = ", ".join(f"{k}={v}" for k, v in event.items() if k not in {"event", "log_level"})
    return f"{event.get('event', '')} ({extra})" if extra else str(event.get("event", ""))


def _materialize(
    dirs: VersionDirs, stage: Path, limits: StageLimits, request: MaterializeRequest, dest: Path
) -> MaterializedDoc:
    packs, pack_id, template_id, version_id = stage_version(dirs, stage, limits)
    repo = YamlTemplateRepository(packs)
    version = repo.get_version(pack_id, template_id, version_id)
    if version is None:
        raise ValueError("version.yaml не разобран: проверьте манифест линтером")
    project = _project(request, version, repo, dest)
    warnings = _render(project, version, repo)
    doc = next((d for d in project.documents if d.def_id == request.def_id), None)
    if doc is None:
        raise ValueError(f"документа {request.def_id!r} нет в проекте этой комбинации")
    source_file, engine, needs_compile = _source_of(project, doc, version)
    if not (dest / source_file).is_file():
        raise ValueError(f"исходник документа не появился в проекте: {source_file}")
    return MaterializedDoc(
        doc_id=doc.id,
        def_id=doc.def_id,
        source_file=source_file,
        base_dir=doc_base_dir(project, doc),
        engine=engine.value,
        needs_compile=needs_compile,
        default_passes=version.engine_config.passes,
        warnings=warnings,
    )


def _render(project: Project, version: TemplateVersion, repo: YamlTemplateRepository) -> tuple[str, ...]:
    """Файлы пака по базам, динамические инклуды и NDA, как `create_project._render_template_files`.

    Рендер глотает ошибки Jinja (файл копируется как есть) и пишет предупреждение: автору пака они нужны в журнале.
    """
    renderer = TemplateRenderer()
    with structlog.testing.capture_logs() as events:
        for base_dir, author in project_bases(project):
            instantiate_base(project, version, repo, renderer, base_dir, author)
        regenerate_dynamic_includes(project, version, repo)
        instantiate_nda(project, version, repo)
    return tuple(_warning_line(e) for e in events if e.get("log_level") in {"warning", "error"})[:50]


def _source_of(project: Project, doc: Document, version: TemplateVersion) -> tuple[str, EngineType, bool]:
    """Исходник, движок и нужна ли сборка, как в `TriggerCompileUC`: вариант без движка только копируется."""
    service = ProjectTemplateService()
    doc_def = service.find_definition(version, doc)
    if doc_def is None:
        raise ValueError(f"определение документа {doc.def_id!r} не найдено")
    source_file, _output = service.resolve_instance_source(project, doc, version)
    if not doc_def.variants:
        return source_file, project.lock.engine, True
    variant = next((v for v in doc_def.variants if v.id == doc.chosen_variant), doc_def.variants[0])
    if variant.engine is None:
        return source_file, project.lock.engine, False
    return source_file, variant.engine, True


def _project(
    request: MaterializeRequest, version: TemplateVersion, repo: YamlTemplateRepository, dest: Path
) -> Project:
    """`Project` в памяти из синтетических данных: документы и мета как у `CreateProjectUC`."""
    synthetic = request.project
    authors = list(synthetic.authors)
    created = datetime.combine(synthetic.today, time(12, 0), tzinfo=UTC)
    dest.mkdir(parents=True, exist_ok=True)
    return Project(
        id=request.build_id,
        name=synthetic.name,
        folder=dest,
        lock=ProjectLock(
            pack_id=request.pack_id,
            template_id=request.template_id,
            version=request.version_id,
            engine=version.engine_config.default,
            digest=repo.content_digest(request.pack_id, request.template_id, request.version_id),
        ),
        kind=synthetic.kind,
        staffing=synthetic.staffing,
        lang=synthetic.lang,
        authors=authors,
        meta=apply_meta_defaults(version, dict(synthetic.meta), synthetic.today),
        supervisor=synthetic.supervisor,
        co_supervisor=synthetic.co_supervisor,
        academic_supervisor=synthetic.academic_supervisor,
        documents=_build_documents(
            version, None, staffing=synthetic.staffing, authors=authors, shared_enabled=True, kind=synthetic.kind
        ),
        created_at=created,
        updated_at=created,
    )
