"""ORM-модели. Каждая зона держит свои таблицы в своём модуле и импортирует их здесь для autogenerate."""

from hse_doc_studio.infra.db.orm.ai_providers import AIProviderRow
from hse_doc_studio.infra.db.orm.auth import (
    ApiTokenRow,
    AuditLogRow,
    AuthTokenRow,
    LoginAttemptRow,
    MailOutboxRow,
    OidcProviderRow,
    RegistrationInviteRow,
    SessionRow,
)
from hse_doc_studio.infra.db.orm.blobs import BlobRow, FileHashCacheRow
from hse_doc_studio.infra.db.orm.chat import AgentRunRow, ChatMessageRow, ChatSessionRow, ChatSummaryRow
from hse_doc_studio.infra.db.orm.compile import CompileRecordRow
from hse_doc_studio.infra.db.orm.git_credentials import GitCredentialRow, GitRemoteBindingRow
from hse_doc_studio.infra.db.orm.git_trust import GitHostSettingsRow, GitKnownHostRow
from hse_doc_studio.infra.db.orm.identity import (
    InstanceSettingRow,
    PasswordCredentialRow,
    UserIdentityRow,
    UserRow,
    UserSettingRow,
)
from hse_doc_studio.infra.db.orm.instance_meta import InstanceMetaRow
from hse_doc_studio.infra.db.orm.invitations import (
    AccessRequestRow,
    NotificationRow,
    ProjectInvitationRow,
    ProjectTransferRow,
)
from hse_doc_studio.infra.db.orm.jobs import (
    FairShareRow,
    JobQueueStateRow,
    JobRow,
    JobRunnerPollRow,
    QuotaRow,
    RunnerPairingRow,
    RunnerRegistrationTokenRow,
    RunnerRow,
)
from hse_doc_studio.infra.db.orm.orgs import GroupMemberRow, GroupRow, OrgMemberRow, OrgRow
from hse_doc_studio.infra.db.orm.project_usage import ProjectUsageRow
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow
from hse_doc_studio.infra.db.orm.signing_identities import SigningIdentityRow
from hse_doc_studio.infra.db.orm.submission import SubmissionRow

__all__ = [
    "AIProviderRow",
    "AccessRequestRow",
    "AgentRunRow",
    "ApiTokenRow",
    "AuditLogRow",
    "AuthTokenRow",
    "BlobRow",
    "ChatMessageRow",
    "ChatSessionRow",
    "ChatSummaryRow",
    "CompileRecordRow",
    "FairShareRow",
    "FileHashCacheRow",
    "GitCredentialRow",
    "GitHostSettingsRow",
    "GitKnownHostRow",
    "GitRemoteBindingRow",
    "GroupMemberRow",
    "GroupRow",
    "InstanceMetaRow",
    "InstanceSettingRow",
    "JobQueueStateRow",
    "JobRow",
    "JobRunnerPollRow",
    "LoginAttemptRow",
    "MailOutboxRow",
    "NotificationRow",
    "OidcProviderRow",
    "OrgMemberRow",
    "OrgRow",
    "PasswordCredentialRow",
    "ProjectInvitationRow",
    "ProjectMemberRow",
    "ProjectRow",
    "ProjectTransferRow",
    "ProjectUsageRow",
    "QuotaRow",
    "RegistrationInviteRow",
    "RunnerPairingRow",
    "RunnerRegistrationTokenRow",
    "RunnerRow",
    "SessionRow",
    "SigningIdentityRow",
    "SubmissionRow",
    "UserIdentityRow",
    "UserRow",
    "UserSettingRow",
]
