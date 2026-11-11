"""Шаг очистки: одна команда Docker (или шаг, подключённый процессом) со своим статусом и итогом."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

# Шаги, которые `DockerCleanupJobManager` умеет сам. Другие виды подключает процесс (раннер: свой кэш).
DockerStepKind = Literal["build_cache", "dangling_images", "image", "container"]
DOCKER_STEP_KINDS: Final[frozenset[str]] = frozenset({"build_cache", "dangling_images", "image", "container"})

StepStatus = Literal["pending", "running", "done", "error", "skipped"]


@dataclass
class CleanupStep:
    # `DockerStepKind` или вид, подключённый в `DockerCleanupJobManager(extra_steps=...)`.
    kind: str
    # Image reference or container name; None for the prune steps.
    ref: str | None = None
    status: StepStatus = "pending"
    freed_bytes: int = 0
    error: str | None = None
