from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

import structlog

from hse_doc_studio.core.catalog import (
    DocumentDefinition,
    ExtraSubmissionItem,
    SubmissionDocItem,
    TemplateVersion,
)
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.services import ProjectTemplateService
from hse_doc_studio.core.team import author_by_slug
from hse_doc_studio.core.value_objects import SignaturesState
from hse_doc_studio.infra.office.convert_manager import CONVERTIBLE_OFFICE_EXTS, OfficeConvertManager
from hse_doc_studio.infra.signatures.pdf_stamper import PdfStamper, Stamp, format_sign_date

logger = structlog.get_logger()

_EXTERNAL_TIMEOUT_SEC = 120.0


@dataclass(frozen=True)
class ArchiveFormatSpec:
    id: str
    label: str
    ext: str
    # External CLIs that can produce this format (first found wins). Empty tuple
    # means the format is produced natively by shutil and is always available.
    tools: tuple[str, ...]


# zip/tar.gz are native (shutil); 7z/rar shell out to an external tool that may
# or may not be installed — availability is probed with shutil.which, the same
# way the system router detects external editors.
_ARCHIVE_FORMATS: tuple[ArchiveFormatSpec, ...] = (
    ArchiveFormatSpec(id="zip", label="ZIP", ext=".zip", tools=()),
    ArchiveFormatSpec(id="targz", label="TAR.GZ", ext=".tar.gz", tools=()),
    ArchiveFormatSpec(id="7z", label="7z", ext=".7z", tools=("7z", "7za")),
    ArchiveFormatSpec(id="rar", label="RAR", ext=".rar", tools=("rar",)),
)
_FORMAT_BY_ID: dict[str, ArchiveFormatSpec] = {spec.id: spec for spec in _ARCHIVE_FORMATS}


def _resolve_tool(spec: ArchiveFormatSpec) -> str | None:
    for tool in spec.tools:
        path = shutil.which(tool)
        if path is not None:
            return path
    return None


def _resolve_output_name(doc_def: DocumentDefinition, chosen_variant: str | None) -> dict[str, str]:
    """output_name для arcname: у вариантного дока — из ВЫБРАННОГО варианта.

    Fallback на первый вариант — как в resolve_document_source; пустой
    output_name варианта → def-level output_name (дальше локализация как
    раньше, с фолбэком на путь output_file).
    """
    if doc_def.variants:
        variant = next((v for v in doc_def.variants if v.id == chosen_variant), doc_def.variants[0])
        if variant.output_name:
            return variant.output_name
    return doc_def.output_name


def _with_owner_suffix(arcname: str, owner_name: str | None) -> str:
    """Личный док в team-пакете несёт фамилию владельца в имени файла."""
    if not owner_name:
        return arcname
    stem, ext = arcname.rsplit(".", 1) if "." in arcname else (arcname, "")
    return f"{stem} — {owner_name}.{ext}" if ext else f"{stem} — {owner_name}"


def is_archive_format_available(fmt: str) -> bool:
    spec = _FORMAT_BY_ID.get(fmt)
    if spec is None:
        return False
    if not spec.tools:
        return True  # native (shutil)
    return _resolve_tool(spec) is not None


def archive_ext(fmt: str) -> str:
    spec = _FORMAT_BY_ID.get(fmt)
    if spec is None:
        raise ValueError(f"Unknown archive format: {fmt!r}")
    return spec.ext


def available_archive_formats() -> list[dict[str, object]]:
    """Catalog for the API: id, label, ext, available. Drives the UI selector."""
    return [
        {"id": spec.id, "label": spec.label, "ext": spec.ext, "available": is_archive_format_available(spec.id)}
        for spec in _ARCHIVE_FORMATS
    ]


def _contained(base: Path, rel: str) -> Path | None:
    """Join ``rel`` under ``base``, refusing anything that escapes ``base``.

    ``rel`` comes (via SubmissionDocItem/ExtraSubmissionItem) from the template
    YAML *and* the raw HTTP override body, so a value like ``../../x`` or an
    absolute path must not be allowed to read or write outside the submission
    folder / project tree. resolve() collapses ``..`` and follows symlinks in
    the existing prefix, so symlink escapes are caught too. Returns the joined
    path when safe, else None.
    """
    candidate = base / rel
    try:
        resolved = candidate.resolve()
        base_resolved = base.resolve()
    except OSError:
        return None
    if not resolved.is_relative_to(base_resolved):
        return None
    return candidate


def _extra_arcname(output_name: str) -> str:
    """Имя файла extra-артефакта в пакете: расширение из output_name уважается.

    Профиль сам задаёт целевое расширение («Ссылка на код.txt», «Декларация
    ИИ.md»); `.md` дописывается только когда расширения нет вовсе — легаси-
    дефолт для form-рендеренных extras.
    """
    return output_name if PurePosixPath(output_name).suffix else output_name + ".md"


class SubmissionAssembler:
    """Builds the two submission deliverables from a project's compiled PDFs.

    1. ``populate_dir`` writes a human-browsable folder of signature-stamped
       PDFs (+ extras) — the artefact the user opens in an editor / file
       manager.
    2. ``create_archive`` packs that folder into the requested format.

    Source PDFs in the project tree are never mutated: stamping renders into
    the output folder, leaving the originals as latexmk produced them.
    """

    def __init__(
        self, pdf_stamper: PdfStamper | None = None, office_manager: OfficeConvertManager | None = None
    ) -> None:
        self._pdf_stamper = pdf_stamper or PdfStamper()
        self._office_manager = office_manager

    async def populate_dir(  # noqa: C901, PLR0912
        self,
        output_dir: Path,
        project_folder: Path,
        doc_items: list[SubmissionDocItem],
        extra_items: list[ExtraSubmissionItem],
        template_version: TemplateVersion,
        signatures_state: SignaturesState,
        lang: str = "ru",
        rendered_extras: dict[str, str] | None = None,
        project: Project | None = None,
        custom_doc_decisions: dict[str, bool] | None = None,
    ) -> list[str]:
        """Write stamped PDFs + extras into ``output_dir``; return arcnames written.

        ``rendered_extras`` maps an extra item's ``source`` to a ready-rendered
        text body (e.g. a form's output template rendered over its answers). When
        present for a ``format: markdown`` item, that body is written verbatim
        instead of dumping the raw JSON — this is how the AI declaration becomes
        the official ``Декларация ИИ.md`` rather than a key/value dump.

        ``project`` (когда передан) включает инстанс-резолв: item.doc_id — id
        ИНСТАНСА ("vkr--shalaev"), PDF ищется по пути базы владельца, а имя в
        пакете получает фамилию автора. Без проекта — легаси-режим (def id ==
        instance id, плоские пути) для обратной совместимости тестов.

        ``custom_doc_decisions`` (doc_id -> convert-to-PDF?) drives the
        convert/keep-as-is choice for a custom-file document with a
        convertible office format; falls back to the document's remembered
        ``custom_file.convert_to_pdf_at_package`` when absent.
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        written: list[str] = []

        for item in doc_items:
            resolved = await self._resolve_doc_target(
                item.doc_id, template_version, project, lang, project_folder, custom_doc_decisions
            )
            if resolved is None:
                continue
            output_file, arcname, is_pdf = resolved
            source_path = project_folder / output_file
            if not source_path.exists():
                logger.warning("assembler: compiled PDF not found", path=str(source_path), doc_id=item.doc_id)
                continue

            target = _contained(output_dir, arcname)
            if target is None:
                logger.warning("assembler: doc output_name escapes folder", doc_id=item.doc_id, arcname=arcname)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            # Never attempt to stamp a non-PDF file — that would crash trying
            # to parse it as a PDF. An unsignable custom document (docx/pptx
            # kept as-is, or an unrecognized format) is copied in unstamped
            # even if placements exist for it.
            stamps = (
                self._stamps_for_doc(
                    item_signatures=item.signatures,
                    doc_id=item.doc_id,
                    project_folder=project_folder,
                    signatures_state=signatures_state,
                )
                if is_pdf
                else []
            )
            try:
                if stamps:
                    self._pdf_stamper.stamp(source_path, target, stamps)
                else:
                    shutil.copyfile(source_path, target)
                written.append(arcname)
                logger.debug("assembler: added doc", source=str(source_path), arcname=arcname, stamps=len(stamps))
            except OSError as exc:
                logger.warning("assembler: error adding doc", source=str(source_path), exc=str(exc))

        for extra in extra_items:
            name = self._write_extra(output_dir, project_folder, extra, rendered_extras or {})
            if name is not None:
                written.append(name)

        return written

    async def _resolve_doc_target(  # noqa: C901
        self,
        item_doc_id: str,
        template_version: TemplateVersion,
        project: Project | None,
        lang: str,
        project_folder: Path,
        custom_doc_decisions: dict[str, bool] | None,
    ) -> tuple[str, str, bool] | None:
        """(output_file, arcname, is_pdf) для пункта пакета; None — пункт пропускается.

        С `project` item_doc_id — id ИНСТАНСА: PDF берётся из базы владельца,
        имя в пакете получает фамилию автора. Без проекта — легаси-режим
        (def id == instance id, плоские пути) для обратной совместимости.

        Кастомный файл (`doc.custom_file`) резолвится НЕЗАВИСИМО от шаблонных
        output_file/variants — см. `_resolve_custom_doc_target`/`_custom_doc_arcname`.
        """
        doc_def_map = {d.id: d for d in template_version.documents}
        owner_name: str | None = None
        chosen_variant: str | None = None
        if project is not None:
            doc = next((d for d in project.documents if d.id == item_doc_id), None)
            if doc is None:
                logger.warning("assembler: doc instance not found", doc_id=item_doc_id)
                return None
            owner = author_by_slug(project, doc.owner)
            if owner is not None:
                owner_name = owner.name.split()[0] if owner.name.split() else owner.slug
            if doc.custom_file is not None:
                custom = await self._resolve_custom_doc_target(doc, project_folder, custom_doc_decisions)
                if custom is None:
                    return None
                output_file, is_pdf = custom
                arcname = self._custom_doc_arcname(doc, doc_def_map.get(doc.def_id), lang, is_pdf)
                return output_file, _with_owner_suffix(arcname, owner_name), is_pdf
            doc_def = doc_def_map.get(doc.def_id)
            chosen_variant = doc.chosen_variant
            try:
                _, output_file = ProjectTemplateService().resolve_instance_source(project, doc, template_version)
            except ValueError:
                output_file = None
        else:
            doc_def = doc_def_map.get(item_doc_id)
            output_file = doc_def.output_file if doc_def is not None else None
        if doc_def is None or not output_file:
            logger.warning("assembler: doc_def/output_file not resolvable", doc_id=item_doc_id)
            return None
        output_name = _resolve_output_name(doc_def, chosen_variant)
        arcname = output_name.get(lang, output_name.get("ru", output_file))
        return output_file, _with_owner_suffix(arcname, owner_name), True

    @staticmethod
    def _custom_doc_arcname(doc: Document, doc_def: DocumentDefinition | None, lang: str, is_pdf: bool) -> str:
        """Имя в пакете для custom_file-документа, с правильным расширением.

        Берёт локализованное имя из пака, если оно есть (док остаётся
        узнаваемым по имени — «ТЗ.pdf» вместо оригинального имени загрузки),
        иначе падает на оригинальное имя загрузки; расширение подгоняется под
        фактический результат (`is_pdf` -> .pdf, иначе — реальный ext).
        """
        assert doc.custom_file is not None  # noqa: S101 — invariant enforced by caller
        output_name = _resolve_output_name(doc_def, doc.chosen_variant) if doc_def is not None else {}
        fallback_name = Path(doc.custom_file.original_filename).name
        arcname = output_name.get(lang, output_name.get("ru", fallback_name)) if output_name else fallback_name
        if is_pdf and not arcname.lower().endswith(".pdf"):
            return str(Path(arcname).with_suffix(".pdf"))
        if not is_pdf and not arcname.lower().endswith(doc.custom_file.ext):
            return str(Path(arcname).with_suffix(doc.custom_file.ext))
        return arcname

    @staticmethod
    def _custom_doc_decision(
        doc_id: str, convert_to_pdf_at_package: bool | None, decisions: dict[str, bool] | None
    ) -> bool | None:
        if decisions is not None and doc_id in decisions:
            return decisions[doc_id]
        return convert_to_pdf_at_package

    async def _get_or_convert_preview(self, project_folder: Path, stored_path: str) -> str | None:
        """Sibling PDF-превью конвертируемого custom_file; None — недоступно.

        Использует уже сгенерированный на аплоаде sibling, иначе пробует
        синхронный fallback через OfficeConvertManager (напр., превью не
        удалось сгенерировать при загрузке).
        """
        stored_abs = project_folder / stored_path
        preview_rel = str(Path(stored_path).with_suffix(".pdf"))
        preview_abs = project_folder / preview_rel
        if preview_abs.is_file():
            return preview_rel
        if self._office_manager is None or not stored_abs.is_file():
            return None
        pdf_bytes = await self._office_manager.convert_to_pdf(stored_abs)
        if pdf_bytes is None:
            return None
        try:
            preview_abs.write_bytes(pdf_bytes)
        except OSError as exc:
            logger.warning("assembler: custom doc preview write failed", path=str(preview_abs), exc=str(exc))
            return None
        return preview_rel

    async def _resolve_custom_doc_target(
        self,
        doc: Document,
        project_folder: Path,
        custom_doc_decisions: dict[str, bool] | None,
    ) -> tuple[str, bool] | None:
        """(output_file, is_pdf) для документа с custom_file; None — пропуск.

        already-PDF -> используем как есть. Конвертируемый формат И решение
        "конвертировать" (явное из `custom_doc_decisions`, иначе запомненное
        `convert_to_pdf_at_package`) -> sibling-превью-PDF (см.
        `_get_or_convert_preview`). Иначе — сырой файл под настоящим
        расширением, is_pdf=False.
        """
        custom_file = doc.custom_file
        if custom_file is None:
            return None
        if custom_file.ext == ".pdf":
            return custom_file.stored_path, True

        decision = self._custom_doc_decision(doc.id, custom_file.convert_to_pdf_at_package, custom_doc_decisions)
        if decision and custom_file.ext in CONVERTIBLE_OFFICE_EXTS:
            preview_rel = await self._get_or_convert_preview(project_folder, custom_file.stored_path)
            if preview_rel is not None:
                return preview_rel, True
            logger.warning("assembler: custom doc conversion unavailable, including raw file", doc_id=doc.id)
        return custom_file.stored_path, False

    def create_archive(self, src_dir: Path, dest_base: Path, fmt: str) -> Path:
        """Pack ``src_dir`` into ``dest_base + ext``. Returns the archive path.

        Raises ValueError for an unknown format or when the external tool for a
        7z/rar archive is not installed.
        """
        spec = _FORMAT_BY_ID.get(fmt)
        if spec is None:
            raise ValueError(f"Unknown archive format: {fmt!r}")

        dest_base.parent.mkdir(parents=True, exist_ok=True)

        if fmt == "zip":
            return Path(shutil.make_archive(str(dest_base), "zip", root_dir=str(src_dir)))
        if fmt == "targz":
            return Path(shutil.make_archive(str(dest_base), "gztar", root_dir=str(src_dir)))

        tool = _resolve_tool(spec)
        if tool is None:
            raise ValueError(
                f"Archive format {fmt!r} requires an external tool ({'/'.join(spec.tools)}) which is not installed"
            )
        dest = dest_base.with_name(dest_base.name + spec.ext)
        names = [p.name for p in sorted(src_dir.iterdir())]
        cmd = [tool, "a", str(dest), *names]
        result = subprocess.run(  # noqa: S603 — tool path comes from shutil.which, args are local filenames
            cmd,
            cwd=str(src_dir),
            capture_output=True,
            text=True,
            timeout=_EXTERNAL_TIMEOUT_SEC,
            check=False,
        )
        if result.returncode != 0 or not dest.exists():
            detail = result.stderr.strip() or result.stdout.strip() or f"exit {result.returncode}"
            raise ValueError(f"{fmt} archiving failed: {detail}")
        return dest

    def _stamps_for_doc(
        self,
        item_signatures: tuple[str, ...],
        doc_id: str,
        project_folder: Path,
        signatures_state: SignaturesState,
    ) -> list[Stamp]:
        # Only stamp slots the profile actually requested AND that have an
        # enabled placement + on-disk PNG. We don't second-guess the profile:
        # if the user enabled a slot in the UI but the profile didn't ask for
        # it on this doc, we skip it.
        doc_placements = signatures_state.placements.get(doc_id, {})
        result: list[Stamp] = []
        for slot_id in item_signatures:
            placement = doc_placements.get(slot_id)
            slot = signatures_state.slots.get(slot_id)
            if placement is None or not placement.enabled:
                continue
            if slot is None or slot.png_path is None:
                continue
            png_path = project_folder / slot.png_path
            if not png_path.exists():
                logger.warning(
                    "assembler: PNG missing for slot",
                    doc_id=doc_id,
                    slot_id=slot_id,
                    path=str(png_path),
                )
                continue
            aspect = 0.4
            if slot.natural_width_px and slot.natural_height_px and slot.natural_width_px > 0:
                aspect = slot.natural_height_px / slot.natural_width_px
            result.append(
                Stamp(
                    page=placement.page,
                    x_mm=placement.x_mm,
                    y_mm=placement.y_mm,
                    width_mm=placement.width_mm,
                    png_path=png_path,
                    aspect_ratio=aspect,
                    date_text=format_sign_date(placement.sign_date),
                )
            )
        return result

    def _write_extra(
        self,
        output_dir: Path,
        project_folder: Path,
        extra: ExtraSubmissionItem,
        rendered_extras: dict[str, str],
    ) -> str | None:
        # A pre-rendered body (e.g. the AI declaration form rendered through its
        # output template) wins over any on-disk source — it doesn't even need
        # the source file to exist.
        rendered = rendered_extras.get(extra.source)
        if rendered is not None:
            return self._write_text_extra(output_dir, extra, rendered)

        # Both source (read, inside the project) and output_name (write, inside
        # the submission folder) are kept inside their respective roots — see
        # _contained — so a crafted "../.." can neither exfiltrate nor overwrite
        # files outside the tree.
        source_path = _contained(project_folder, extra.source)
        if source_path is None:
            logger.warning("assembler: extra source escapes project", source=extra.source)
            return None
        if not source_path.exists():
            logger.warning("assembler: extra source not found", path=str(source_path))
            return None
        if extra.format == "markdown":
            return self._write_markdown_extra(output_dir, source_path, extra)
        return self._write_raw_extra(output_dir, source_path, extra)

    def _write_text_extra(self, output_dir: Path, extra: ExtraSubmissionItem, content: str) -> str | None:
        arcname = _extra_arcname(extra.output_name)
        target = _contained(output_dir, arcname)
        if target is None:
            logger.warning("assembler: extra output_name escapes folder", output_name=extra.output_name)
            return None
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        logger.debug("assembler: added rendered markdown extra", arcname=arcname)
        return arcname

    def _write_markdown_extra(self, output_dir: Path, source_path: Path, extra: ExtraSubmissionItem) -> str | None:
        try:
            data = json.loads(source_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("assembler: extra markdown read/parse error", path=str(source_path), exc=str(exc))
            return None
        arcname = _extra_arcname(extra.output_name)
        target = _contained(output_dir, arcname)
        if target is None:
            logger.warning("assembler: extra output_name escapes folder", output_name=extra.output_name)
            return None
        lines: list[str] = [f"# {extra.output_name}", ""]
        for key, value in data.items():
            lines.append(f"**{key}**: {value}")
            lines.append("")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(lines), encoding="utf-8")
        logger.debug("assembler: added markdown extra", arcname=arcname)
        return arcname

    def _write_raw_extra(self, output_dir: Path, source_path: Path, extra: ExtraSubmissionItem) -> str | None:
        target = _contained(output_dir, extra.output_name)
        if target is None:
            logger.warning("assembler: extra output_name escapes folder", output_name=extra.output_name)
            return None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source_path, target)
        except OSError as exc:
            logger.warning("assembler: error adding raw extra", source=str(source_path), exc=str(exc))
            return None
        else:
            logger.debug("assembler: added raw extra", source=str(source_path), arcname=extra.output_name)
            return extra.output_name
