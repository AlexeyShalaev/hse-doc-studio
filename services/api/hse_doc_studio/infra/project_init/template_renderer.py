from __future__ import annotations

import html
import re
import shutil
import zipfile
from pathlib import Path
from typing import Any

import structlog
from jinja2 import ChainableUndefined, Environment, TemplateSyntaxError, UndefinedError

from hse_doc_studio.core.catalog import (
    DocumentDefinition,
    PackInfo,
    TemplateInfo,
    TemplateVersion,
)
from hse_doc_studio.core.doc_dirs import def_dirs, def_source_dirs
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.repositories import ITemplateRepository
from hse_doc_studio.core.team import (
    author_by_slug,
    doc_base_dir,
    effective_meta,
    is_team,
    nda_bases,
    prefix_path,
    project_bases,
)
from hse_doc_studio.core.value_objects import Author

logger = structlog.get_logger()

_BINARY_EXTENSIONS: frozenset[str] = frozenset(
    {".pptx", ".png", ".jpg", ".jpeg", ".pdf", ".gif", ".ico", ".bin", ".ttf", ".otf", ".woff", ".woff2"}
)

_TEXT_EXTENSIONS: frozenset[str] = frozenset({".tex", ".md", ".html", ".txt", ".cls", ".sty", ".bib"})

# ── Bundle-раскладка пака (языковые суффиксы имён) ──────────────
# Дерево files/ СОВПАДАЕТ с деревом проекта (bundle files/<doc_id>/ == папке
# документа), а язык выражается суффиксом имени `<stem>.<код>.<ext>`
# (`operator_manual.ru.tex` / `.en.tex`). Коды распознаются ТОЛЬКО из
# объявленного top-level `langs:` version.yaml (первый в списке = дефолт и
# фолбэк; версия без `langs:` получает дефолт `ru`); файл БЕЗ суффикса —
# единственная форма для всех языков (ISO/IEEE-варианты, nda, ассеты, *.j2).
# Резолюция по-файлово: язык проекта → дефолт → bare → (только
# сироты-переводы) первый по алфавиту. Выбранный файл материализуется под
# базовым именем `<stem>.<ext>` — проект суффиксов не видит. Механизм един
# для текста и бинарников (pptx). Новый язык = файлы-соседи `.de.*` + код в
# `langs:` — правок кода не требуется. `doc.yaml` — манифест bundle, в проект
# не копируется. Санитарные проверки раскладки — infra.template.pack_lint.
PACK_DOC_MANIFEST = "doc.yaml"
DEFAULT_TEMPLATE_LANG = "ru"


def _split_lang_qualifier(rel_posix: str, codes: tuple[str, ...]) -> tuple[str, str]:
    """(bare rel-путь, код) для имени файла пака; код "" — файл без суффикса.

    Квалификатор — ПРЕДПОСЛЕДНИЙ dot-сегмент имени и только из объявленных
    кодов: `meta.tex.j2` («tex» не код) и легитимные точки в именах не ловятся.
    """
    parent, _, name = rel_posix.rpartition("/")
    parts = name.split(".")
    if len(parts) >= 3 and parts[-2] in codes:
        bare_name = ".".join(parts[:-2]) + "." + parts[-1]
        return ((parent + "/" if parent else "") + bare_name, parts[-2])
    return (rel_posix, "")


def collect_sources_suffixed(
    version_files_dir: Path,
    lang_codes: tuple[str, ...],
    project_lang: str,
) -> dict[str, Path]:
    """Сбор источников пака: группировка по bare-пути + выбор языковой редакции."""
    default_lang = lang_codes[0]
    groups: dict[str, dict[str, Path]] = {}
    for src_file in version_files_dir.rglob("*"):
        if not src_file.is_file() or src_file.name == PACK_DOC_MANIFEST:
            continue
        rel = src_file.relative_to(version_files_dir).as_posix()
        bare, code = _split_lang_qualifier(rel, lang_codes)
        groups.setdefault(bare, {})[code] = src_file
    sources: dict[str, Path] = {}
    for bare, by_code in groups.items():
        pick = by_code.get(project_lang) or by_code.get(default_lang) or by_code.get("")
        if pick is None:
            # Группа только из сирот-переводов (нет ни дефолта, ни bare) —
            # детерминированный фолбэк; pack lint помечает это предупреждением.
            pick = by_code[sorted(by_code)[0]]
        sources[bare] = pick
    return sources


def _person_dict(person: Any) -> dict[str, str]:
    """Flatten a Person value object for the Jinja context.

    Returns {} (not None) when there is no person, so `project.supervisor.name`
    resolves to "" via ChainableUndefined instead of raising.
    """
    if person is None:
        return {}
    return {
        "name": person.name,
        "role": str(person.role),
        "title": person.title or "",
        "degree": person.degree or "",
    }


def _author_dict(author: Author | None) -> dict[str, Any]:
    """Flatten an Author for the Jinja context ({} when there is none)."""
    if author is None:
        return {}
    return {
        "name": author.name,
        "group": author.group or "",
        "email": author.email or "",
        "slug": author.slug or "",
        "topic": author.topic or "",
        "meta": dict(author.meta),
    }


def build_context(
    project: Project,
    pack_info: PackInfo,
    template_info: TemplateInfo,
    version: TemplateVersion,
    author: Author | None = None,
) -> dict[str, Any]:
    """Build Jinja2 rendering context from domain objects.

    The whole `Project` is flattened here, so the same context serves both the
    one-time creation copy and the per-compile regeneration of dynamic includes
    (see `regenerate_dynamic_includes`). `supervisor`/`co_supervisor` are
    included — historically they were not, so `project.supervisor.name` rendered
    empty on the title page.

    `author` — владелец рендеримой БАЗЫ (team mode). Его контекст:
    - `author.*` — имя/группа/тема владельца ({} для shared-базы и когда
      автор не передан — solo-вызовы без изменений передают None, и тогда
      владельцем считается единственный автор);
    - `project.meta` в контексте — ЭФФЕКТИВНАЯ мета базы: авторские значения
      (scope=author: doc_code_base/udc/name_en/…) поверх системных, поэтому
      существующие шаблоны продолжают читать `project.meta.*` без изменений.
    Для shared-базы значения остаются системными (project.meta как есть).
    """
    if author is None and not is_team(project) and project.authors:
        # Solo: единственный автор и есть владелец комплекта.
        author = project.authors[0]
    return {
        "project": {
            "name": project.name,
            "lang": project.lang,
            "kind": project.kind,
            "staffing": project.staffing,
            # Черновики из настроек (пустое имя) в PDF не попадают: иначе
            # \hseAuthorsList и блок исполнителей общего ТЗ получили бы
            # пустые строки подписей.
            "authors": [
                {
                    "name": a.name,
                    "group": a.group,
                    "email": a.email,
                    "slug": a.slug or "",
                    "topic": a.topic or "",
                    "managed": a.managed,
                    "meta": dict(a.meta),
                }
                for a in project.authors
                if a.name.strip()
            ],
            "meta": effective_meta(project, author),
            "supervisor": _person_dict(project.supervisor),
            "co_supervisor": _person_dict(project.co_supervisor),
            "academic_supervisor": _person_dict(project.academic_supervisor),
            "created_at": project.created_at.isoformat(),
        },
        "author": _author_dict(author),
        "team": {
            "is_team": is_team(project),
            # Владелец базы задан → личная база; team без владельца → shared.
            "is_shared_base": is_team(project) and author is None,
        },
        "pack": {"id": pack_info.id},
        "template": {
            "id": template_info.id,
            "version": version.version,
        },
    }


# Order matters: backslash must be escaped first or it doubles the replacements
# that themselves introduce backslashes. Mirrors the standard LaTeX-escape map.
_TEX_ESCAPES: tuple[tuple[str, str], ...] = (
    ("\\", r"\textbackslash{}"),
    ("&", r"\&"),
    ("%", r"\%"),
    ("$", r"\$"),
    ("#", r"\#"),
    ("_", r"\_"),
    ("{", r"\{"),
    ("}", r"\}"),
    ("~", r"\textasciitilde{}"),
    ("^", r"\textasciicircum{}"),
)


def _texesc(value: Any) -> str:
    """Escape LaTeX special characters in user-supplied data.

    Exposed as the `texesc` Jinja filter so generated includes (meta.tex) can
    inject names/titles that contain `&`, `_`, `%`, … without breaking xelatex.
    """
    text = "" if value is None else str(value)
    for char, repl in _TEX_ESCAPES:
        text = text.replace(char, repl)
    return text


def _xmlesc(value: Any) -> str:
    """Escape XML/HTML special characters (incl. quotes) in user-supplied data.

    Exposed as the `xmlesc` Jinja filter for placeholders inside pptx slide XML
    (see `_copy_pptx_rendered`): names/topics with `&`, `<`, `"` must not break
    the OOXML markup the same way `texesc` guards xelatex.
    """
    return html.escape("" if value is None else str(value), quote=True)


def _is_binary(path: Path) -> bool:
    return path.suffix.lower() in _BINARY_EXTENSIONS


def _should_render(path: Path) -> bool:
    return path.suffix.lower() in _TEXT_EXTENSIONS


def _render_text(content: str, context: dict[str, Any], source_path: Path) -> str:
    """Render Jinja2 template; return original content on hard errors.

    Uses ChainableUndefined so missing chained attributes (e.g. project.meta.foo
    when meta has no `foo`) render as empty string instead of leaking raw
    `{{ ... }}` into the output and breaking downstream tools (e.g. xelatex).
    Hard syntax errors still fall back to a verbatim copy + warning so the
    user sees the unrendered file rather than silently losing it.
    """
    try:
        # LaTeX collides hard with Jinja's default {% %} / {# #} delimiters:
        # idioms like `\caption{% подпись}` (comment-eats-newline) and `{#1}`
        # (macro parameters, e.g. \newcommand{..}{#1}) get parsed as a Jinja
        # block / comment and raise TemplateSyntaxError — which sends the WHOLE
        # file through the verbatim fallback below, leaving real `{{ ... }}`
        # placeholders unrendered (literal "{{ project.name }}" lands in the
        # PDF). Keep the variable delimiter as `{{ }}` (every template already
        # uses it) but move block/comment to sequences that never occur in
        # LaTeX. NOTE: Jinja control blocks in templates must use `((* ... *))`
        # / `((# ... #))` accordingly (see pres beamer template).
        env = Environment(  # noqa: S701
            undefined=ChainableUndefined,
            keep_trailing_newline=True,
            block_start_string="((*",
            block_end_string="*))",
            comment_start_string="((#",
            comment_end_string="#))",
        )
        env.filters["texesc"] = _texesc
        env.filters["xmlesc"] = _xmlesc
        template = env.from_string(content)
        return template.render(**context)
    except TemplateSyntaxError as exc:
        logger.warning(
            "jinja2 syntax error, copying as-is",
            path=str(source_path),
            exc=str(exc),
        )
        return content
    except UndefinedError as exc:
        logger.warning(
            "jinja2 undefined variable, copying as-is",
            path=str(source_path),
            exc=str(exc),
        )
        return content
    except Exception as exc:
        logger.warning(
            "jinja2 render error, copying as-is",
            path=str(source_path),
            exc=str(exc),
        )
        return content


# Слайды официального pptx-шаблона несут Jinja-плейсхолдеры прямо в XML —
# рендерим ТОЛЬКО их, остальные члены архива не трогаем.
_PPTX_SLIDE_XML_RE = re.compile(r"^ppt/slides/slide\d+\.xml$")


class TemplateRenderer:
    """Copies template files into a project folder, rendering Jinja2 templates."""

    def render_and_copy(  # noqa: C901, PLR0912
        self,
        version_files_dir: Path,
        dest_folder: Path,
        context: dict[str, Any],
        skip_rel_files: frozenset[str] = frozenset(),
        extra_skip_dirs: frozenset[Path] = frozenset(),
        skip_existing: bool = False,
        lang_codes: tuple[str, ...] | None = None,
    ) -> list[str]:
        """
        Copy files from version_files_dir into dest_folder.
        - Text files (.tex, .md, etc.) are rendered through Jinja2.
        - Binary files (.png, .pdf, etc.) are copied as-is.
        - .pptx are copied as zip with slide XMLs rendered through Jinja2
          (see `_copy_pptx_rendered`); on any error — verbatim copy.
        - ALL variant directories are copied: смена варианта — lossless, файлы
          вариантов никогда не удаляются и не пропускаются при создании.
        - `lang_codes` (top-level `langs:` версии; None → дефолт `ru`) —
          коды языковых суффиксов: источники собираются суффикс-резолвером
          (`collect_sources_suffixed`), rel-пути — bare (без суффиксов) и
          совпадают с раскладкой проекта.
        - `skip_rel_files` (posix rel paths) are NOT copied: these are dynamic
          include SOURCES (e.g. `common/meta.tex.j2`) whose rendered OUTPUT is
          written separately by `regenerate_dynamic_includes`.
        - `extra_skip_dirs` are whole directories never copied here (e.g. the
          NDA file group, materialised conditionally by `instantiate_nda`).
        - `skip_existing=True` — существующие файлы назначения НЕ трогаются
          (правки студента не перезаписываются), докладываются только
          отсутствующие.
        Returns the POSIX dest (project-space) rel paths of files actually written.
        """
        if not version_files_dir.exists():
            logger.warning("version_files_dir does not exist", path=str(version_files_dir))
            return []

        skip_dirs: set[Path] = {d.resolve() for d in extra_skip_dirs}
        written: list[str] = []
        # Язык проекта — выбор языковой редакции каждого файла.
        lang = str((context.get("project") or {}).get("lang") or "ru").lower()
        sources = collect_sources_suffixed(version_files_dir, lang_codes or (DEFAULT_TEMPLATE_LANG,), lang)

        for rel_posix, src_file in sources.items():
            # Файлы лежат по своим bare-путям (суффикс — только в имени),
            # поэтому абсолютной проверки skip-каталогов достаточно.
            if self._is_under_skipped_dir(src_file, skip_dirs):
                continue

            if rel_posix in skip_rel_files:
                continue

            dest_rel = rel_posix
            dest_file = dest_folder / dest_rel
            if skip_existing and dest_file.exists():
                logger.debug("skipped existing file", dest=str(dest_file))
                continue
            dest_file.parent.mkdir(parents=True, exist_ok=True)

            if src_file.suffix.lower() == ".pptx":
                # .pptx остаётся в _BINARY_EXTENSIONS (другие потоки полагаются
                # на это), но здесь ветвимся раньше: слайды рендерятся Jinja.
                self._copy_pptx_rendered(src_file, dest_file, context)
                written.append(dest_rel)
            elif _is_binary(src_file):
                shutil.copy2(src_file, dest_file)
                logger.debug("copied binary", src=str(src_file), dest=str(dest_file))
                written.append(dest_rel)
            elif _should_render(src_file):
                try:
                    content = src_file.read_text(encoding="utf-8")
                    rendered = _render_text(content, context, src_file)
                    dest_file.write_text(rendered, encoding="utf-8")
                    logger.debug("rendered text", src=str(src_file), dest=str(dest_file))
                    written.append(dest_rel)
                except Exception as exc:
                    logger.warning(
                        "text file copy error, skipping",
                        src=str(src_file),
                        exc=str(exc),
                    )
            else:
                # Unknown extension — copy as-is
                shutil.copy2(src_file, dest_file)
                logger.debug("copied as-is", src=str(src_file), dest=str(dest_file))
                written.append(dest_rel)
        return written

    def _copy_pptx_rendered(self, src_file: Path, dest_file: Path, context: dict[str, Any]) -> None:
        """Копирует .pptx как zip, прогоняя slide-XML через Jinja.

        Официальный университетский pptx-шаблон несёт плейсхолдеры пака
        (`{{ author.name | xmlesc }}`, `((* if ... *))`) прямо в
        `ppt/slides/slide*.xml`. Рендерим только слайды, и только если в них
        есть маркеры Jinja; все остальные члены архива копируются
        байт-в-байт с сохранением порядка. Любая ошибка (битый zip, не-utf8,
        ...) — предупреждение и честный copy2: создание проекта не должно
        падать из-за презентации.
        """
        try:
            with zipfile.ZipFile(src_file, "r") as src_zip:
                members = [(info, src_zip.read(info.filename)) for info in src_zip.infolist()]
            with zipfile.ZipFile(dest_file, "w", zipfile.ZIP_DEFLATED) as dest_zip:
                for info, data in members:
                    payload = data
                    if _PPTX_SLIDE_XML_RE.match(info.filename):
                        text = data.decode("utf-8")
                        if "{{" in text or "((*" in text:
                            payload = _render_text(text, context, src_file).encode("utf-8")
                    # Свежий ZipInfo: имя/дата — из исходника, без унаследованных
                    # флагов (data descriptor и т.п.), сжатие — ZIP_DEFLATED.
                    out_info = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                    out_info.external_attr = info.external_attr
                    out_info.compress_type = zipfile.ZIP_DEFLATED
                    dest_zip.writestr(out_info, payload)
            logger.debug("rendered pptx", src=str(src_file), dest=str(dest_file))
        except Exception as exc:
            logger.warning("pptx render error, copying as-is", src=str(src_file), exc=str(exc))
            shutil.copy2(src_file, dest_file)

    def _is_under_skipped_dir(self, file_path: Path, skip_dirs: set[Path]) -> bool:
        """Check if a file path is inside any of the skipped directories."""
        resolved = file_path.resolve()
        for skip_dir in skip_dirs:
            try:
                resolved.relative_to(skip_dir)
            except ValueError:
                pass
            else:
                return True
        return False


def version_files_dir(template_repo: ITemplateRepository, version: TemplateVersion) -> Path | None:
    """Locate a version's authored `files/` directory.

    Duck-types `_packs_dir` off the YAML repository (same access pattern as
    `CreateProjectUC`), so this stays usable without threading the path through
    every call site.
    """
    packs_dir = getattr(template_repo, "_packs_dir", None)
    if packs_dir is None:
        return None
    return (
        Path(packs_dir) / version.pack_id / "templates" / version.template_id / "versions" / version.version / "files"
    )


def build_render_context(
    project: Project,
    version: TemplateVersion,
    template_repo: ITemplateRepository,
    author: Author | None = None,
) -> dict[str, Any] | None:
    """Resolve pack/template info and build the Jinja context for a project."""
    packs = template_repo.list_packs()
    pack_info = next((p for p in packs if p.id == version.pack_id), None)
    if pack_info is None:
        return None
    template_info = next((t for t in pack_info.templates if t.id == version.template_id), None)
    if template_info is None:
        return None
    return build_context(project, pack_info, template_info, version, author=author)


# Каталоги-владельцы определений (def_dirs/def_source_dirs) вынесены в
# core.doc_dirs — ЕДИНЫЙ источник правды: инстанциация файлов здесь и
# атрибуция файлов к документам в core.services пользуются одними функциями.


def _skip_all_but(files_dir: Path, keep_src: set[str], version: TemplateVersion) -> set[Path]:
    """extra_skip-набор: всё, кроме каталогов доков из `keep_src`.

    Пропускаем целиком верхнеуровневые каталоги, не ведущие к нужным докам
    (common/, assets/, ai-usage/, чужие документы), и вложенные
    doc-каталоги-соседи внутри общего верхнего уровня, не входящие в keep_src.
    Так докладывается ровно нужный документ, а правки в остальных файлах базы
    не затрагиваются.
    """
    keep_tops = {src.split("/", 1)[0] for src in keep_src}
    skip = {entry.resolve() for entry in files_dir.iterdir() if entry.is_dir() and entry.name not in keep_tops}
    all_src = {src for doc_def in version.documents for src in def_source_dirs(doc_def)}
    for src in all_src:
        if src not in keep_src and src.split("/", 1)[0] in keep_tops:
            skip.add((files_dir / src).resolve())
    return skip


def _def_in_base(doc_def: DocumentDefinition, *, team: bool, shared_base: bool, kind: str) -> bool:
    """Существует ли документ определения в данной базе раскладки.

    `kind` — формат ВКР проекта (research/project): документ другого формата в
    базу не попадает (его файлы-скелет не копируются)."""
    if kind not in doc_def.supported_kinds:
        return False
    if not team:
        return "solo" in doc_def.supported_staffing
    if "team" not in doc_def.supported_staffing:
        return False
    return (doc_def.scope == "shared") == shared_base


def instantiate_base(
    project: Project,
    version: TemplateVersion,
    template_repo: ITemplateRepository,
    renderer: TemplateRenderer,
    base_dir: str,
    author: Author | None,
) -> None:
    """Материализует одну базу раскладки из пака.

    Solo (`base_dir=""`) — корень проекта, как раньше. Team — `shared/` или
    `<slug>/`: копируются служебные каталоги (common/, assets/, …) плюс папки
    ТОЛЬКО тех документов, что принадлежат базе (personal → автору,
    shared → shared-базе); NDA и исходники dynamic includes пропускаются
    всегда. Идемпотентна на уровне render_and_copy (файлы перезаписываются
    из пака) — вызывающий довключения обязан сам не трогать существующие базы.
    """
    files_dir = version_files_dir(template_repo, version)
    if files_dir is None or not files_dir.exists():
        logger.warning("instantiate_base: version files dir missing", base=base_dir or ".")
        return
    team = is_team(project)
    shared_base = team and author is None
    included: set[str] = set()
    excluded: set[str] = set()
    for doc_def in version.documents:
        dirs = def_source_dirs(doc_def)
        if _def_in_base(doc_def, team=team, shared_base=shared_base, kind=project.kind.value):
            included |= dirs
        else:
            excluded |= dirs
    # Каталог, где живут и включённый, и исключённый док, не пропускаем.
    extra_skip = {(files_dir / d).resolve() for d in excluded - included}
    nda_dir = nda_source_dir(template_repo, version)
    if nda_dir is not None:
        extra_skip.add(nda_dir.resolve())
    context = build_render_context(project, version, template_repo, author=author)
    if context is None:
        logger.warning("instantiate_base: cannot build context", project_id=str(project.id))
        return
    renderer.render_and_copy(
        version_files_dir=files_dir,
        dest_folder=project.folder / base_dir if base_dir else project.folder,
        context=context,
        skip_rel_files=frozenset(inc.template for inc in version.dynamic_includes),
        extra_skip_dirs=frozenset(extra_skip),
        lang_codes=version.langs or None,
    )


def instantiate_missing_base_parts(
    project: Project,
    version: TemplateVersion,
    template_repo: ITemplateRepository,
    renderer: TemplateRenderer,
    base_dir: str,
    author: Author | None,
) -> list[str]:
    """Докладывает в СУЩЕСТВУЮЩУЮ базу каталоги доков, которых в ней ещё нет.

    Нужна довключению комплекта, когда пак получил новые определения
    документов уже ПОСЛЕ материализации базы (например, pmi_shared):
    instantiate_base существующую базу не трогает, а новому доку нужны
    исходники. Копируются ТОЛЬКО отсутствующие top-level каталоги доков этой
    базы; существующие каталоги и корневые файлы базы не перезаписываются.
    Возвращает список доложенных каталогов (пустой — база уже полна).
    """
    files_dir = version_files_dir(template_repo, version)
    if files_dir is None or not files_dir.exists():
        logger.warning("instantiate_missing_base_parts: version files dir missing", base=base_dir or ".")
        return []
    dest = project.folder / base_dir if base_dir else project.folder
    if not dest.exists():
        logger.warning("instantiate_missing_base_parts: base does not exist", base=base_dir or ".")
        return []
    team = is_team(project)
    shared_base = team and author is None
    # Каталоги документов этой базы (пак == проект: одно пространство путей).
    doc_dirs: set[str] = set()
    for doc_def in version.documents:
        if _def_in_base(doc_def, team=team, shared_base=shared_base, kind=project.kind.value):
            doc_dirs |= def_dirs(doc_def)
    missing = {d for d in doc_dirs if not (dest / d).exists()}
    if not missing:
        return []
    context = build_render_context(project, version, template_repo, author=author)
    if context is None:
        logger.warning("instantiate_missing_base_parts: cannot build context", project_id=str(project.id))
        return []
    # Пропускаем всё, кроме недостающих доков: остальные каталоги пака — целиком,
    # корневые файлы пака — через skip_rel_files (они уже лежат в базе,
    # перезапись затёрла бы правки студента).
    extra_skip = _skip_all_but(files_dir, keep_src=missing, version=version)
    root_files = {entry.name for entry in files_dir.iterdir() if entry.is_file()}
    renderer.render_and_copy(
        version_files_dir=files_dir,
        dest_folder=dest,
        context=context,
        skip_rel_files=frozenset(root_files) | frozenset(inc.template for inc in version.dynamic_includes),
        extra_skip_dirs=frozenset(extra_skip),
        lang_codes=version.langs or None,
    )
    added = sorted(missing)
    logger.info("materialised missing doc dirs", base=base_dir or ".", dirs=added)
    return added


def instantiate_missing_doc_files(
    project: Project,
    version: TemplateVersion,
    template_repo: ITemplateRepository,
    renderer: TemplateRenderer,
    doc: Document,
) -> list[str]:
    """Докладывает в базу документа ОТСУТСТВУЮЩИЕ файлы его исходников.

    В отличие от instantiate_missing_base_parts (целые недостающие каталоги),
    здесь докладываются отдельные файлы ВНУТРИ возможно существующего каталога
    (skip_existing=True) — правки студента никогда не перезаписываются.
    Нужна смене варианта документа: проекты, созданные до материализации всех
    вариантов, несут файлы только одного варианта. Копируются исходники ВСЕХ
    вариантов данного определения; база документа — как в project_bases:
    solo → корень (владелец = единственный автор), team personal → папка
    владельца, shared → shared-база (системный контекст). Возвращает список
    реально доложенных rel-путей ([] — всё уже на месте).
    """
    doc_def = next((d for d in version.documents if d.id == doc.def_id), None)
    if doc_def is None:
        logger.warning("instantiate_missing_doc_files: definition not found", def_id=doc.def_id)
        return []
    files_dir = version_files_dir(template_repo, version)
    if files_dir is None or not files_dir.exists():
        logger.warning("instantiate_missing_doc_files: version files dir missing", def_id=doc.def_id)
        return []
    source_dirs = def_source_dirs(doc_def)
    if not source_dirs:
        return []
    base_dir = doc_base_dir(project, doc)
    author = author_by_slug(project, doc.owner)
    context = build_render_context(project, version, template_repo, author=author)
    if context is None:
        logger.warning("instantiate_missing_doc_files: cannot build context", project_id=str(project.id))
        return []
    # Пропускаем всё, кроме source-каталогов самого дока (см. _skip_all_but);
    # корневые файлы и исходники dynamic includes — через skip_rel_files.
    extra_skip = _skip_all_but(files_dir, keep_src=source_dirs, version=version)
    root_files = {entry.name for entry in files_dir.iterdir() if entry.is_file()}
    created = renderer.render_and_copy(
        version_files_dir=files_dir,
        dest_folder=project.folder / base_dir if base_dir else project.folder,
        context=context,
        skip_rel_files=frozenset(root_files) | frozenset(inc.template for inc in version.dynamic_includes),
        extra_skip_dirs=frozenset(extra_skip),
        skip_existing=True,
        lang_codes=version.langs or None,
    )
    if created:
        logger.info("materialised missing doc files", doc_id=doc.id, files=created)
    return created


def regenerate_dynamic_includes(
    project: Project,
    version: TemplateVersion,
    template_repo: ITemplateRepository,
) -> None:
    """(Re)render every `DynamicInclude` from the project into its folder.

    Called at project creation AND before every compile, so changeable data
    (author/supervisor names, group, NDA flag, …) is always current in the
    build without re-rendering the user's own `.tex` files. Errors are logged
    and swallowed: a missing/broken include must never abort a compile — the
    build falls back to the previously generated file.
    """
    if not version.dynamic_includes:
        return
    files_dir = version_files_dir(template_repo, version)
    if files_dir is None:
        logger.warning("regenerate_dynamic_includes: template_repo has no _packs_dir")
        return
    # Solo — одна база (корень); team — каждая база получает СВОЙ комплект
    # dynamic includes (meta.tex с темой/кодами владельца; shared — системные).
    for base_dir, author in project_bases(project):
        context = build_render_context(project, version, template_repo, author=author)
        if context is None:
            logger.warning("regenerate_dynamic_includes: cannot build context", project_id=str(project.id))
            return
        _render_includes_into_base(project, version, files_dir, context, base_dir)


def _render_includes_into_base(
    project: Project,
    version: TemplateVersion,
    files_dir: Path,
    context: dict[str, Any],
    base_dir: str,
) -> None:
    for inc in version.dynamic_includes:
        src = files_dir / inc.template
        if not src.exists():
            logger.warning("dynamic include source missing", template=inc.template, path=str(src))
            continue
        try:
            rendered = _render_text(src.read_text(encoding="utf-8"), context, src)
            dest = project.folder / prefix_path(base_dir, inc.output)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(rendered, encoding="utf-8")
            logger.debug("dynamic include regenerated", template=inc.template, output=inc.output, base=base_dir or ".")
        except Exception as exc:
            logger.warning("dynamic include render error", template=inc.template, exc=str(exc))


def nda_source_dir(template_repo: ITemplateRepository, version: TemplateVersion) -> Path | None:
    """Absolute path to the version's NDA file group, or None if not declared."""
    if version.nda is None:
        return None
    files_dir = version_files_dir(template_repo, version)
    if files_dir is None:
        return None
    return files_dir / version.nda.source_dir


def instantiate_nda(  # noqa: C901, PLR0912
    project: Project,
    version: TemplateVersion,
    template_repo: ITemplateRepository,
) -> None:
    """Materialise the NDA file group into the project when `meta.nda` is set.

    Per-author: the NDA расписка is a personal document — each author signs their
    own. In a team project one copy is materialised into every managed author's
    base (`project/<slug>/nda/…`, rendered with that author's ВКР topic); in a
    solo project a single copy lands at the root (`project/nda/…`).

    Toggling `meta.nda` is literally toggling this folder into the project (and
    later the submission package). Idempotent and non-destructive: only missing
    files are written, so a student's edits to an already-instantiated NDA file
    are never clobbered. A no-op when the version declares no NDA group or the
    project is not marked NDA.
    """
    src_dir = nda_source_dir(template_repo, version)
    if src_dir is None or not project.meta.get("nda"):
        return
    if not src_dir.exists():
        logger.warning("instantiate_nda: source dir missing", path=str(src_dir))
        return
    files_dir = version_files_dir(template_repo, version)
    if files_dir is None:
        # Недостижимо, пока src_dir найден (оба выводятся из _packs_dir), но
        # тип честный: без files_dir не вычислить rel-путь.
        return
    # Расписка NDA — персональный документ: каждый автор подписывает свою. В
    # команде материализуем по экземпляру в папке каждого ведомого автора (с его
    # темой ВКР через author-контекст); в solo — один экземпляр в корне проекта.
    for base_dir, author in nda_bases(project):
        context = build_render_context(project, version, template_repo, author=author)
        for src_file in src_dir.rglob("*"):
            if not src_file.is_file():
                continue
            rel = src_file.relative_to(files_dir)  # keep the nda/ prefix in the project
            dest = project.folder / prefix_path(base_dir, rel.as_posix())
            if dest.exists():
                continue  # never overwrite the student's copy
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                if _is_binary(src_file) or context is None:
                    shutil.copy2(src_file, dest)
                elif _should_render(src_file):
                    rendered = _render_text(src_file.read_text(encoding="utf-8"), context, src_file)
                    dest.write_text(rendered, encoding="utf-8")
                else:
                    shutil.copy2(src_file, dest)
                logger.debug("nda file instantiated", rel=str(rel), base=base_dir)
            except Exception as exc:
                logger.warning("nda file instantiate error", rel=str(rel), exc=str(exc))
