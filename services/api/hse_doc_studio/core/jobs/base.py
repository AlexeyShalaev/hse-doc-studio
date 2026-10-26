"""Маркерные базы полезной нагрузки и результата задачи.

Нагрузка и результат ездят между процессами, поэтому содержат только данные:
str/int/float/bool/None, StrEnum, UUID, datetime, tuple, frozenset[str], Optional
и вложенные frozen-датаклассы. Path, bytes, сущности и вызываемые объекты в них
не допускаются, это проверяет codec.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class JobPayload:
    """База нагрузки задачи (что именно делать)."""


@dataclass(frozen=True)
class JobResultData:
    """База полезного результата успешной или частично успешной задачи."""
