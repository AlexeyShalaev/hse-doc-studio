from __future__ import annotations

from dataclasses import dataclass

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.jobs.enums import JobErrorCategory, RunnerErrorCode


class JobFailedError(RuntimeError):
    """Задача упала по внутренней причине (500)."""


class JobUnavailableError(RuntimeError):
    """Нужная для задачи среда недоступна (docker, образ, gpg)."""


@dataclass(frozen=True)
class JobError:
    """Ожидаемый сбой задачи: категория, стабильный код и сырая деталь.

    Обработчик отдаёт код и деталь, а локализованный текст собирает use case по коду.
    """

    category: JobErrorCategory
    code: str
    detail: str = ""

    def raise_for_error(self) -> None:
        message = self.detail or self.code
        match self.category:
            case JobErrorCategory.invalid_input:
                raise ValueError(message)
            case JobErrorCategory.not_found:
                raise NotFoundError(message)
            case JobErrorCategory.unavailable:
                raise JobUnavailableError(message)
            case JobErrorCategory.internal:
                raise JobFailedError(message)


class JobFailure(Exception):  # noqa: N818
    """Ожидаемый сбой, который обработчик бросает вместо результата."""

    def __init__(self, error: JobError) -> None:
        super().__init__(error.detail or error.code)
        self.error = error

    @classmethod
    def of(cls, category: JobErrorCategory, code: str, detail: str = "") -> JobFailure:
        return cls(JobError(category=category, code=code, detail=detail))


class StaleAttemptError(Exception):
    """Запрос по попытке, которая уже не текущая: аренда истекла или задачу взял другой раннер (409 `stale_attempt`)."""


class QueuedJobNotFoundError(NotFoundError):
    """Записи очереди с таким id нет (404 `job_not_found`)."""


class RunnerAuthError(Exception):
    """Раннер или задача не доказали подлинность: код из закрытого списка протокола раннера."""

    def __init__(self, code: RunnerErrorCode, detail: str = "") -> None:
        super().__init__(detail or code.value)
        self.code = code
        self.detail = detail or code.value


class RunnerNotFoundError(NotFoundError):
    """Нет раннера или токена регистрации с таким id."""
