"""Статус панели «Изменения» и главная кнопка Студии шаблонов (pack-studio-ux.md, 4.3; pack-studio-mcp.md, P4).

Повтор чистых функций интерфейса `deriveChangesStatus` и `resolveNextStep` (`features/pack-space/changes` и
`next-step`) на сервере, чтобы агент MCP одним вызовом узнавал то же, что человек видит на кнопке «Изменения» и на
главной кнопке. Правила те же и в том же порядке; данные приходят из тех же ответов (`git`, дерево, линтер изменённых
мест, проверки хостинга, заметки манифеста). Сверки копии с основой (`useCopyScan`) здесь нет: файлы считаются по git.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Final

from hse_doc_studio.core.pack_studio.paths import (
    PACK_MANIFEST,
    RELEASES_FILE,
    TEMPLATE_MANIFEST,
    TEMPLATES_DIR,
    VERSIONS_DIR,
    VersionRef,
    version_ref_of,
)

# Сколько мест проверяем линтером сразу, как интерфейс (`MAX_LINT_TARGETS`).
MAX_LINT_TARGETS: Final = 3

# Находка про заметки версии (`changes.ru`, `changes.en`, `changes`): это шаг «Описать изменения», а не ошибка.
_NOTES_FINDING: Final = re.compile(r"`changes(\.[a-z]+)?`")
# Находка про номер версии: шаг, номер подбирается сам; «release.kind мягче класса» сюда не относится.
_NUMBER_FINDING: Final = re.compile(r"^release: номер \S+ после \S+ это (patch|minor|major), а изменения")

_FINISHED: Final = frozenset({"success", "failure", "neutral", "skipped", "cancelled"})


class Connection(StrEnum):
    cloning = "cloning"
    failed = "failed"
    ready = "ready"


class RequestChecks(StrEnum):
    pending = "pending"
    passed = "passed"
    failed = "failed"
    awaiting_approval = "awaiting_approval"
    unknown = "unknown"


@dataclass(frozen=True)
class LintSummary:
    """Ответ линтера по одному месту: что проверено, выпущена ли версия, находки (уровень и текст)."""

    target: str | None
    released: bool
    findings: tuple[tuple[str, str], ...]  # (severity, message)


@dataclass(frozen=True)
class ChangesRaw:
    """Всё, из чего собирается статус. `changed`: пути от папки паков с видом изменения (`deleted` и др.)."""

    workspace_kind: str  # git | folder
    workspace_state: str  # ready | cloning | failed
    open: VersionRef
    open_released: bool
    released_versions: frozenset[str]  # каталоги выпущенных версий, «пак/templates/шаблон/versions/в»
    git_ready: bool = True
    changed: tuple[tuple[str, str], ...] = ()
    lint: tuple[LintSummary, ...] = ()
    notes: tuple[tuple[str, ...], tuple[str, ...]] | None = None  # (ru, en); None: манифест не прочитан
    provider: str | None = None
    pr_number: int | None = None
    pr_url: str | None = None
    pushed_sha: str | None = None
    head_sha: str | None = None
    dirty: bool = False
    ci_state: str | None = None
    ci_pr_state: str | None = None
    ci_checks: tuple[str, ...] = ()  # состояния отдельных проверок хостинга
    behind: int = 0


@dataclass(frozen=True)
class Request:
    kind: str  # none | open | merged | closed
    number: int | None = None
    label: str | None = None
    url: str | None = None
    checks: RequestChecks = RequestChecks.unknown
    progress: tuple[int, int] | None = None
    new_edits: bool = False


@dataclass(frozen=True)
class ChangesStatus:
    connection: Connection
    workspace_kind: str
    released: bool
    load: str = "ready"
    changed_files: int = 0
    changed_in_version: int = 0
    changed_elsewhere: VersionRef | None = None
    errors: int = 0
    warnings: int = 0
    notes_needed: bool = False
    request: Request = field(default_factory=lambda: Request("none"))
    behind: int = 0


@dataclass(frozen=True)
class NextStep:
    """Главная кнопка: `kind` как у интерфейса (`makeCopy`, `fixErrors`, `describe`, `submit`, ...)."""

    kind: str
    count: int | None = None
    version: VersionRef | None = None
    label: str | None = None
    checks: RequestChecks | None = None
    progress: tuple[int, int] | None = None


def is_pack_manifest(path: str) -> bool:
    """`pack.yaml` пака, `template.yaml` и `releases.yaml` шаблона (как `isPackManifest` интерфейса)."""
    parts = path.split("/")
    name = parts[-1].lower()
    if len(parts) == 2:  # noqa: PLR2004
        return name == PACK_MANIFEST
    return len(parts) == 4 and parts[1].lower() == TEMPLATES_DIR and name in {TEMPLATE_MANIFEST, RELEASES_FILE}  # noqa: PLR2004


def lint_target_of(path: str) -> str | None:
    ref = version_ref_of(path)
    if ref is not None:
        return ref.dir
    return path if is_pack_manifest(path) else None


def _same(a: VersionRef, b: VersionRef) -> bool:
    return a.dir.casefold() == b.dir.casefold()


def lint_targets(changed: Sequence[tuple[str, str]], open_ref: VersionRef) -> list[str]:
    """Что проверять: открытая версия, если в ней правки, затем остальные места по алфавиту, не больше трёх."""
    targets: dict[str, None] = {}
    for path, status in changed:
        if status == "deleted":
            continue
        target = lint_target_of(path)
        if target:
            targets[target] = None
    open_dir = next((t for t in targets if t.casefold() == open_ref.dir.casefold()), None)
    rest = sorted(t for t in targets if t != open_dir)
    ordered = ([open_dir] if open_dir else []) + rest
    return ordered[:MAX_LINT_TARGETS]


def _version_key(ref: VersionRef) -> tuple[int, ...]:
    return tuple(int(p) if p.isdigit() else 0 for p in ref.version.split("."))


def _elsewhere(raw: ChangesRaw) -> VersionRef | None:
    found: dict[str, VersionRef] = {}
    for path, _ in raw.changed:
        ref = version_ref_of(path)
        if ref is not None and not _same(ref, raw.open):
            found[ref.dir.casefold()] = VersionRef(ref.pack, ref.template, ref.version)
    if not found:
        return None
    others = sorted(found.values(), key=_version_key, reverse=True)
    others.sort(key=lambda ref: ref.dir in raw.released_versions)
    return others[0]


def _checks(state: str | None) -> RequestChecks:
    return {
        "pending": RequestChecks.pending,
        "success": RequestChecks.passed,
        "failure": RequestChecks.failed,
        "awaiting_approval": RequestChecks.awaiting_approval,
    }.get(state or "", RequestChecks.unknown)


def _request(raw: ChangesRaw) -> Request:
    number = raw.pr_number
    if number is None:
        return Request("none")
    label = f"{'!' if raw.provider == 'gitlab' else '#'}{number}"
    if raw.ci_pr_state in {"merged", "closed"}:
        return Request(raw.ci_pr_state, number, label)
    progress = (sum(1 for s in raw.ci_checks if s in _FINISHED), len(raw.ci_checks)) if raw.ci_checks else None
    new_edits = raw.dirty or (raw.pushed_sha is not None and raw.head_sha != raw.pushed_sha)
    return Request("open", number, label, raw.pr_url, _checks(raw.ci_state), progress, new_edits)


def derive_status(raw: ChangesRaw) -> ChangesStatus:
    connection = (
        Connection.ready
        if raw.workspace_state == "ready"
        else Connection.cloning
        if raw.workspace_state == "cloning"
        else Connection.failed
    )
    base = ChangesStatus(connection=connection, workspace_kind=raw.workspace_kind, released=raw.open_released)
    if raw.workspace_kind == "folder" or connection is not Connection.ready:
        return base
    if not raw.git_ready:
        return ChangesStatus(connection, raw.workspace_kind, raw.open_released, load="failed")
    in_version = 0
    for path, _ in raw.changed:
        ref = version_ref_of(path)
        if ref is not None and _same(ref, raw.open):
            in_version += 1
    errors = warnings = 0
    notes_finding = False
    for report in raw.lint:
        notes = sum(1 for sev, msg in report.findings if sev == "error" and _NOTES_FINDING.search(msg))
        number = sum(1 for sev, msg in report.findings if sev == "error" and _NUMBER_FINDING.search(msg))
        skip_notes = 0 if report.released else notes
        skip = skip_notes + (0 if report.released else number)
        target = version_ref_of(report.target) if report.target else None
        notes_finding = notes_finding or (skip_notes > 0 and target is not None and _same(target, raw.open))
        errors += max(0, sum(1 for sev, _ in report.findings if sev == "error") - skip)
        warnings += sum(1 for sev, _ in report.findings if sev == "warning")
    notes_missing = raw.notes is not None and (not raw.notes[0] or not raw.notes[1])
    return ChangesStatus(
        connection=connection,
        workspace_kind=raw.workspace_kind,
        released=raw.open_released,
        changed_files=len(raw.changed),
        changed_in_version=in_version,
        changed_elsewhere=_elsewhere(raw),
        errors=errors,
        warnings=warnings,
        notes_needed=not raw.open_released and ((in_version > 0 and notes_missing) or notes_finding),
        request=_request(raw),
        behind=raw.behind,
    )


def resolve_next_step(status: ChangesStatus) -> NextStep | None:  # noqa: C901, PLR0911, PLR0912 — таблица 4.3 сверху вниз
    """Следующий шаг по таблице 4.3, первая подходящая строка; None: кнопки нет (черновик без правок)."""
    if status.connection is Connection.cloning:
        return NextStep("connecting")
    if status.connection is Connection.failed:
        return NextStep("checkAccess")
    if status.workspace_kind == "folder":
        return NextStep("folder")
    if status.load != "ready":
        return None
    request = status.request
    if request.kind == "merged":
        return NextStep("startNew")
    if status.released:
        if status.changed_files == 0 and request.kind != "open":
            return NextStep("makeCopy")
        if status.changed_in_version == 0 and status.changed_elsewhere is not None:
            return NextStep("toDraft", version=status.changed_elsewhere)
    if status.errors > 0:
        return NextStep("fixErrors", count=status.errors)
    if status.notes_needed:
        return NextStep("describe")
    if request.kind == "open":
        if request.new_edits:
            return NextStep("updateRequest")
        return NextStep("request", label=request.label, checks=request.checks, progress=request.progress)
    if status.changed_files > 0:
        return NextStep("submit")
    return None


def version_dir(pack: str, template: str, version: str) -> str:
    return f"{pack}/{TEMPLATES_DIR}/{template}/{VERSIONS_DIR}/{version}"
