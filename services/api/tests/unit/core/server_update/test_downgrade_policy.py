"""Политика отката на выбранную версию: чистые функции (вердикт по схеме, ревизии из истории, старшие релизы)."""

from __future__ import annotations

from datetime import UTC, datetime

from hse_doc_studio.core.server_update.entities import ReleaseInfo, RunKind, RunStatus, RunTrigger, UpdateRun
from hse_doc_studio.core.server_update.versions import SchemaVerdict, known_revisions, older_releases, schema_verdict
from hse_doc_studio.infra.update.server_updater import plan

T = datetime(2026, 11, 1, tzinfo=UTC)


def _run(
    frm: str, to: str, *, fr: str | None, tr: str | None, status: RunStatus, kind: RunKind = RunKind.update
) -> UpdateRun:
    return UpdateRun(
        id=f"{frm}-{to}",
        kind=kind,
        trigger=RunTrigger.manual,
        status=status,
        from_version=frm,
        to_version=to,
        created_at=T,
        from_revision=fr,
        to_revision=tr,
    )


def test__verdict__equal_revision_is_compatible_other_is_not_missing_is_unknown() -> None:
    known = {"0.3.2": "r2", "0.3.1": "r1"}
    assert schema_verdict("0.3.2", "r2", known) == (SchemaVerdict.compatible, "r2")
    assert schema_verdict("0.3.1", "r2", known) == (SchemaVerdict.incompatible, "r1")
    assert schema_verdict("0.3.0", "r2", known) == (SchemaVerdict.unknown, None)
    assert schema_verdict("0.3.2", None, known) == (SchemaVerdict.unknown, "r2")


def test__known_revisions__learns_from_successful_and_rolled_back_updates_only() -> None:
    runs = [
        _run("0.3.0", "0.3.1", fr="r0", tr="r1", status=RunStatus.succeeded),
        _run("0.3.1", "0.3.2", fr="r1", tr="r2", status=RunStatus.succeeded),
        # откатившееся обновление говорит только про исходную версию, схему цели оно не доказывает
        _run("0.3.2", "0.4.0", fr="r2", tr="r3", status=RunStatus.rolled_back),
        _run("0.4.0", "0.3.2", fr="r9", tr="r9", status=RunStatus.succeeded, kind=RunKind.rollback),
    ]
    assert known_revisions(runs) == {"0.3.0": "r0", "0.3.1": "r1", "0.3.2": "r2"}


def test__older_releases__only_older_newest_first() -> None:
    releases = [ReleaseInfo(v) for v in ("0.3.1", "0.4.0", "0.3.10", "0.3.2", "0.3.3")]
    assert [r.version for r in older_releases("0.3.3", releases)] == ["0.3.2", "0.3.1"]


def test__schema_mismatch__message_explains_and_equal_heads_pass() -> None:
    assert plan.schema_mismatch("0.3.2", "r2", "r2") is None
    text = plan.schema_mismatch("0.3.2", "r3", "r2")
    assert text is not None
    assert "r2" in text
    assert "r3" in text
    assert "nothing was changed" in text
    assert plan.schema_mismatch("0.3.2", None, None) is not None
