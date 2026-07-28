from __future__ import annotations


class VcsError(Exception):
    """Base for ProjectVCS failures."""


class VcsUnavailableError(VcsError):
    """The project folder isn't reachable by the backend, or the git binary is missing.

    Mirrors compilation: the VCS store needs the same access to the project folder
    that a build does. Surfaced to the API as a structured 409, never a crash.
    """


class VcsNotInitializedError(VcsError):
    """No VCS store exists for this project yet (call EnsureVcsUC first)."""


class VcsCommandError(VcsError):
    """A git command exited non-zero."""

    def __init__(self, command: str, stderr: str) -> None:
        super().__init__(f"git {command} failed: {stderr.strip()}")
        self.command = command
        self.stderr = stderr
