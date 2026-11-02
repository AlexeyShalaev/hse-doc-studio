"""Журнал апдейтера на диске: что делается сейчас, что чем заменено и какие события ещё не доставлены в api.

Нужен потому, что api на время обновления гаснет (события ждут в очереди), а сам апдейтер может быть убит посреди
работы: по журналу он на старте понимает, на каком шаге остановился, и откатывает незаконченное.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

MAX_OUTBOX = 500


class Journal:
    def __init__(self, path: Path) -> None:
        self._path = path
        self.data: dict[str, Any] = {"run": None, "outbox": [], "last_ok": None}
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self.data.update(loaded)
            except (OSError, json.JSONDecodeError):
                pass  # битый журнал не должен мешать работе: начинаем с чистого

    def save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")
        with tmp.open("r+b") as handle:  # fsync на Windows требует дескриптор с записью
            os.fsync(handle.fileno())
        tmp.replace(self._path)

    @property
    def run(self) -> dict[str, Any] | None:
        return self.data.get("run")

    def start_run(self, run: dict[str, Any]) -> None:
        self.data["run"] = run
        self.save()

    def update_run(self, **changes: Any) -> None:
        if self.data["run"] is not None:
            self.data["run"].update(changes)
            self.save()

    def finish_run(self, *, keep_as_last_ok: dict[str, Any] | None = None) -> None:
        self.data["run"] = None
        if keep_as_last_ok is not None:
            self.data["last_ok"] = keep_as_last_ok
        self.save()

    @property
    def outbox(self) -> list[dict[str, Any]]:
        return self.data["outbox"]

    def push_event(self, run_id: str, event: dict[str, Any]) -> None:
        self.data["outbox"].append({"run_id": run_id, "event": event})
        del self.data["outbox"][:-MAX_OUTBOX]
        self.save()

    def pop_event(self) -> None:
        if self.data["outbox"]:
            self.data["outbox"].pop(0)
            self.save()

    def next_seq(self) -> int:
        run = self.data["run"]
        if run is None:
            return 1
        run["seq"] = int(run.get("seq", 0)) + 1
        return int(run["seq"])
