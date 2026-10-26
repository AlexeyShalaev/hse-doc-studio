from __future__ import annotations

from enum import StrEnum


class JobKind(StrEnum):
    # Остальные виды добавляют слайсы своих семейств, по одному на вид.
    compile = "compile"


class JobStatus(StrEnum):
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"
    timed_out = "timed_out"


class JobErrorCategory(StrEnum):
    # Отображаются на ValueError / NotFoundError / недоступность / внутреннюю ошибку,
    # то есть на 400 / 404 / 409-503 / 500 в API.
    invalid_input = "invalid_input"
    not_found = "not_found"
    unavailable = "unavailable"
    internal = "internal"
