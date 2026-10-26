"""Перевод результатов сценариев Git-синхронизации в тела ответов (api.schemas.git_sync).

Общие для роутеров проекта и глобального: операцию отдают оба, статус тоже. Секретов здесь нет по построению:
в сценариях их нет в результатах.
"""

from __future__ import annotations

from hse_doc_studio.api.schemas import git_sync as schema
from hse_doc_studio.core.git_sync.entities import (
    CloneResult,
    CommitBrief,
    GitOperation,
    LastError,
    LastSync,
    PendingSession,
    SyncResult,
    SyncWarning,
)
from hse_doc_studio.use_cases.git_sync.probe_remote import ProbeView
from hse_doc_studio.use_cases.git_sync.status import GitStatusView


def _brief(commit: CommitBrief) -> schema.GitCommitBrief:
    return schema.GitCommitBrief(
        id=commit.id,
        short_id=commit.short_id,
        message=commit.message,
        author=commit.author,
        author_email=commit.author_email,
        created_at=commit.created_at,
        kind=commit.kind,
    )


def _last_error(error: LastError | None) -> schema.GitLastError | None:
    return None if error is None else schema.GitLastError(code=error.code.value, detail=error.detail, at=error.at)


def _last_sync(sync: LastSync | None) -> schema.GitLastSync | None:
    if sync is None:
        return None
    return schema.GitLastSync(
        id=sync.id,
        at=sync.at,
        outcome=sync.outcome.value,
        pulled_commits=sync.pulled_commits,
        pushed_commits=sync.pushed_commits,
    )


def _pending(pending: PendingSession | None) -> schema.GitPending | None:
    if pending is None:
        return None
    return schema.GitPending(
        session_id=pending.session_id, files_total=pending.files_total, files_open=pending.files_open
    )


def map_status(view: GitStatusView) -> schema.GitStatusResponse:
    remote = view.remote
    return schema.GitStatusResponse(
        connected=view.connected,
        ui_state=view.ui_state.value,
        remote=None
        if remote is None
        else schema.GitRemoteInfo(
            display_url=remote.display_url,
            kind=remote.kind.value,
            host=remote.host,
            provider=remote.provider,
            web_url=remote.web_url,
            branch=remote.branch,
            local_branch=remote.local_branch,
            credential=None
            if remote.credential is None
            else schema.GitRemoteCredentialRef(
                id=remote.credential.id, label=remote.credential.label, kind=remote.credential.kind.value
            ),
            insecure_http=remote.insecure_http,
        ),
        relation=view.relation.value,
        ahead=view.ahead,
        behind=view.behind,
        behind_files=view.behind_files,
        health=view.health.value,
        last_error=_last_error(view.last_error),
        blocked=None
        if view.blocked is None
        else schema.GitBlocked(reason=view.blocked.reason.value, required_studio=view.blocked.required_studio),
        profile_ok=view.profile_ok,
        incoming=[_brief(c) for c in view.incoming],
        outgoing=[_brief(c) for c in view.outgoing],
        operation=None
        if view.operation is None
        else schema.GitStatusOperation(
            id=view.operation.id,
            kind=view.operation.kind,
            phase=view.operation.phase,
            percent=view.operation.percent,
            cancellable=view.operation.cancellable,
            started_at=view.operation.started_at,
        ),
        pending=_pending(view.pending),
        last_fetch_at=view.last_fetch_at,
        last_fetch_ok_at=view.last_fetch_ok_at,
        last_sync_at=view.last_sync_at,
        last_sync=_last_sync(view.last_sync),
        auto_fetch=schema.GitAutoFetch(
            enabled=view.auto_fetch.enabled,
            interval_s=view.auto_fetch.interval_s,
            next_fetch_at=view.auto_fetch.next_fetch_at,
        ),
        shared_folder=None
        if view.shared_folder is None
        else schema.GitSharedFolder(
            provider=view.shared_folder.provider,
            root=view.shared_folder.root,
            acknowledged=view.shared_folder.acknowledged,
        ),
        bot_authored_commits=view.bot_authored_commits,
    )


def _warning(warning: SyncWarning) -> schema.OperationWarning:
    return schema.OperationWarning(code=warning.code.value, paths=list(warning.paths))


def _result(result: SyncResult | CloneResult | None) -> schema.SyncResult | schema.CloneResult | None:
    if result is None:
        return None
    if isinstance(result, CloneResult):
        return schema.CloneResult(
            project_id=result.project_id,
            folder=result.folder,
            access=result.access.value,
            required_studio=result.required_studio,
            warnings=[_warning(w) for w in result.warnings],
        )
    return schema.SyncResult(
        outcome=result.outcome.value,
        pulled_commits=result.pulled_commits,
        pushed_commits=result.pushed_commits,
        merge_commit=result.merge_commit,
        files_changed=result.files_changed,
        auto=[schema.AutoMergedFile(path=a.path, action=a.action.value, copy_path=a.copy_path) for a in result.auto],
        conflicts=None
        if result.conflicts is None
        else schema.ConflictCounts(files_total=result.conflicts.files_total, files_open=result.conflicts.files_open),
        warnings=[_warning(w) for w in result.warnings],
    )


def map_operation(operation: GitOperation) -> schema.OperationResponse:
    return schema.OperationResponse(
        id=operation.id,
        kind=operation.kind.value,
        project_id=operation.project_id,
        status=operation.status.value,
        phase=operation.phase.value,
        percent=operation.percent,
        message=operation.message,
        cancellable=operation.cancellable,
        started_at=operation.started_at,
        finished_at=operation.finished_at,
        result=_result(operation.result),
        error=None
        if operation.error is None
        else schema.OperationError(code=operation.error.code.value, detail=operation.error.detail),
    )


def map_probe(view: ProbeView) -> schema.ProbeResponse:
    url = view.url
    project = view.project
    return schema.ProbeResponse(
        ok=view.ok,
        error=None
        if view.error is None
        else schema.ProbeError(
            code=view.error.code.value,
            detail=view.error.detail,
            host_keys=[schema.GitHostKey(type=k.type, fingerprint_sha256=k.fingerprint_sha256) for k in view.host_keys]
            or None,
        ),
        url=schema.ProbeUrl(
            display_url=url.display_url,
            kind=url.kind.value,
            host=url.host,
            provider=url.provider.value,
            owner=url.owner,
            repo=url.repo,
            token_stripped=url.token_stripped,
        ),
        reachable=view.reachable,
        auth_ok=view.auth_ok,
        empty=view.empty,
        default_branch=view.default_branch,
        branches=list(view.branches),
        relation=view.relation.value,
        project=None
        if project is None
        else schema.ProbeProject(
            id=project.id,
            name=project.name,
            pack_id=project.pack_id,
            template_id=project.template_id,
            template_version=project.template_version,
            kind=project.kind,
            staffing=project.staffing,
            authors_count=project.authors_count,
        ),
        schema_access=None if view.schema_access is None else view.schema_access.value,
        required_studio=view.required_studio,
        template_available=view.template_available,
    )
