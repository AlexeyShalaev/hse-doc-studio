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

__all__ = [
    "Capability",
    "ILocalRunnerHost",
    "InstallError",
    "InstallJob",
    "InstallStepState",
    "InstallTarget",
    "LocalInstance",
    "LocalRunnerSpec",
    "ProgressReporter",
    "UnavailableReason",
]
