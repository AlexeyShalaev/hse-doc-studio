"""Личность раннера на диске: токен регистрации одноразовый, поэтому выданный токен раннера хранится у раннера."""

from __future__ import annotations

import contextlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

from hse_doc_studio.core.jobs.wire import RunnerRegisterResponse

IDENTITY_FILE = "identity.json"


@dataclass(frozen=True)
class RunnerIdentity:
    api_url: str
    runner_id: str
    runner_token: str


class RunnerIdentityStore:
    def __init__(self, data_dir: Path) -> None:
        self._path = data_dir / IDENTITY_FILE

    def load(self, api_url: str) -> RunnerIdentity | None:
        """Сохранённая личность, если она выдана этим же api; битый файл или чужой адрес это «не зарегистрирован»."""
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            identity = RunnerIdentity(str(data["api_url"]), str(data["runner_id"]), str(data["runner_token"]))
        except (OSError, ValueError, KeyError, TypeError):
            return None
        return identity if identity.api_url == api_url else None

    def save(self, api_url: str, registered: RunnerRegisterResponse) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        payload = {"api_url": api_url, "runner_id": registered.runner_id, "runner_token": registered.runner_token}
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)
        tmp.replace(self._path)

    def forget(self) -> None:
        with contextlib.suppress(OSError):
            self._path.unlink()
