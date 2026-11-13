"""Планировщик пакета сдачи: все решения на стороне API, на выходе нагрузка задачи pack.submission.

Решает, какие документы и дополнения попадут в пакет, под какими именами,
с какими штампами, замороженными копиями, подписями, ключами и README. Диска
планировщик не касается (только через `IProjectFileProbe`), файлы не пишет и
не конвертирует: готовый соседний PDF custom-файла он берет, а если его нет,
кладет исходный файл как есть.

Документ берется из источника подписи (docs/design/signing-route.md, 12.4 и 12.8):
версии на подписи, если маршрут ее снял, иначе текущей сборки. Рабочая сборка,
ушедшая вперед версии на подписи, это предупреждение `changed_after_sent` без
пропуска: в пакет все равно едет версия на подписи.

Подпись, пропущенная маршрутом на этой точке, и необязательная неподписанная
готовности не блокируют (signing-route.md, 13.11): КАК_ПРОВЕРИТЬ.txt называет их,
а вторая еще и дает предупреждение `optional_unsigned`.
"""

from __future__ import annotations

import json
import posixpath
from dataclasses import dataclass, field, replace
from pathlib import Path, PurePosixPath
from typing import Literal

import structlog

from hse_doc_studio.core.catalog import (
    DocumentDefinition,
    ExtraSubmissionItem,
    SubmissionDocItem,
    TemplateVersion,
)
from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.jobs.files import (
    InlineBlob,
    IProjectFileProbe,
    ManifestFile,
    StampSpec,
    validate_relative_posix,
)
from hse_doc_studio.core.jobs.pack import (
    ArchiveFormat,
    PackEntry,
    PackEntryKind,
    PackSkip,
    PackSubmissionPayload,
)
from hse_doc_studio.core.office import CONVERTIBLE_OFFICE_EXTS, resolve_custom_doc_decision, sibling_pdf_path
from hse_doc_studio.core.services import ProjectTemplateService, SignatureSlotService
from hse_doc_studio.core.signatures.dates import display_day, format_moment, format_numeric
from hse_doc_studio.core.signatures.package_text import (
    BASE_SUFFIX,
    CRYPTO_GUIDE_KINDS,
    VERIFY_GUIDE_NAME,
    GuideDocument,
    GuideSignature,
    PackageSignature,
    build_verify_guide,
    detached_signature_name,
    public_key_files,
    signer_display_name,
    version_date,
)
from hse_doc_studio.core.signatures.plan import SignMethod, method_of, signer_for
from hse_doc_studio.core.signatures.ports import IPublicKeyExporter
from hse_doc_studio.core.signatures.stamps import Stamp, stamps_digest_matches, stamps_for_doc
from hse_doc_studio.core.submission_errors import (
    archive_format_unknown,
    frozen_missing,
    marks_changed,
    rebuilt_after_freeze,
    signature_missing,
    signed_pdf_changed,
    version_not_frozen,
)
from hse_doc_studio.core.team import author_by_slug
from hse_doc_studio.core.value_objects import (
    DetachedSignature,
    EmbeddedSignature,
    FrozenPdf,
    PinnedPdf,
    SignaturesState,
)
from hse_doc_studio.use_cases.signatures.signing_source import pinned_file_rel

logger = structlog.get_logger()

# Причины в PackSkip, которые ставит планировщик.
REASON_DOC_NOT_FOUND = "doc_not_found"
REASON_DOC_NOT_RESOLVABLE = "doc_not_resolvable"
REASON_SOURCE_MISSING = "source_missing"
REASON_ARCNAME_ESCAPES = "arcname_escapes"
REASON_EXTRA_SOURCE_ESCAPES = "extra_source_escapes"
REASON_EXTRA_SOURCE_MISSING = "extra_source_missing"
REASON_EXTRA_UNREADABLE = "extra_unreadable"

# Коды PackNotice: файл в пакете есть, но автору стоит о нем знать.
NoticeCode = Literal["changed_after_sent", "optional_unsigned"]
NOTICE_CHANGED_AFTER_SENT: NoticeCode = "changed_after_sent"
NOTICE_OPTIONAL_UNSIGNED: NoticeCode = "optional_unsigned"


@dataclass(frozen=True)
class PackNotice:
    """Предупреждение без пропуска: документ в пакете, но автору стоит о нем знать.

    `changed_after_sent` (signing-route.md, 12.8): рабочая сборка разошлась с версией на подписи, в пакет попала
    версия на подписи. Поля версии те же, что у `pinned` в плане подписей; `source_sha256` хэш файла версии, по
    которому собран пакет, `working_sha256` хэш рабочей сборки.
    `optional_unsigned` (13.11): необязательная на точке подпись `slot_id` не поставлена; полей версии у него нет.
    """

    code: NoticeCode
    doc_id: str
    arcname: str
    message: str
    pinned_at: str = ""
    route_id: str = ""
    round: int = 0
    source_sha256: str = ""
    working_sha256: str = ""
    slot_id: str = ""


@dataclass(frozen=True)
class PackPlan:
    payload: PackSubmissionPayload
    # Пропущенные пункты, в порядке обхода; то же самое пишется в лог.
    warnings: tuple[PackSkip, ...] = ()
    # Предупреждения без пропуска, в порядке документов.
    notices: tuple[PackNotice, ...] = ()


def _resolve_output_name(doc_def: DocumentDefinition, chosen_variant: str | None) -> dict[str, str]:
    """output_name для arcname: у вариантного дока из ВЫБРАННОГО варианта, иначе с def-уровня."""
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


def _extra_arcname(output_name: str) -> str:
    """Имя extra-артефакта: расширение из output_name уважается, `.md` дописывается только без него."""
    return output_name if PurePosixPath(output_name).suffix else output_name + ".md"


def _custom_doc_arcname(doc: Document, doc_def: DocumentDefinition | None, lang: str, is_pdf: bool) -> str:
    """Имя в пакете для custom_file-документа, с расширением по фактическому результату."""
    assert doc.custom_file is not None  # noqa: S101 — invariant enforced by caller
    output_name = _resolve_output_name(doc_def, doc.chosen_variant) if doc_def is not None else {}
    fallback_name = Path(doc.custom_file.original_filename).name
    arcname = output_name.get(lang, output_name.get("ru", fallback_name)) if output_name else fallback_name
    if is_pdf and not arcname.lower().endswith(".pdf"):
        return str(Path(arcname).with_suffix(".pdf"))
    if not is_pdf and not arcname.lower().endswith(doc.custom_file.ext):
        return str(Path(arcname).with_suffix(doc.custom_file.ext))
    return arcname


def _contained(rel: str) -> str | None:
    """Путь внутри корня (архива или проекта) в нормальной форме; None, если он выходит наружу.

    Лексическая проверка: `a/../b` сворачивается в `b`, `../x`, абсолютные пути
    и обратные слеши отвергаются. Символьные ссылки проверяет сам probe (цель за пределами проекта для него не файл).
    """
    norm = posixpath.normpath(rel)
    if norm == ".":
        return None
    try:
        validate_relative_posix(norm)
    except ValueError:
        return None
    return norm


def _method(state: SignaturesState, slot_id: str) -> SignMethod:
    slot = state.slots.get(slot_id)
    return method_of(slot.sign_mode) if slot is not None else SignMethod.image


def _detached_for_item(
    item_signatures: tuple[str, ...], doc_id: str, state: SignaturesState
) -> list[tuple[str, DetachedSignature]]:
    attached = state.detached.get(doc_id, {})
    return [
        (slot_id, attached[slot_id])
        for slot_id in item_signatures
        if slot_id in attached and _method(state, slot_id) is SignMethod.detached
    ]


def _embedded_for_item(
    item_signatures: tuple[str, ...], doc_id: str, state: SignaturesState
) -> list[tuple[str, EmbeddedSignature]]:
    embedded = state.embedded.get(doc_id, {})
    return [
        (slot_id, embedded[slot_id])
        for slot_id in item_signatures
        if slot_id in embedded and _method(state, slot_id) is SignMethod.pades
    ]


def _signing_time(signed_at: str | None) -> str:
    """Время самой ЭП для КАК_ПРОВЕРИТЬ.txt (signing-route.md, 14.8): «14.11.2026 10:05» по Москве, если оно есть."""
    return (format_moment(signed_at) or "") if signed_at else ""


def _stamp_spec(stamp: Stamp) -> StampSpec:
    return StampSpec(
        page=stamp.page,
        x_mm=stamp.x_mm,
        y_mm=stamp.y_mm,
        width_mm=stamp.width_mm,
        png=ManifestFile(stamp.png_path.as_posix()) if stamp.png_path is not None else None,
        aspect_ratio=stamp.aspect_ratio,
        text=stamp.text,
        details=stamp.details,
        subtitle=stamp.subtitle,
        date_label=stamp.date_label,
        date_text=stamp.date_text,
        height_mm=stamp.height_mm,
        align=stamp.align,
    )


@dataclass(frozen=True)
class _Version:
    """Версия на подписи, из которой собран документ пакета: дата для текстов и sha256 файла версии."""

    date: str
    sha256: str


def _with_version(doc: GuideDocument, version: _Version | None) -> GuideDocument:
    """Раздел КАК_ПРОВЕРИТЬ.txt со строкой версии на подписи, если документ собран из нее."""
    return replace(doc, version_date=version.date, version_sha256=version.sha256) if version is not None else doc


@dataclass
class _Run:
    """Состояние одного вызова build: входы и накопленные записи и предупреждения."""

    project: Project
    version: TemplateVersion
    sig_state: SignaturesState
    lang: str
    rendered_extras: dict[str, str]
    decisions: dict[str, bool] | None
    probe: IProjectFileProbe
    key_exporter: IPublicKeyExporter | None
    template_service: ProjectTemplateService
    slot_service: SignatureSlotService
    profile_id: str = ""
    entries: list[PackEntry] = field(default_factory=list)
    warnings: list[PackSkip] = field(default_factory=list)
    notices: list[PackNotice] = field(default_factory=list)
    # Разделы КАК_ПРОВЕРИТЬ.txt по документам с подписями (docs/design/signature-plan.md, раздел 8).
    guide: list[GuideDocument] = field(default_factory=list)

    def warn(self, event: str, name: str, reason: str, detail: str = "", **log: str) -> None:
        logger.warning(f"assembler: {event}", **log)
        self.warnings.append(PackSkip(arcname=name, reason=reason, detail=detail))

    def add_doc(self, item: SubmissionDocItem) -> None:  # noqa: C901
        resolved = self._resolve_doc_target(item.doc_id)
        if resolved is None:
            return
        output_file, arcname, is_pdf = resolved
        pinned = self.sig_state.pinned.get(item.doc_id)
        working_rel = _contained(output_file) if is_pdf else None
        if pinned is not None:
            # Версия на подписи всегда PDF: документ едет ею, даже если рабочий файл другого формата.
            if not is_pdf:
                arcname, is_pdf = str(PurePosixPath(arcname).with_suffix(".pdf")), True
            pinned_rel = pinned_file_rel(pinned)
            source_rel = _contained(pinned_rel) if pinned_rel is not None else None
            missing = pinned.path
        else:
            source_rel = _contained(output_file)
            missing = output_file
        if source_rel is None or not self.probe.is_file(source_rel):
            self.warn(
                "compiled PDF not found" if pinned is None else "PDF sent for signing not found",
                arcname,
                REASON_SOURCE_MISSING,
                missing,
                path=missing,
                doc_id=item.doc_id,
            )
            return

        target = _contained(arcname)
        if target is None:
            self.warn(
                "doc output_name escapes folder", arcname, REASON_ARCNAME_ESCAPES, doc_id=item.doc_id, arcname=arcname
            )
            return
        version = self._pinned_version(item.doc_id, target, source_rel, working_rel, pinned) if pinned else None
        self._optional_notices(item, target)
        # Документ с криптоподписями едет зафиксированными байтами, которые подписи и покрывают:
        # итоговый файл со встроенными PAdES и отдельный файл на каждую открепленную подпись.
        detached = _detached_for_item(item.signatures, item.doc_id, self.sig_state) if is_pdf else []
        embedded = _embedded_for_item(item.signatures, item.doc_id, self.sig_state) if is_pdf else []
        frozen = self.sig_state.frozen.get(item.doc_id)
        if (detached or embedded) and frozen is not None:
            self._add_frozen_doc(item, source_rel, target, frozen, detached, embedded, version)
            return
        # Не-PDF (docx/pptx как есть, неопознанный формат) не штампуем даже при
        # размещениях: парсер PDF на нем упал бы.
        stamps = self._stamps(item) if is_pdf else []
        if stamps:
            specs = tuple(_stamp_spec(s) for s in stamps)
            self.entries.append(
                PackEntry(PackEntryKind.stamp_pdf, target, source=ManifestFile(source_rel), stamps=specs)
            )
            sigs = (*self._image_signatures(item), *self._unsigned_signatures(item))
            if sigs:
                self.guide.append(_with_version(GuideDocument(pdf=target, sha256="", signatures=sigs), version))
        else:
            self.entries.append(PackEntry(PackEntryKind.copy, target, source=ManifestFile(source_rel)))

    def _pinned_version(
        self, doc_id: str, arcname: str, source_rel: str, working_rel: str | None, pinned: PinnedPdf
    ) -> _Version:
        """Версия на подписи документа для КАК_ПРОВЕРИТЬ.txt и предупреждение, если рабочая сборка ушла вперед.

        Хэш версии считается по файлу, а не берется из записи, как у источника подписи (`source_and_working`).
        Несобранная рабочая сборка расхождением не считается: показывать нечего.
        """
        source_sha = self.probe.sha256(source_rel)
        working_sha = (
            self.probe.sha256(working_rel) if working_rel is not None and self.probe.is_file(working_rel) else None
        )
        version = _Version(date=version_date(pinned.pinned_at), sha256=source_sha)
        if working_sha is not None and working_sha != source_sha:
            name = PurePosixPath(arcname).stem
            logger.info("assembler: document changed after it was sent for signing", doc_id=doc_id)
            self.notices.append(
                PackNotice(
                    code=NOTICE_CHANGED_AFTER_SENT,
                    doc_id=doc_id,
                    arcname=arcname,
                    message=localized_error(
                        f"Документ «{name}» изменён после отправки на подпись: в пакет попала версия на подписи "
                        f"от {version.date}",
                        f"The document «{name}» changed after it was sent for signing: the package holds the "
                        f"version sent for signing on {version.date}",
                    ),
                    pinned_at=pinned.pinned_at,
                    route_id=pinned.route_id,
                    round=pinned.round,
                    source_sha256=source_sha,
                    working_sha256=working_sha,
                )
            )
        return version

    def _stamps(self, item: SubmissionDocItem) -> list[Stamp]:
        # Только слоты, которые просил профиль, с включенным размещением и PNG на
        # месте (или печатной подписью «открепленная»): профиль не пересматриваем.
        return stamps_for_doc(
            self.sig_state,
            item.doc_id,
            Path(),
            self.lang,
            item.signatures,
            png_exists=self._png_exists,
        )

    def _png_exists(self, path: Path) -> bool:
        rel = _contained(path.as_posix())
        return rel is not None and self.probe.is_file(rel)

    def _resolve_doc_target(self, item_doc_id: str) -> tuple[str, str, bool] | None:  # noqa: C901
        """(output_file, arcname, is_pdf) для пункта пакета; None: пункт пропускается.

        item_doc_id это id ИНСТАНСА: PDF берется из базы владельца, имя в пакете
        получает фамилию автора. Кастомный файл (`doc.custom_file`) резолвится
        независимо от шаблонных output_file и variants.
        """
        project = self.project
        doc_def_map = {d.id: d for d in self.version.documents}
        owner_name: str | None = None
        doc = next((d for d in project.documents if d.id == item_doc_id), None)
        if doc is None:
            self.warn("doc instance not found", item_doc_id, REASON_DOC_NOT_FOUND, doc_id=item_doc_id)
            return None
        owner = author_by_slug(project, doc.owner)
        if owner is not None:
            owner_name = owner.name.split()[0] if owner.name.split() else owner.slug
        if doc.custom_file is not None:
            custom = self._resolve_custom_doc_target(doc)
            output_file, is_pdf = custom
            arcname = _custom_doc_arcname(doc, doc_def_map.get(doc.def_id), self.lang, is_pdf)
            return output_file, _with_owner_suffix(arcname, owner_name), is_pdf
        doc_def = doc_def_map.get(doc.def_id)
        try:
            _, output_file = self.template_service.resolve_instance_source(project, doc, self.version)
        except ValueError:
            output_file = None
        if doc_def is None or not output_file:
            self.warn("doc_def/output_file not resolvable", item_doc_id, REASON_DOC_NOT_RESOLVABLE, doc_id=item_doc_id)
            return None
        output_name = _resolve_output_name(doc_def, doc.chosen_variant)
        arcname = output_name.get(self.lang, output_name.get("ru", output_file))
        return output_file, _with_owner_suffix(arcname, owner_name), True

    def _resolve_custom_doc_target(self, doc: Document) -> tuple[str, bool]:
        """(output_file, is_pdf) для документа с custom_file.

        Готовый PDF берется как есть. Конвертируемый формат и решение
        «конвертировать» (явное, иначе запомненное) дают соседний PDF, если он
        уже есть: конвертацию делает шаг до планирования. Иначе сырой файл под
        настоящим расширением, is_pdf=False.
        """
        custom_file = doc.custom_file
        assert custom_file is not None  # noqa: S101 — invariant enforced by caller
        if custom_file.ext == ".pdf":
            return custom_file.stored_path, True
        decision = resolve_custom_doc_decision(doc.id, custom_file.convert_to_pdf_at_package, self.decisions)
        if decision and custom_file.ext in CONVERTIBLE_OFFICE_EXTS:
            preview_rel = sibling_pdf_path(custom_file.stored_path)
            if self.probe.is_file(preview_rel):
                return preview_rel, True
            logger.warning("assembler: custom doc conversion unavailable, including raw file", doc_id=doc.id)
        return custom_file.stored_path, False

    def _slot_label(self, slot_id: str) -> str:
        rslot = self.slot_service.find_runtime_slot(self.project, self.version, slot_id)
        return (rslot.label.get(self.lang) or rslot.label.get("ru") or slot_id) if rslot else slot_id

    def _image_signatures(self, item: SubmissionDocItem) -> tuple[GuideSignature, ...]:
        return tuple(
            GuideSignature(
                "image",
                self._slot_label(slot_id),
                signer_for(self.project, slot_id).name,
                page_date=self._page_date(item.doc_id, slot_id),
            )
            for slot_id in item.signatures
            if _method(self.sig_state, slot_id) is SignMethod.image
        )

    def _page_date(self, doc_id: str, slot_id: str) -> str:
        """«13.11.2026»: день подписи слота по Москве, если у слота есть метки даты и они видны (14.8); иначе пусто."""
        state = self.sig_state
        placement = state.placements.get(doc_id, {}).get(slot_id)
        if placement is None or not placement.dates or placement.signed_at is None:
            return ""
        if state.mark_hidden(doc_id, slot_id):
            return ""
        day = display_day(placement.signed_at.at)
        return format_numeric(day) if day is not None else ""

    def _unsigned_signatures(self, item: SubmissionDocItem) -> tuple[GuideSignature, ...]:
        """Строки инструкции без подписи (13.11): пропущенные маршрутом на этой точке, в том числе слоты сверх точки
        (в пункте профиля их нет, а метка с `keep_mark` стоит на странице), и необязательные неподписанные."""
        skipped = sorted(
            (slot_id, skip)
            for slot_id, skip in self.sig_state.skipped.get(item.doc_id, {}).items()
            if skip.profile_id == self.profile_id
        )
        return (
            *(
                GuideSignature("skipped", self._slot_label(slot_id), "", kept_mark=skip.keep_mark)
                for slot_id, skip in skipped
            ),
            *(GuideSignature("optional_unsigned", self._slot_label(slot_id), "") for slot_id in item.optional_unsigned),
        )

    def _optional_notices(self, item: SubmissionDocItem, arcname: str) -> None:
        """Предупреждение `optional_unsigned` на каждую необязательную неподписанную подпись документа (13.11)."""
        name = PurePosixPath(arcname).stem
        for slot_id in item.optional_unsigned:
            label = self._slot_label(slot_id)
            self.notices.append(
                PackNotice(
                    code=NOTICE_OPTIONAL_UNSIGNED,
                    doc_id=item.doc_id,
                    arcname=arcname,
                    message=localized_error(
                        f"Необязательная подпись «{label}» в «{name}» не поставлена",
                        f"The optional signature «{label}» on «{name}» is not signed",
                    ),
                    slot_id=slot_id,
                )
            )

    def _check_frozen_current(
        self, doc_id: str, source_rel: str, arcname: str, frozen: FrozenPdf, *, pinned: bool
    ) -> str:
        """Путь зафиксированного PDF; `PackError`, если источник подписи или видимый слой изменились после фиксации.

        Источник это версия на подписи, если она есть: пересборка рабочей сборки фиксацию не старит (12.8).
        Фиксация другой версии (например, ручная до отправки на подпись) к версии на подписи не относится: ее
        заменит фиксация маршрута, поэтому отказ говорит про маршрут, а не про ручную фиксацию (12.8.1).
        """
        name = PurePosixPath(arcname).stem
        if self.probe.sha256(source_rel) != frozen.source_sha256:
            if pinned:
                raise version_not_frozen(doc_id, name)
            raise rebuilt_after_freeze(doc_id, name)
        frozen_rel = _contained(frozen.path)
        if frozen_rel is None or not self.probe.is_file(frozen_rel):
            raise frozen_missing(doc_id, name)
        folder = self.project.folder

        def png_exists(path: Path) -> bool:
            return path.is_relative_to(folder) and self._png_exists(path.relative_to(folder))

        marks = stamps_for_doc(self.sig_state, doc_id, folder, self.lang, png_exists=png_exists)
        if not stamps_digest_matches(frozen.stamps_digest, marks, folder):
            raise marks_changed(doc_id, name)
        return frozen_rel

    def _add_frozen_doc(  # noqa: C901, PLR0913 — пункт, источник, имя, три части состояния и версия
        self,
        item: SubmissionDocItem,
        source_rel: str,
        arcname: str,
        frozen: FrozenPdf,
        detached: list[tuple[str, DetachedSignature]],
        embedded: list[tuple[str, EmbeddedSignature]],
        version: _Version | None,
    ) -> None:
        """Итоговый PDF, PDF для открепленных (если он другой), подписи и ключи. Ошибки до любой записи."""
        frozen_rel = self._check_frozen_current(item.doc_id, source_rel, arcname, frozen, pinned=version is not None)
        pdf_name = PurePosixPath(arcname).name
        parent = PurePosixPath(arcname).parent
        final_rel, final_sha, final_size = frozen_rel, frozen.sha256, frozen.size
        if embedded:
            signed_rel = _contained(frozen.signed_path)
            if signed_rel is None or self.probe.sha256(signed_rel) != frozen.signed_sha256:
                raise signed_pdf_changed(item.doc_id, PurePosixPath(arcname).stem)
            final_rel, final_sha, final_size = signed_rel, frozen.signed_sha256, frozen.signed_size
        entries = [
            PackEntry(
                PackEntryKind.copy,
                arcname,
                source=ManifestFile(final_rel, sha256=final_sha, size=final_size),
                critical=True,
            )
        ]
        # Открепленные подписи покрывают зафиксированные байты: при встроенных подписях это уже другой файл.
        base_name = pdf_name
        if embedded and detached:
            stem = pdf_name.rsplit(".", 1)[0]
            base_name = f"{stem}.{BASE_SUFFIX.get(self.lang, BASE_SUFFIX['ru'])}.pdf"
            entries.append(
                PackEntry(
                    PackEntryKind.copy,
                    str(parent / base_name),
                    source=ManifestFile(frozen_rel, sha256=frozen.sha256, size=frozen.size),
                    critical=True,
                )
            )
        guide_sigs = list(self._image_signatures(item))
        sigs: list[PackageSignature] = []
        used: set[str] = set()
        for slot_id, sig in detached:
            sig_rel = _contained(sig.file)
            if sig_rel is None or not self.probe.is_file(sig_rel):
                raise signature_missing(item.doc_id, PurePosixPath(arcname).stem, self._slot_label(slot_id))
            label = self._slot_label(slot_id)
            # Имя из самой подписи: кто подписал на деле, а не кого ждали на плашке.
            signer = signer_display_name(sig.signer) or signer_for(self.project, slot_id).name or label
            sig_name = detached_signature_name(base_name, signer, sig.format, PurePosixPath(sig_rel).suffix)
            if sig_name in used:
                sig_name = detached_signature_name(
                    base_name, f"{signer} {label}", sig.format, PurePosixPath(sig_rel).suffix
                )
            used.add(sig_name)
            entries.append(
                PackEntry(PackEntryKind.copy, str(parent / sig_name), source=ManifestFile(sig_rel), critical=True)
            )
            sigs.append(PackageSignature(label, sig_name, sig.format, signer, sig.signer_id))
            guide_sigs.append(
                GuideSignature(
                    "detached",
                    label,
                    signer,
                    str(parent / sig_name),
                    sig.format,
                    str(parent / base_name),
                    page_date=self._page_date(item.doc_id, slot_id),
                    signing_time=_signing_time(sig.signed_at),
                )
            )
        guide_sigs += [
            GuideSignature(
                "pades",
                self._slot_label(slot_id),
                signer_display_name(emb.signer) or signer_for(self.project, slot_id).name,
                page_date=self._page_date(item.doc_id, slot_id),
                signing_time=_signing_time(emb.signed_at),
            )
            for slot_id, emb in embedded
        ]
        guide_sigs += self._unsigned_signatures(item)
        keys = public_key_files(self.key_exporter.export_public, sigs) if self.key_exporter is not None else {}
        for name, blob in keys.items():
            entries.append(
                PackEntry(PackEntryKind.blob, str(parent / name), blob=InlineBlob.from_bytes(blob), critical=True)
            )
        self.entries.extend(entries)
        self.guide.append(
            _with_version(
                GuideDocument(
                    pdf=arcname,
                    sha256=final_sha,
                    signatures=tuple(guide_sigs),
                    base=str(parent / base_name) if base_name != pdf_name else "",
                    base_sha256=frozen.sha256 if base_name != pdf_name else "",
                    base_size=frozen.size if base_name != pdf_name else 0,
                    keys=tuple(str(parent / k) for k in keys),
                ),
                version,
            )
        )

    def add_guide(self) -> None:
        """Одна инструкция «как проверить» на весь комплект, если в нём есть электронные подписи.

        Комплект из одних картинок инструкции не получает: проверять в нём нечего, а лишний файл в LMS мешает.
        """
        if not any(sig.kind in CRYPTO_GUIDE_KINDS for doc in self.guide for sig in doc.signatures):
            return
        name = VERIFY_GUIDE_NAME.get(self.lang, VERIFY_GUIDE_NAME["ru"])
        self.entries.append(
            PackEntry(PackEntryKind.text, name, text=build_verify_guide(self.lang, self.guide), critical=True)
        )

    def add_extra(self, extra: ExtraSubmissionItem) -> None:
        # Готовый текст (например, декларация ИИ через output-шаблон формы)
        # главнее файла на диске: исходник ему даже не нужен.
        rendered = self.rendered_extras.get(extra.source)
        if rendered is not None:
            self._add_text_extra(extra, rendered)
            return

        # Исходник (читаем в проекте) и output_name (пишем в папку пакета) держим
        # внутри своих корней: «../..» не должен ни утечь, ни перезаписать чужое.
        source_rel = _contained(extra.source)
        if source_rel is None:
            self.warn(
                "extra source escapes project", extra.output_name, REASON_EXTRA_SOURCE_ESCAPES, source=extra.source
            )
            return
        if not self.probe.is_file(source_rel):
            self.warn(
                "extra source not found", extra.output_name, REASON_EXTRA_SOURCE_MISSING, source_rel, path=source_rel
            )
            return
        if extra.format == "markdown":
            self._add_markdown_extra(source_rel, extra)
        else:
            self._add_raw_extra(source_rel, extra)

    def _add_text_extra(self, extra: ExtraSubmissionItem, content: str) -> None:
        arcname = _contained(_extra_arcname(extra.output_name))
        if arcname is None:
            self.warn(
                "extra output_name escapes folder",
                extra.output_name,
                REASON_ARCNAME_ESCAPES,
                output_name=extra.output_name,
            )
            return
        self.entries.append(PackEntry(PackEntryKind.text, arcname, text=content))

    def _add_markdown_extra(self, source_rel: str, extra: ExtraSubmissionItem) -> None:
        try:
            data = json.loads(self.probe.read_text(source_rel))
        except (OSError, json.JSONDecodeError) as exc:
            self.warn(
                "extra markdown read/parse error",
                extra.output_name,
                REASON_EXTRA_UNREADABLE,
                str(exc),
                path=source_rel,
                exc=str(exc),
            )
            return
        arcname = _contained(_extra_arcname(extra.output_name))
        if arcname is None:
            self.warn(
                "extra output_name escapes folder",
                extra.output_name,
                REASON_ARCNAME_ESCAPES,
                output_name=extra.output_name,
            )
            return
        lines: list[str] = [f"# {extra.output_name}", ""]
        for key, value in data.items():
            lines.append(f"**{key}**: {value}")
            lines.append("")
        self.entries.append(PackEntry(PackEntryKind.text, arcname, text="\n".join(lines)))

    def _add_raw_extra(self, source_rel: str, extra: ExtraSubmissionItem) -> None:
        arcname = _contained(extra.output_name)
        if arcname is None:
            self.warn(
                "extra output_name escapes folder",
                extra.output_name,
                REASON_ARCNAME_ESCAPES,
                output_name=extra.output_name,
            )
            return
        self.entries.append(PackEntry(PackEntryKind.copy, arcname, source=ManifestFile(source_rel)))


class PackPlanner:
    """Строит нагрузку pack.submission из проекта, состояния подписей и профиля сдачи."""

    def __init__(
        self,
        template_service: ProjectTemplateService | None = None,
        slot_service: SignatureSlotService | None = None,
    ) -> None:
        self._template_service = template_service or ProjectTemplateService()
        self._slot_service = slot_service or SignatureSlotService()

    def build(  # noqa: PLR0913
        self,
        project: Project,
        version: TemplateVersion,
        sig_state: SignaturesState,
        doc_items: list[SubmissionDocItem],
        extra_items: list[ExtraSubmissionItem],
        lang: Lang | str,
        rendered_extras: dict[str, str] | None,
        decisions: dict[str, bool] | None,
        probe: IProjectFileProbe,
        key_exporter: IPublicKeyExporter | None,
        base_name: str,
        profile_id: str,
        archive_format: str,
        *,
        keep_folder: bool = True,
        verify_manifest: bool = False,
    ) -> PackPlan:
        """План пакета: записи в порядке документов, затем дополнений.

        Ошибки замороженных источников (`PackError` с кодом и текстом на языке
        интерфейса) поднимаются здесь, до любой записи на диск.
        """
        try:
            fmt = ArchiveFormat(archive_format)
        except ValueError:
            raise archive_format_unknown(archive_format) from None
        run = _Run(
            project=project,
            version=version,
            sig_state=sig_state,
            lang=str(lang),
            rendered_extras=rendered_extras or {},
            decisions=decisions,
            probe=probe,
            key_exporter=key_exporter,
            template_service=self._template_service,
            slot_service=self._slot_service,
            profile_id=profile_id,
        )
        for item in doc_items:
            run.add_doc(item)
        for extra in extra_items:
            run.add_extra(extra)
        run.add_guide()
        payload = PackSubmissionPayload(
            base_name=base_name,
            profile_id=profile_id,
            lang=Lang(str(lang)),
            archive_format=fmt,
            keep_folder=keep_folder,
            entries=tuple(run.entries),
            verify_manifest=verify_manifest,
        )
        return PackPlan(payload=payload, warnings=tuple(run.warnings), notices=tuple(run.notices))
