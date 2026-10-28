from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from uuid import UUID

import structlog

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.catalog import ExtraSubmissionItem, SubmissionDocItem, TemplateVersion
from hse_doc_studio.core.entities import ChangeLogEntry, PackSubmissionRecord, Project
from hse_doc_studio.core.enums import ChangeLogKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.i18n import current_interface_language, localized_error
from hse_doc_studio.core.jobs.entities import JobSpec, job_tags
from hse_doc_studio.core.jobs.enums import JobKind, JobStatus
from hse_doc_studio.core.jobs.files import IProjectFileProbeFactory, ManifestFile
from hse_doc_studio.core.jobs.office import (
    OfficeConvertPayload,
    OfficeConvertReason,
    OfficeConvertResult,
    OfficeConvertStatus,
)
from hse_doc_studio.core.jobs.pack import PackResult
from hse_doc_studio.core.jobs.protocols import IJobDispatcher
from hse_doc_studio.core.office import ConvertRequest, custom_docs_to_convert
from hse_doc_studio.core.projects.locator import IProjectLocator
from hse_doc_studio.core.repositories import (
    IChangeLogRepository,
    IPackSubmissionRepository,
    IProjectRepository,
    ISignatureRepository,
    ITemplateRepository,
)
from hse_doc_studio.core.services import SubmissionProfileService
from hse_doc_studio.core.signatures.ports import IPublicKeyExporter
from hse_doc_studio.core.team import (
    author_by_slug,
    base_dir_for_owner,
    doc_instance_id,
    prefix_path,
    split_instance_id,
)
from hse_doc_studio.core.template_materializer import ITemplateMaterializer
from hse_doc_studio.use_cases.forms.render_form import RenderFormInput, RenderFormUC
from hse_doc_studio.use_cases.submission.pack_planner import PackPlanner

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


class CreateSubmissionUC:
    def __init__(
        self,
        project_repo: IProjectRepository,
        locator: IProjectLocator,
        template_repo: ITemplateRepository,
        submission_repo: IPackSubmissionRepository,
        submission_profile_service: SubmissionProfileService,
        signature_repo: ISignatureRepository,
        materializer: ITemplateMaterializer,
        planner: PackPlanner,
        key_exporter: IPublicKeyExporter,
        changelog_repo: IChangeLogRepository,
        render_form_uc: RenderFormUC,
        dispatcher: IJobDispatcher,
        file_probes: IProjectFileProbeFactory,
    ) -> None:
        self._project_repo = project_repo
        self._locator = locator
        self._template_repo = template_repo
        self._submission_repo = submission_repo
        self._submission_profile_service = submission_profile_service
        self._signature_repo = signature_repo
        self._materializer = materializer
        self._planner = planner
        self._key_exporter = key_exporter
        self._changelog_repo = changelog_repo
        self._render_form_uc = render_form_uc
        self._dispatcher = dispatcher
        self._file_probes = file_probes

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
        located = await self._locator.locate(inp.project_id)
        if located is None:
            raise NotFoundError(
                localized_error(f"Проект не найден: {inp.project_id}", f"Project not found: {inp.project_id}")
            )
        project_folder, project = located

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
            self._materializer.instantiate_nda(project, version)
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

        await self._convert_custom_docs(project, project_folder, doc_items, inp.custom_doc_decisions)
        # Все решения о составе пакета принимаются здесь, до записи на диск: ошибки
        # замороженных источников поднимаются раньше, чем появится папка пакета.
        plan = self._planner.build(
            project=project,
            version=version,
            sig_state=sig_state,
            doc_items=doc_items,
            extra_items=extra_items,
            lang=str(project.lang),
            rendered_extras=rendered_extras,
            decisions=inp.custom_doc_decisions,
            probe=self._file_probes.for_root(project_folder),
            key_exporter=self._key_exporter,
            base_name=base_name,
            profile_id=inp.profile_id,
            archive_format=inp.archive_format,
        )
        spec = JobSpec(
            id=submission_id,
            kind=JobKind.pack_submission,
            tags=job_tags(JobKind.pack_submission, plan.payload),
            project_id=project.id,
            actor=current_actor() or Actor.local(),
            locale=current_interface_language(),
            payload=plan.payload,
            local_root=project_folder,
        )
        job = await self._dispatcher.run(spec)
        job.raise_for_error()
        packed = job.data_as(PackResult)
        # Папку пакета запись хранит рядом с архивом: keep_folder в нагрузке всегда включен.
        assert packed.folder is not None  # noqa: S101
        output_path = project_folder / packed.archive.path
        output_dir = project_folder / packed.folder.path

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

    async def _convert_custom_docs(
        self,
        project: Project,
        project_folder: Path,
        doc_items: list[SubmissionDocItem],
        decisions: dict[str, bool] | None,
    ) -> None:
        """Шаг до сборки папки: готовит sibling-PDF custom-файлов, выбранных к конвертации.

        Сбой или недоступный конвертер не мешают пакету: ассемблер не найдет
        sibling и положит сырой файл с обычным предупреждением. Документы идут
        по одному, в порядке пунктов пакета: конвертер один на всех.
        """
        probe = self._file_probes.for_root(project_folder)
        for request in custom_docs_to_convert(project, doc_items, decisions, probe.is_file):
            await self._convert_custom_doc(project, project_folder, request)

    async def _convert_custom_doc(self, project: Project, project_folder: Path, request: ConvertRequest) -> None:
        try:
            # image=None: образ деплоя по умолчанию, как у конвертации при упаковке до диспетчера.
            payload = OfficeConvertPayload(
                source=ManifestFile(request.stored_path),
                output_path=request.output_path,
                image=None,
                reason=OfficeConvertReason.package,
            )
        except ValueError as exc:
            logger.warning("create_submission: custom doc conversion skipped", doc_id=request.doc_id, exc=str(exc))
            return
        spec = JobSpec(
            id=uuid.uuid4(),
            kind=JobKind.office_convert,
            tags=job_tags(JobKind.office_convert, payload),
            project_id=project.id,
            actor=current_actor() or Actor.local(),
            locale=current_interface_language(),
            payload=payload,
            local_root=project_folder,
        )
        job = await self._dispatcher.run(spec)
        if job.status is not JobStatus.succeeded:
            logger.warning(
                "create_submission: custom doc conversion failed",
                doc_id=request.doc_id,
                status=str(job.status),
                exc=job.error.detail if job.error is not None else str(job.status),
                error=job.error.code if job.error is not None else None,
            )
            return
        result = job.data_as(OfficeConvertResult)
        if result.status is not OfficeConvertStatus.ok and result.detail:
            logger.warning(
                "assembler: custom doc preview write failed",
                path=str(project_folder / request.output_path),
                exc=result.detail,
            )

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
