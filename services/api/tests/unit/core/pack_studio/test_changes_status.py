"""Статус «Изменений» и главная кнопка (pack-studio-mcp.md, P4): та же таблица, что `resolveNextStep.test.ts`."""

from __future__ import annotations

from dataclasses import replace

import pytest
from hse_doc_studio.core.pack_studio.changes_status import (
    ChangesRaw,
    LintSummary,
    derive_status,
    lint_targets,
    resolve_next_step,
)
from hse_doc_studio.core.pack_studio.paths import VersionRef

DRAFT = VersionRef("demo", "report", "2026.1.1")
RELEASED = VersionRef("demo", "report", "2026.1.0")
DRAFT_FILE = f"{DRAFT.dir}/version.yaml"

BASE = ChangesRaw(
    workspace_kind="git",
    workspace_state="ready",
    open=DRAFT,
    open_released=False,
    released_versions=frozenset({RELEASED.dir}),
    notes=(("Правка",), ("Edit",)),
)


def _kind(raw: ChangesRaw) -> str | None:
    step = resolve_next_step(derive_status(raw))
    return step.kind if step is not None else None


@pytest.mark.parametrize(
    ("raw", "kind"),
    [
        (replace(BASE, workspace_state="cloning"), "connecting"),
        (replace(BASE, workspace_state="failed"), "checkAccess"),
        (replace(BASE, workspace_kind="folder"), "folder"),
        (replace(BASE, git_ready=False), None),
        (BASE, None),
        (replace(BASE, changed=((DRAFT_FILE, "modified"),)), "submit"),
        (replace(BASE, changed=((DRAFT_FILE, "modified"),), notes=((), ())), "describe"),
        (replace(BASE, open=RELEASED, open_released=True), "makeCopy"),
        (replace(BASE, open=RELEASED, open_released=True, changed=((DRAFT_FILE, "modified"),)), "toDraft"),
        (
            replace(
                BASE,
                changed=((DRAFT_FILE, "modified"),),
                lint=(LintSummary(DRAFT.dir, False, (("error", "схема: поле"),)),),
            ),
            "fixErrors",
        ),
        (
            replace(
                BASE,
                changed=((DRAFT_FILE, "modified"),),
                lint=(LintSummary(DRAFT.dir, False, (("error", "нет `changes.en`"),)),),
            ),
            "describe",
        ),
        (
            replace(BASE, changed=((DRAFT_FILE, "modified"),), pr_number=4, pushed_sha="a", head_sha="a"),
            "request",
        ),
        (
            replace(BASE, changed=((DRAFT_FILE, "modified"),), pr_number=4, pushed_sha="a", head_sha="b"),
            "updateRequest",
        ),
        (replace(BASE, pr_number=4, ci_pr_state="merged", open=RELEASED, open_released=True), "startNew"),
    ],
)
def test__next_step__table(raw: ChangesRaw, kind: str | None) -> None:
    assert _kind(raw) == kind


def test__status__request_label_checks_and_progress() -> None:
    raw = replace(
        BASE,
        changed=((DRAFT_FILE, "modified"), ("demo/pack.yaml", "modified")),
        pr_number=12,
        provider="gitlab",
        pushed_sha="a",
        head_sha="a",
        ci_state="pending",
        ci_checks=("success", "running"),
        behind=3,
    )

    status = derive_status(raw)
    step = resolve_next_step(status)

    assert status.changed_files == 2
    assert status.changed_in_version == 1
    assert status.request.label == "!12"
    assert status.request.checks.value == "pending"
    assert status.request.progress == (1, 2)
    assert status.behind == 3
    assert step is not None
    assert step.label == "!12"


def test__lint_targets__open_version_first_then_manifests_at_most_three() -> None:
    changed = [
        ("demo/templates/report/versions/2026.1.0/files/a.tex", "modified"),
        (DRAFT_FILE, "modified"),
        ("demo/pack.yaml", "modified"),
        ("demo/templates/other/versions/1.0.0/x.tex", "deleted"),
        ("demo/templates/report/template.yaml", "modified"),
    ]

    assert lint_targets(changed, DRAFT) == [DRAFT.dir, "demo/pack.yaml", "demo/templates/report/template.yaml"]


def test__released_errors_count_notes_findings() -> None:
    raw = replace(
        BASE,
        open=RELEASED,
        open_released=True,
        changed=((f"{RELEASED.dir}/version.yaml", "modified"),),
        lint=(LintSummary(RELEASED.dir, True, (("error", "нет `changes.en`"),)),),
    )

    status = derive_status(raw)

    assert status.errors == 1
    assert status.notes_needed is False
