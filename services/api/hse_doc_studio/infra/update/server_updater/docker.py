"""Обёртка над docker CLI. Всё, что апдейтер делает с хостом, идёт через `IDocker`: тесты подставляют фейк."""

from __future__ import annotations

import json
import subprocess  # noqa: S404 — этот модуль и есть драйвер docker CLI
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class Result:
    code: int
    out: str = ""
    err: str = ""

    @property
    def ok(self) -> bool:
        return self.code == 0


class IDocker(Protocol):
    def run(self, args: Sequence[str], timeout: float = 120.0) -> Result: ...


class CliDocker:
    def run(self, args: Sequence[str], timeout: float = 120.0) -> Result:
        try:
            proc = subprocess.run(  # noqa: S603 — аргументы собраны кодом, оболочки нет
                ["docker", *args],  # noqa: S607 — docker из PATH образа
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return Result(1, "", str(exc))
        return Result(proc.returncode, proc.stdout, proc.stderr)


def inspect(docker: IDocker, ref: str) -> dict[str, Any] | None:
    result = docker.run(["inspect", ref])
    if not result.ok:
        return None
    try:
        data = json.loads(result.out)
    except json.JSONDecodeError:
        return None
    return data[0] if isinstance(data, list) and data else None
