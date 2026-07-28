from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import UUID

import structlog

from hse_doc_studio.core.catalog import ExtraSubmissionItem, SubmissionDocItem, TemplateVersion
from hse_doc_studio.core.entities import ChangeLogEntry, PackSubmissionRecord, Project
from hse_doc_studio.core.enums import ChangeLogKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.repositories import (
    IChangeLogRepository,
    IPackSubmissionRepository,
    IProjectIndexRepository,
    IProjectRepository,
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import SubmissionProfileService
from hse_doc_studio.core.team import (
    author_by_slug,
    base_dir_for_owner,
    doc_instance_id,
    prefix_path,
    split_instance_id,
)
from hse_doc_studio.infra.project_init.template_renderer import instantiate_nda
from hse_doc_studio.infra.submission.assembler import SubmissionAssembler
from hse_doc_studio.use_cases.forms.render_form import RenderFormInput, RenderFormUC

logger = structlog.get_logger()


def _form_id_for_extra(extra: ExtraSubmissionItem, version: TemplateVersion) -> str | None:
    """If an extra item's source is a form's answers file, return that form id.

    Convention: form answers live at ``.hse-studio/forms/<form_id>.json``. When
    the extra points there and the form declares an output template, the
    declaration is rendered through that template rather than json-dumped.
    В team инстанс формы ("ai_declaration--slug") резолвится по базовому id.
    """
    if extra.format != "markdown":
        return None
    path = PurePosixPath(extra.source.replace("\\", "/"))
    if path.parent.name != "forms" or path.suffix != ".json":
        return None
    form_id = path.stem
    base_id, _owner = split_instance_id(form_id)
    form = version.get_form(base_id)
    if form is None or form.output is None:
        return None
    return form_id


@dataclass
class CreateSubmissionInput:
    project_id: UUID
    profile_id: str
    items: list[SubmissionDocItem]
    extra_items: list[ExtraSubmissionItem]
    archive_format: str = "zip"
    # Team mode: чей пакет формируем — личные доки этого автора + общие.
    # Обязателен для командных проектов; в solo игнорируется.
    author_slug: str | None = None
    # doc_id (инстанс) -> конвертировать в PDF при упаковке? Только для доков
    # с custom_file конвертируемого формата; см. PreviewSubmissionCustomDocsUC.
    custom_doc_decisions: dict[str, bool] | None = None


@dataclass
class CreateSubmissionOutput:
    submission: PackSubmissionRecord


def _resolve_project(
    project_id: UUID,
    project_repo: IProjectRepository,
    project_index_repo: IProjectIndexRepository,
) -> tuple[Path, Project] | tuple[None, None]:
    known_folders = project_index_repo.list_known()
    for folder in known_folders:
        try:
            project = project_repo.get(folder)
            if project is not None and project.id == project_id:
                return folder, project
        except Exception as exc:
            logger.warning(
                "create_submission: error loading project",
                folder=str(folder),
                exc=str(exc),
            )
    return None, None


class CreateSubmissionUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        project_index_repo: IProjectIndexRepository,
        template_repo: ITemplateRepository,
        submission_repo: IPackSubmissionRepository,
        submission_profile_service: SubmissionProfileService,
        signature_repo: ISignatureRepository,
        assembler: SubmissionAssembler,
        changelog_repo: IChangeLogRepository,
        render_form_uc: RenderFormUC,
    ) -> None:
        self._project_repo = project_repo
        self._project_index_repo = project_index_repo
        self._template_repo = template_repo
        self._submission_repo = submission_repo
        self._submission_profile_service = submission_profile_service
        self._signature_repo = signature_repo
        self._assembler = assembler
        self._changelog_repo = changelog_repo
        self._render_form_uc = render_form_uc

    @staticmethod
    def _reroute_form_extra(
        extra: ExtraSubmissionItem,
        version: TemplateVersion,
        author_slug: str,
    ) -> ExtraSubmissionItem:
        """Extra, указывающий на ответы per-author формы, → инстанс автора.

        `.hse-studio/forms/ai_declaration.json` → `…/ai_declaration--slug.json`.
        Прочие extras (статические файлы, не-per_author формы) — без изменений.
        """
        path = PurePosixPath(extra.source.replace("\\", "/"))
        if path.parent.name != "forms" or path.suffix != ".json":
            return extra
        base_id, owner = split_instance_id(path.stem)
        form = version.get_form(base_id)
        if form is None or not form.per_author or owner is not None:
            return extra
        instance = doc_instance_id(base_id, author_slug)
        return ExtraSubmissionItem(
            source=str(path.with_name(f"{instance}.json")),
            output_name=extra.output_name,
            format=extra.format,
        )

    async def execute(self, inp: CreateSubmissionInput) -> CreateSubmissionOutput:  # noqa: C901, PLR0915
        project_folder, project = _resolve_project(inp.project_id, self._project_repo, self._project_index_repo)
        if project is None or project_folder is None:
            raise NotFoundError(
                localized_error(f"Проект не найден: {inp.project_id}", f"Project not found: {inp.project_id}")
            )

        version = self._template_repo.get_version(
            project.lock.pack_id,
            project.lock.template_id,
            project.lock.version,
        )
        if version is None:
            version_ref = f"{project.lock.pack_id}/{project.lock.template_id}/{project.lock.version}"
            raise NotFoundError(
                localized_error(
                    f"Версия шаблона не найдена: {version_ref}", f"Template version not found: {version_ref}"
                )
            )

        sig_state = self._signature_repo.get_state(project_folder)

        profile = self._submission_profile_service.get_profile(version, inp.profile_id)
        if profile is None:
            raise NotFoundError(
                localized_error(
                    f"Профиль сдачи {inp.profile_id!r} не найден", f"Submission profile {inp.profile_id!r} not found"
                )
            )

        team = str(project.staffing) == "team"
        author = author_by_slug(project, inp.author_slug) if team else None
        if team and author is None:
            raise ValueError(
                localized_error(
                    "Командный проект: укажите существующего автора (author_slug) для пакета сдачи",
                    "Team project: specify an existing author (author_slug) for the submission package",
                )
            )

        validated_items = self._submission_profile_service.build_item_list(
            profile=profile,
            project=project,
            version=version,
            sig_state=sig_state,
            author_slug=inp.author_slug if team else None,
        )

        doc_items = validated_items if validated_items else inp.items
        extra_items = list(profile.extra_items) if profile.extra_items else list(inp.extra_items)
        # Extras гейтятся по виду проекта (supported_kinds), как пункты-доки по
        # kind документов: «Ссылка на код.txt» на КТ2 — только research.
        extra_items = [e for e in extra_items if str(project.kind) in e.supported_kinds]

        # Team: формы с per_author живут в инстансах "{form}--{slug}" — extra,
        # указывающий на файл ответов формы, переадресуется на инстанс автора.
        if team and author is not None and author.slug:
            extra_items = [self._reroute_form_extra(extra, version, author.slug) for extra in extra_items]

        # NDA file group: when the project is marked NDA, materialise the pack's
        # NDA files into the project (idempotent) and append each to the package
        # under the configured submission_dir. Toggling meta.nda off simply
        # leaves them out of the package.
        if version.nda is not None and project.meta.get("nda"):
            instantiate_nda(project, version, self._template_repo)
            # Расписка NDA — персональная: в команде берём её из папки автора
            # пакета (project/<slug>/nda/), в solo — из корня (project/nda/).
            nda_base = base_dir_for_owner(project, author.slug) if team and author is not None else ""
            nda_dir = project_folder / prefix_path(nda_base, version.nda.source_dir)
            if nda_dir.exists():
                for nda_file in sorted(p for p in nda_dir.rglob("*") if p.is_file()):
                    rel = nda_file.relative_to(nda_dir).as_posix()
                    extra_items.append(
                        ExtraSubmissionItem(
                            source=prefix_path(nda_base, f"{version.nda.source_dir}/{rel}"),
                            output_name=f"{version.nda.submission_dir}/{rel}",
                            format=None,
                        )
                    )

        # Pre-render any form-backed markdown extras (e.g. the AI declaration)
        # through their output template so the package gets the official
        # document, not a raw json dump. Failures degrade gracefully.
        rendered_extras: dict[str, str] = {}
        for extra in extra_items:
            form_id = _form_id_for_extra(extra, version)
            if form_id is None:
                continue
            try:
                rendered = await self._render_form_uc.execute(
                    RenderFormInput(project_id=inp.project_id, form_id=form_id)
                )
                rendered_extras[extra.source] = rendered.content
            except (ValueError, NotFoundError) as exc:
                logger.warning("create_submission: form render skipped", form_id=form_id, exc=str(exc))

        now = datetime.now(tz=timezone.utc)
        timestamp = now.strftime("%Y%m%dT%H%M%S")
        # The submission id is minted up front and a short slug of it goes into
        # the folder/archive name. The timestamp alone is only second-granular,
        # so two same-profile packs in the same second would otherwise reuse the
        # same folder and silently overwrite each other's PDFs + archive.
        submission_id = uuid.uuid4()
        owner_part = f"-{author.slug}" if author is not None and author.slug else ""
        base_name = f"{inp.profile_id}{owner_part}-{timestamp}-{submission_id.hex[:8]}"
        submissions_dir = project_folder / "submissions"
        # Two deliverables: a browsable folder of PDFs + an archive of it. The
        # folder keeps its extensionless name; the archive gets the format ext,
        # so they never collide (e.g. final-…/ and final-….zip).
        output_dir = submissions_dir / base_name

        await self._assembler.populate_dir(
            output_dir=output_dir,
            project_folder=project_folder,
            doc_items=doc_items,
            extra_items=extra_items,
            template_version=version,
            signatures_state=sig_state,
            lang=str(project.lang),
            rendered_extras=rendered_extras,
            project=project,
            custom_doc_decisions=inp.custom_doc_decisions,
        )
        output_path = self._assembler.create_archive(output_dir, submissions_dir / base_name, inp.archive_format)

        if inp.custom_doc_decisions:
            self._remember_custom_doc_decisions(project_folder, inp.custom_doc_decisions)

        record = PackSubmissionRecord(
            id=submission_id,
            project_folder=project_folder,
            profile_id=inp.profile_id,
            created_at=now,
            doc_items=doc_items,
            extra_items=extra_items,
            output_path=output_path,
            output_dir=output_dir,
            archive_format=inp.archive_format,
        )
        self._submission_repo.save(record)

        entry = ChangeLogEntry(
            id=uuid.uuid4(),
            at=now,
            kind=ChangeLogKind.pack_submission,
            doc_id=None,
            summary=f"Pack submission created: profile={inp.profile_id}, archive={output_path.name}",
            note=None,
        )
        self._changelog_repo.append(project_folder, entry)

        logger.debug(
            "create_submission: done",
            submission_id=str(record.id),
            output=str(output_path),
        )

        return CreateSubmissionOutput(submission=record)

    def _remember_custom_doc_decisions(self, project_folder: Path, decisions: dict[str, bool]) -> None:
        """Best-effort: persist the accepted convert choices as each document's
        new default, so the next package build doesn't need to ask again."""
        try:
            project = self._project_repo.get(project_folder)
            if project is None:
                return
            changed = False
            for i, doc in enumerate(project.documents):
                if doc.id not in decisions or doc.custom_file is None:
                    continue
                decision = decisions[doc.id]
                if doc.custom_file.convert_to_pdf_at_package == decision:
                    continue
                project.documents[i] = replace(
                    doc, custom_file=replace(doc.custom_file, convert_to_pdf_at_package=decision)
                )
                changed = True
            if changed:
                self._project_repo.save(project)
        except Exception as exc:  # noqa: BLE001 — remembering the default must never fail packaging
            logger.warning("create_submission: failed to remember custom doc decisions", exc=str(exc))
