from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from hse_doc_studio.core.enums import (
    CheckSeverity,
    EngineType,
    PersonRole,
    RequirementFormatKind,
    SignMode,
)


@dataclass(frozen=True)
class ProjectLock:
    pack_id: str
    template_id: str
    version: str
    engine: EngineType


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


@dataclass(frozen=True)
class SignaturesState:
    """Project-level signatures state.

    `slots` holds the global PNG per slot (one upload, reused across docs).
    `placements` holds the per-(doc, slot) positioning.
    """

    slots: dict[str, SignatureSlot]
    placements: dict[str, dict[str, SignaturePlacement]]

    @classmethod
    def empty(cls) -> SignaturesState:
        return cls(slots={}, placements={})


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
