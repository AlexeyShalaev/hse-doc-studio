"""ORM-модели. Каждая зона держит свои таблицы в своём модуле и импортирует их здесь для autogenerate."""

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
from hse_doc_studio.infra.db.orm.compile import CompileRecordRow
from hse_doc_studio.infra.db.orm.identity import (
    InstanceSettingRow,
    PasswordCredentialRow,
    UserIdentityRow,
    UserRow,
    UserSettingRow,
)
from hse_doc_studio.infra.db.orm.instance_meta import InstanceMetaRow
from hse_doc_studio.infra.db.orm.jobs import (
    FairShareRow,
    JobQueueStateRow,
    JobRow,
    JobRunnerPollRow,
    RunnerRegistrationTokenRow,
    RunnerRow,
)
from hse_doc_studio.infra.db.orm.project_usage import ProjectUsageRow
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow
from hse_doc_studio.infra.db.orm.submission import SubmissionRow

__all__ = [
    "ApiTokenRow",
    "AuditLogRow",
    "AuthTokenRow",
    "BlobRow",
    "CompileRecordRow",
    "FairShareRow",
    "FileHashCacheRow",
    "InstanceMetaRow",
    "InstanceSettingRow",
    "JobQueueStateRow",
    "JobRow",
    "JobRunnerPollRow",
    "LoginAttemptRow",
    "MailOutboxRow",
    "OidcProviderRow",
    "PasswordCredentialRow",
    "ProjectMemberRow",
    "ProjectRow",
    "ProjectUsageRow",
    "RegistrationInviteRow",
    "RunnerRegistrationTokenRow",
    "RunnerRow",
    "SessionRow",
    "SubmissionRow",
    "UserIdentityRow",
    "UserRow",
    "UserSettingRow",
]
