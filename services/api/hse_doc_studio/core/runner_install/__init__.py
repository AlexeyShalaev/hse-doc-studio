"""Установка раннеров из админки: возможности хоста, ход установки по шагам, порты docker и kubernetes."""

from hse_doc_studio.core.runner_install.entities import (
    Capability,
    InstallError,
    InstallJob,
    InstallStepState,
    InstallTarget,
    LocalInstance,
    LocalRunnerSpec,
    UnavailableReason,
)
from hse_doc_studio.core.runner_install.protocols import ILocalRunnerHost, ProgressReporter
from hse_doc_studio.core.runner_install.resources import (
    InvalidResourcesError,
    PodResources,
    ResourceDefaults,
    ResourceOverrides,
    resolve,
)
from hse_doc_studio.core.runner_install.ssh import (
    HostKey,
    ISshConnector,
    ISshCredentialRepository,
    ISshSession,
    RemoteSystem,
    SavedSshCredential,
    SshAuth,
    SshAuthKind,
    SshError,
    SshResult,
    SshTarget,
)

__all__ = [
    "Capability",
    "HostKey",
    "ILocalRunnerHost",
    "ISshConnector",
    "ISshCredentialRepository",
    "ISshSession",
    "InstallError",
    "InstallJob",
    "InstallStepState",
    "InstallTarget",
    "InvalidResourcesError",
    "LocalInstance",
    "LocalRunnerSpec",
    "PodResources",
    "ProgressReporter",
    "RemoteSystem",
    "ResourceDefaults",
    "ResourceOverrides",
    "SavedSshCredential",
    "SshAuth",
    "SshAuthKind",
    "SshError",
    "SshResult",
    "SshTarget",
    "UnavailableReason",
    "resolve",
]
