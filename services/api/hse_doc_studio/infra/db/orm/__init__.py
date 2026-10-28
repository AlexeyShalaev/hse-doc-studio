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
from hse_doc_studio.infra.db.orm.identity import (
    InstanceSettingRow,
    PasswordCredentialRow,
    UserIdentityRow,
    UserRow,
)
from hse_doc_studio.infra.db.orm.instance_meta import InstanceMetaRow
from hse_doc_studio.infra.db.orm.jobs import FairShareRow, JobQueueStateRow, JobRow, JobRunnerPollRow
from hse_doc_studio.infra.db.orm.projects import ProjectMemberRow, ProjectRow

__all__ = [
    "ApiTokenRow",
    "AuditLogRow",
    "AuthTokenRow",
    "FairShareRow",
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
    "RegistrationInviteRow",
    "SessionRow",
    "UserIdentityRow",
    "UserRow",
]
