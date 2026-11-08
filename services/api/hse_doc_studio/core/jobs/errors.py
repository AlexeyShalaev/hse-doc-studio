from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.jobs.availability import no_runner_code
from hse_doc_studio.core.jobs.enums import JobErrorCategory, RunnerErrorCode

if TYPE_CHECKING:
    from hse_doc_studio.core.jobs.runner_fit import RunnerFit, RunnerGapReason


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


class NoRunnerAvailableError(Exception):
    """Нет живого раннера с нужными тегами: задача встала бы в очередь без исполнителя.

    `any_runner`: раннеры вообще есть, но ни один не берёт эти теги (409 `no_runner_for_tags`);
    иначе раннеров нет совсем (409 `no_runners`).
    """

    def __init__(
        self, tags: frozenset[str] = frozenset(), *, any_runner: bool = False, fit: RunnerFit | None = None
    ) -> None:
        needed = ", ".join(sorted(tags)) or "any"
        super().__init__(fit.describe() if fit is not None else f"no live runner for tags: {needed}")
        self.tags = tags
        self.any_runner = any_runner
        # Что с подходящими раннерами: на паузе, не в сети или их нет; `None` у старых вызовов без разбора.
        self.fit = fit

    @property
    def code(self) -> str:
        return no_runner_code(any_runner=self.any_runner)

    @property
    def reason(self) -> RunnerGapReason | None:
        return self.fit.reason if self.fit is not None else None


class StaleAttemptError(Exception):
    """Запрос по попытке, которая уже не текущая: аренда истекла или задачу взял другой раннер (409 `stale_attempt`)."""


class QueuedJobNotFoundError(NotFoundError):
    """Записи очереди с таким id нет (404 `job_not_found`)."""


class JobNotRunningError(Exception):
    """Задача не идёт: уже закончена или отменена, выходы и лог по ней не принимаются (409 `job_not_running`)."""


class BlobForbiddenError(Exception):
    """Блоба нет в манифесте этой задачи: чужие блобы раннеру не выдаются (403 `blob_forbidden`)."""


class BlobMissingError(Exception):
    """Блоб есть в манифесте или не заявлен, но хранилище его не отдаёт (404 `blob_missing`)."""


class ArtifactInvalidError(Exception):
    """Выход не прошёл проверку: не заявлен, неверный размер или хеш, не загружен (422 `artifact_invalid`)."""


class RunnerAuthError(Exception):
    """Раннер или задача не доказали подлинность: код из закрытого списка протокола раннера."""

    def __init__(self, code: RunnerErrorCode, detail: str = "") -> None:
        super().__init__(detail or code.value)
        self.code = code
        self.detail = detail or code.value


class RunnerNotFoundError(NotFoundError):
    """Нет раннера или токена регистрации с таким id."""
