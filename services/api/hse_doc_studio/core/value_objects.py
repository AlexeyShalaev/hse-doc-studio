from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hse_doc_studio.core.enums import (
    CheckSeverity,
    DateMarkAlign,
    DateMarkFormat,
    DetachedFormat,
    DetachedOrigin,
    DetachedVerdict,
    EngineType,
    PersonRole,
    RequirementFormatKind,
    SignedAtSource,
    SignMode,
)


@dataclass(frozen=True)
class ProjectLock:
    pack_id: str
    template_id: str
    version: str
    engine: EngineType
    # Дайджест содержимого версии шаблона, на которой проект создан или на
    # которую обновлён (infra.template.releases.version_digest). Расхождение с
    # реестром выпусков значит, что проект сделан на dev-сборке. None — проект
    # старше этого поля.
    digest: str | None = None
    # `min_studio` версии шаблона: старая Студия, у которой этой версии нет,
    # говорит пользователю, какая версия Студии нужна.
    min_studio: str | None = None


@dataclass(frozen=True)
class ProjectSchema:
    """Версия формата данных проекта (`.hse-studio/*.json`), см. core.project_schema.

    `read_compat` / `write_compat` — минимальная версия схемы, которую должна
    понимать Студия, чтобы читать / писать эти данные (как read/write version
    в заголовке SQLite). `written_by` — версия Студии, записавшей файл.
    """

    version: int
    read_compat: int
    write_compat: int
    written_by: str = ""


@dataclass(frozen=True)
class Author:
    name: str
    group: str | None = None
    email: str | None = None
    # Team mode. `slug` — ключ папки автора в раскладке проекта (транслит
    # фамилии, [a-z][a-z0-9_]*); в solo-проектах None. `topic` — личная тема
    # работы («Серверная часть Системы X»); project.name в team-проекте несёт
    # название системы. `managed` — ведём ли комплект файлов этого автора в
    # ЭТОМ проекте (сокомандник может вести свой у себя). `meta` — значения
    # пак-полей со scope=author (doc_code_base/udc/name_en/name_short);
    # одноимённые project.meta-ключи остаются «системными» для shared-доков.
    slug: str | None = None
    topic: str | None = None
    managed: bool = True
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class Person:
    name: str
    role: PersonRole
    title: str | None = None
    # Учёная степень/звание — отдельная строка титула ВКР («Кандидат
    # технических наук»); в должность не входит.
    degree: str | None = None


@dataclass(frozen=True)
class SignerInfo:
    """Who is expected to sign a slot, as printed on the signature plate.

    The plate sits inside the PDF the signature covers, so its data must be known
    before the file is frozen: it comes from the signer's public certificate or
    key (or a Studio key, or is typed in). `signer_id` is what the signature is
    compared with later: certificate SHA-256 / OpenPGP fingerprint, empty when typed in.
    """

    kind: str  # "x509" | "openpgp" | "manual"
    owner: str
    cert_id: str = ""  # certificate serial (x509) or key id (openpgp), as printed
    valid_from: str | None = None  # ISO 8601
    valid_to: str | None = None
    signer_id: str = ""
    # Printed under the caption: "" (nothing), "ukep" (enhanced qualified), "unep" (enhanced non-qualified).
    level: str = ""


@dataclass(frozen=True)
class SignatureSlot:
    """Global per-slot state — the uploaded PNG, shared across all docs.

    `signing_identity_id` and `sign_mode` are optional crypto-layer fields.
    Their defaults keep all existing `signatures.json` files readable without
    migration: image mode with no crypto identity = current PNG-overlay only.
    """

    png_path: str | None
    natural_width_px: int | None
    natural_height_px: int | None
    signing_identity_id: str | None = None
    sign_mode: SignMode = SignMode.image
    sign_reason: str = ""
    # Detached e-signature slots: the expected signer printed on the plate.
    signer: SignerInfo | None = None


@dataclass(frozen=True)
class DateMark:
    """Метка даты подписания слота на странице документа (docs/design/signing-route.md, 14.3).

    Своя рамка в миллиметрах от левого верхнего угла страницы, как у размещения; печатается часть дня подписи
    (`SignaturePlacement.signed_at`) в формате `format`. `id` уникален в пределах слота документа (`d1`, `d2`, ...).
    """

    id: str
    page: int
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    format: DateMarkFormat
    align: DateMarkAlign = DateMarkAlign.centered


@dataclass(frozen=True)
class SignedAt:
    """Момент подписи слота в документе (14.3): из согласия участника маршрута или день, который указал автор.

    `at` ISO 8601: у согласия момент с поясом, у ручной даты только день («2026-11-13»). `token` отпечаток согласия
    `build:<sha>` (только у `approval`): по нему маршрут видит, что документ согласован заново и дату пора обновить.
    """

    at: str
    source: SignedAtSource
    token: str = ""


@dataclass(frozen=True)
class SignaturePlacement:
    """Per-(doc, slot) placement on the compiled PDF.

    Coordinates are stored in millimetres from the **top-left** of the page —
    the convention the UI uses when overlaying onto a pdfjs-rendered page.
    The PDF stamper converts to PDF native coords (bottom-left origin in points)
    at stamping time.
    """

    enabled: bool
    page: int
    x_mm: float
    y_mm: float
    width_mm: float
    # Дата подписания этой подписи в этом документе (ISO «2026-05-12»).
    # Штампуется текстом «12.05.2026» рядом с подписью; None — без даты.
    sign_date: str | None = None
    # Метки даты подписания слота (signing-route.md, 14.3): где угодно в документе, рисуются и при `enabled: false`.
    dates: tuple[DateMark, ...] = ()
    # Момент подписи этого слота в этом документе: из него печатаются метки даты.
    signed_at: SignedAt | None = None


@dataclass(frozen=True)
class FrozenPdf:
    """A PDF fixed for signing: stamped once, then never touched.

    Detached signatures cover these exact bytes. `source_sha256` is the hash of
    the compiled PDF the copy was made from — a different hash of the current
    build means the document was rebuilt and every signature is out of date.
    """

    path: str  # relative to the project folder
    sha256: str
    source_sha256: str
    size: int
    frozen_at: str  # ISO 8601, UTC
    # Hash of what was stamped (placements, plate data). A different current value
    # means signers or positions changed after freezing: the plate is out of date.
    stamps_digest: str = ""
    # The frozen PDF with embedded PAdES signatures appended as incremental updates
    # (docs/design/signature-plan.md). Empty while nobody signed with PAdES: then the
    # final file is the frozen one. The frozen bytes are always a prefix of this file.
    signed_path: str = ""
    signed_sha256: str = ""
    signed_size: int = 0


@dataclass(frozen=True)
class PinnedPdf:
    """Версия на подписи: копия собранного PDF, которую сняла отправка маршрута (signing-route.md, 12.3).

    Пока она есть, это источник подписи документа: фиксация штампует её, план и «С подписями» считаются по ней,
    а рабочая сборка живёт отдельно. Пишут её только сценарии маршрута; снимает отмена маршрута или явное
    «Подписывать текущую сборку». `pinned_at` время снятия: у документа, который не менялся, новая версия
    маршрута его не трогает. `route_id` и `round` какой маршрут и раунд её сняли.
    """

    path: str  # relative to the project folder: .hse-studio/frozen/<doc>.source.pdf
    sha256: str
    size: int
    pinned_at: str  # ISO 8601, UTC
    route_id: str = ""
    round: int = 0


@dataclass(frozen=True)
class SkippedSlot:
    """Пропуск подписи маршрутом (signing-route.md, 13.3): на точке `profile_id` место не подписывают.

    Источник истины пропуска это участник маршрута в Postgres, а запись в файлах его эффект, как `withheld`:
    её читают план подписей, проверка пакета, `КАК_ПРОВЕРИТЬ.txt` и фиксация. `keep_mark` метка уже стоит в
    зафиксированном PDF, над которым есть ЭП, и остаётся в нём (13.5); без него метка не рисуется нигде.
    """

    profile_id: str
    route_id: str
    round: int
    at: str  # ISO 8601, UTC
    keep_mark: bool = False


@dataclass(frozen=True)
class DetachedSignature:
    """A detached e-signature attached to a (doc, slot): the file plus what we learned from it."""

    file: str  # relative to the project folder
    format: DetachedFormat
    origin: DetachedOrigin
    pdf_sha256: str  # hash of the frozen PDF it was checked against
    verdict: DetachedVerdict
    signer: str
    signer_id: str  # OpenPGP fingerprint / certificate SHA-256
    added_at: str
    issuer: str = ""
    algorithm: str = ""
    signed_at: str | None = None
    not_before: str | None = None
    not_after: str | None = None
    chain: str | None = None
    notes: tuple[str, ...] = ()
    root_subject: str = ""
    root_fingerprint: str = ""


@dataclass(frozen=True)
class EmbeddedSignature:
    """A PAdES signature of a (doc, slot): one incremental update on top of the frozen PDF.

    `base_sha256` is the frozen PDF the chain grew from; `revision_size` and
    `revision_sha256` describe the file right after this signature was appended, so
    later signatures can be told apart from tampering with this one.
    """

    field_name: str
    base_sha256: str
    revision_size: int
    revision_sha256: str
    verdict: DetachedVerdict
    signer: str
    signer_id: str  # certificate SHA-256
    added_at: str
    signed_at: str | None = None
    issuer: str = ""
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class SignaturesState:
    """Project-level signatures state.

    `slots` holds the global PNG per slot (one upload, reused across docs).
    `placements` holds the per-(doc, slot) positioning.
    `frozen` and `detached` back the detached e-signature flow: the PDF fixed
    for signing per doc, and the signature files attached per (doc, slot).
    `withheld` lists, per doc, the slots whose visible mark is held back until
    the signer approves the document in a signing route
    (docs/design/signing-route.md, 6.1): the placement stays on, the mark is
    left out of every stamping and of the visible-layer fingerprint.
    `pinned` holds the signing-route snapshot of each document (docs/design/signing-route.md, 12.3): while it
    is there, it is the signing source of the document instead of the current build.
    """

    slots: dict[str, SignatureSlot]
    placements: dict[str, dict[str, SignaturePlacement]]
    frozen: dict[str, FrozenPdf] = field(default_factory=dict)
    detached: dict[str, dict[str, DetachedSignature]] = field(default_factory=dict)
    # PAdES signatures per (doc, slot), layered over the frozen PDF in signing order.
    embedded: dict[str, dict[str, EmbeddedSignature]] = field(default_factory=dict)
    withheld: dict[str, frozenset[str]] = field(default_factory=dict)
    # Версия на подписи по документам (signing-route.md, 12.3): источник подписи вместо текущей сборки.
    pinned: dict[str, PinnedPdf] = field(default_factory=dict)
    # Необязательные подписи (signing-route.md, 13.3): {doc_id: {profile_id: {slot_id}}}. На точке profile_id место
    # slot_id документа doc_id можно не подписывать. Ставит автор маршрута; видимый слой не меняет.
    optional: dict[str, dict[str, frozenset[str]]] = field(default_factory=dict)
    # Пропущенные маршрутом подписи (13.3): {doc_id: {slot_id: SkippedSlot}}.
    skipped: dict[str, dict[str, SkippedSlot]] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> SignaturesState:
        return cls(slots={}, placements={})

    def is_withheld(self, doc_id: str, slot_id: str) -> bool:
        return slot_id in self.withheld.get(doc_id, ())

    def is_optional(self, doc_id: str, profile_id: str, slot_id: str) -> bool:
        """Подпись `slot_id` документа необязательна на точке `profile_id`."""
        return slot_id in self.optional.get(doc_id, {}).get(profile_id, ())

    def skip_of(self, doc_id: str, slot_id: str, profile_id: str | None = None) -> SkippedSlot | None:
        """Пропуск пары; с `profile_id` только пропуск на этой точке (на другой точке пара не пропущена)."""
        skip = self.skipped.get(doc_id, {}).get(slot_id)
        if skip is None or (profile_id is not None and skip.profile_id != profile_id):
            return None
        return skip

    def mark_hidden(self, doc_id: str, slot_id: str) -> bool:
        """Метка слота не рисуется: придержана маршрутом до согласия (6.1) или пропущена без `keep_mark` (13.3).

        Пропущенная метка не рисуется ни на какой точке: в выпущенных паках документ с подписями входит в одну.
        """
        if self.is_withheld(doc_id, slot_id):
            return True
        skip = self.skip_of(doc_id, slot_id)
        return skip is not None and not skip.keep_mark


@dataclass(frozen=True)
class CustomFileOverride:
    """A user-uploaded file replacing a document's pack-generated output.

    When set on a `Document`, it supersedes `chosen_variant` everywhere a
    source is resolved (compile/preview/signing/packaging) — `chosen_variant`
    is deliberately left untouched so reverting to the template has something
    to fall back to. `convert_to_pdf_at_package` remembers the user's
    convert-to-PDF choice at packaging time for a convertible office format
    (None — not decided yet / not applicable).
    """

    original_filename: str
    stored_path: str
    ext: str
    uploaded_at: str
    convert_to_pdf_at_package: bool | None = None


@dataclass(frozen=True)
class ChecksOverride:
    disabled_categories: tuple[str, ...] = ()
    disabled: tuple[str, ...] = ()
    enabled: tuple[str, ...] = ()
    severity_override: dict[str, CheckSeverity] = field(default_factory=dict)


@dataclass(frozen=True)
class RequirementsFormat:
    """How requirement definitions/references are recognised in .tex sources.

    - ``macro``  — \\req{ID}{text} definitions + \\reqref{ID} references (default).
    - ``id``     — ``id_pattern`` matches bare IDs; every match in
      ``definition_docs`` is a definition, every match elsewhere is a reference.
    - ``custom`` — ``def_pattern`` (named groups id + optional title) and
      ``ref_pattern`` (named group ids) drive detection directly.

    Unused fields for the active ``kind`` are ignored.
    """

    kind: RequirementFormatKind = RequirementFormatKind.macro
    id_pattern: str | None = None
    definition_docs: tuple[str, ...] = ()
    def_pattern: str | None = None
    ref_pattern: str | None = None


@dataclass(frozen=True)
class CheckLocation:
    file: str
    line: int | None = None

    def __post_init__(self) -> None:
        # Canonicalise to POSIX separators. Engines build `file` from
        # `str(Path.relative_to(...))`, which on Windows yields backslashes
        # (`tz\tz.tex`); the file listing uses `Path.as_posix()` (`tz/tz.tex`).
        # Keeping a single forward-slash form lets consumers match paths
        # consistently across operating systems.
        if "\\" in self.file:
            object.__setattr__(self, "file", self.file.replace("\\", "/"))


@dataclass(frozen=True)
class CheckFix:
    """A deterministic, one-click fix for a finding.

    Pure text substitution — no LLM: replace the first occurrence of ``search``
    with ``replace`` on ``line`` of ``file`` (or the first in the whole file if
    ``line`` is None). ``title`` is the human label for the quick-fix action.
    """

    file: str
    search: str
    replace: str
    line: int | None = None
    title: str | None = None

    def __post_init__(self) -> None:
        # Same canonicalisation as CheckLocation.file — engines build fix.file
        # from the same Windows-yields-backslashes path construction, so without
        # this a single CheckResult's location.file and fix.file can disagree
        # on separator style.
        if "\\" in self.file:
            object.__setattr__(self, "file", self.file.replace("\\", "/"))


@dataclass(frozen=True)
class CheckResult:
    rule_id: str
    severity: CheckSeverity
    message: str
    location: CheckLocation | None = None
    fix: CheckFix | None = None


@dataclass(frozen=True)
class FormState:
    """Per-project saved answers for one pack-declared form.

    `answers` is a raw ``field_id -> value`` map — the engine never hardcodes
    which fields exist; their shape is governed by the pack's FormDefinition.
    `completed` records that the student explicitly signed the form off (a
    separate, derived "valid" flag is computed by FormValidationService).
    """

    schema_version: int
    completed: bool
    answers: dict[str, Any]

    @classmethod
    def empty(cls, schema_version: int = 1) -> FormState:
        return cls(schema_version=schema_version, completed=False, answers={})


@dataclass(frozen=True)
class FormValidationError:
    """A single unmet requirement on a filled form (warning-level, never fatal)."""

    field_id: str
    message: str
