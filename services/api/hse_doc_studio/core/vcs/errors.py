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


class VcsInvalidRefError(VcsCommandError):
    """Имя ветки/тега или ревизия не прошли проверку до запуска git.

    Наследует `VcsCommandError`, чтобы роутеры отвечали 400, как на отказ самого git.
    """

    def __init__(self, value: str, reason: str) -> None:
        VcsError.__init__(self, reason)
        self.command = "check-ref-format"
        self.stderr = reason
        self.value = value


class ProfileValidationError(ValueError):
    """Имя или e-mail автора не годятся для подписи коммита.

    `field` — "name" или "email", `reason` — "required", "too_long" или "invalid";
    вместе они дают код правила `<field>_<reason>`, по которому форма подсвечивает поле.
    """

    def __init__(self, field: str, reason: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.reason = reason
        self.message = message

    @property
    def code(self) -> str:
        return f"{self.field}_{self.reason}"


class ProfileInvalidError(ValueError):
    """Профиль не принят: перечислены все негодные поля, а не только первое."""

    def __init__(self, errors: list[ProfileValidationError]) -> None:
        super().__init__("; ".join(e.message for e in errors))
        self.errors = errors
