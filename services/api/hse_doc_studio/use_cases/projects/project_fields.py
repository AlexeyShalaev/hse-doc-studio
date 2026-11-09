"""Поля проекта по описанию шаблона: определение из `meta_fields`, текущее значение и документы, где оно печатается.

Определения те же, что отдаёт каталог (`GET /catalog/.../versions/{version}`) и рисуют настройки проекта; поле,
не относящееся к виду работы проекта, настройки скрывают, здесь его тоже нет. Документы, где поле печатается,
считаются по исходникам шаблона (core.meta_usage): документ печатает поле, если подключает динамический инклуд и
использует его макрос с этим полем.
"""

from __future__ import annotations

import posixpath
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from hse_doc_studio.core.catalog import DocumentDefinition, MetaFieldDef, TemplateVersion
from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import MetaFieldType
from hse_doc_studio.core.meta_usage import (
    PERSON_KEYS,
    IncludeFields,
    input_targets,
    parse_include,
    printed_keys,
    referenced_keys,
    used_macros,
)
from hse_doc_studio.core.team import is_team

_SOURCE_SUFFIXES = (".tex", ".j2")
_MAX_FILES_PER_DOCUMENT = 400


@dataclass(frozen=True)
class ProjectField:
    key: str
    definition: MetaFieldDef
    # Значение в проекте: строка/флаг из project.meta, у поля-человека сам человек; None — не задано.
    value: object
    # Командный проект, поле scope=author: своё значение у каждого автора (slug → значение), пусто — наследуется.
    author_values: dict[str, object]
    # id документов шаблона, где поле печатается, в порядке документов шаблона.
    printed_in: tuple[str, ...]

    @property
    def is_person(self) -> bool:
        return self.definition.type is MetaFieldType.person or self.key in PERSON_KEYS


def visible_for_kind(definition: MetaFieldDef, kind: str) -> bool:
    """Как `metaFieldVisibleForKind` в настройках: пустой список видов значит «во всех»."""
    return not definition.supported_kinds or kind in definition.supported_kinds


def project_documents(project: Project, version: TemplateVersion) -> list[DocumentDefinition]:
    """Документы шаблона, которые есть в проекте этого вида работы и состава."""
    return [
        doc
        for doc in version.documents
        if project.kind in doc.supported_kinds and str(project.staffing) in doc.supported_staffing
    ]


def list_project_fields(project: Project, version: TemplateVersion, files_dir: Path | None) -> list[ProjectField]:
    """Все поля шаблона для проекта в порядке объявления; `files_dir` — каталог `files/` версии (None — не найден)."""
    documents = project_documents(project, version)
    printed = _printed_by_document(version, documents, files_dir) if files_dir is not None else {}
    team_authors = [a for a in project.authors if a.slug] if is_team(project) else []
    fields: list[ProjectField] = []
    for key, definition in version.meta_fields.items():
        if not visible_for_kind(definition, str(project.kind)):
            continue
        person = definition.type is MetaFieldType.person or key in PERSON_KEYS
        value = getattr(project, key, None) if person else project.meta.get(key)
        author_values = (
            {a.slug: a.meta.get(key) for a in team_authors if a.slug}
            if definition.scope == "author" and not person
            else {}
        )
        fields.append(
            ProjectField(
                key=key,
                definition=definition,
                value=value,
                author_values=author_values,
                printed_in=tuple(doc.id for doc in documents if key in printed.get(doc.id, set())),
            )
        )
    return fields


def _printed_by_document(
    version: TemplateVersion, documents: Iterable[DocumentDefinition], files_dir: Path
) -> dict[str, set[str]]:
    includes: dict[str, IncludeFields] = {}
    for include in version.dynamic_includes:
        path = files_dir / include.template
        if path.is_file():
            includes[_stem(include.output)] = parse_include(path.read_text(encoding="utf-8", errors="replace"))
    result: dict[str, set[str]] = {}
    for doc in documents:
        sources = [s for s in (doc.source_file, *(v.source_file for v in doc.variants)) if s]
        macros: set[str] = set()
        inputs: set[str] = set()
        text_keys: set[str] = set()
        for rel, text in _document_sources(files_dir, sources, set(includes)):
            macros |= used_macros(text)
            for target in input_targets(text):
                inputs.add(_stem(posixpath.normpath(posixpath.join(posixpath.dirname(rel), target))))
            # Исходник с Jinja (рендерится при создании проекта) ссылается на поле напрямую.
            text_keys |= referenced_keys(text)
        result[doc.id] = printed_keys(includes, macros, inputs, text_keys)
    return result


def _document_sources(files_dir: Path, sources: list[str], include_outputs: set[str]) -> list[tuple[str, str]]:
    """Исходники документа: файлы его папки в шаблоне и всё, что они подключают, кроме самих динамических инклудов."""
    queue = [rel for source in sources for rel in _bundle_files(files_dir, source)]
    seen: set[str] = set()
    result: list[tuple[str, str]] = []
    while queue and len(seen) < _MAX_FILES_PER_DOCUMENT:
        rel = queue.pop(0)
        path = files_dir / rel
        if rel in seen or not path.is_file():
            continue
        seen.add(rel)
        text = path.read_text(encoding="utf-8", errors="replace")
        result.append((rel, text))
        for target in input_targets(text):
            joined = posixpath.normpath(posixpath.join(posixpath.dirname(rel), target))
            if _stem(joined) not in include_outputs and not joined.startswith(".."):
                queue.extend(_resolve_input(files_dir, joined))
    return result


def _bundle_files(files_dir: Path, source: str) -> list[str]:
    """Исходники папки документа; документ в корне шаблона — только сам главный файл."""
    bundle = PurePosixPath(source).parent.as_posix()
    root = files_dir / bundle
    if bundle in {"", "."} or not root.is_dir():
        return [source]
    return [
        p.relative_to(files_dir).as_posix()
        for p in sorted(root.rglob("*"))
        if p.is_file() and p.name.endswith(_SOURCE_SUFFIXES)
    ]


def _resolve_input(files_dir: Path, target: str) -> list[str]:
    """Файл шаблона по аргументу `\\input`: как есть, с `.tex` или языковые варианты `<имя>.<язык>.tex`."""
    candidates = [target, f"{target}.tex"]
    found = [c for c in candidates if (files_dir / c).is_file()]
    if found:
        return found[:1]
    parent = (files_dir / target).parent
    name = PurePosixPath(target).name
    if not parent.is_dir():
        return []
    return [p.relative_to(files_dir).as_posix() for p in sorted(parent.glob(f"{name}.*.tex")) if p.is_file()]


def _stem(path: str) -> str:
    pure = PurePosixPath(path)
    return pure.with_suffix("").as_posix() if pure.suffix == ".tex" else pure.as_posix()
