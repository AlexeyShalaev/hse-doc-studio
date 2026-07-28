from __future__ import annotations

import time
from pathlib import Path


class VcsEditThrottle:
    """Per-folder throttle for edit-commits.

    `should_commit` returns True at most once per `min_interval_seconds` per
    folder. Edits that arrive inside the window are skipped — their content is
    still on disk and gets captured by the next edit/compile/manual commit, so
    nothing is lost; this just keeps a burst of saves from creating a commit
    each. App-scoped so the timestamp map is shared across requests.
    """

    def __init__(self, min_interval_seconds: float = 5.0) -> None:
        self._min = min_interval_seconds
        self._last: dict[str, float] = {}

    def should_commit(self, folder: Path) -> bool:
        key = str(folder)
        now = time.monotonic()
        last = self._last.get(key)
        if last is not None and (now - last) < self._min:
            return False
        self._last[key] = now
        return True
