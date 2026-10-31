"""Состояние Yjs-документа на диске: родословная переживает закрытие комнаты и перезапуск сервера.

Без неё документ, собранный заново из файла, получил бы новые идентификаторы символов, и правки клиента,
сделанные оффлайн на старой родословной, при слиянии продублировали бы текст. Файл состояния лежит в
`<data_dir>/collab/` и всегда вторичен: источник истины файл проекта, при расхождении побеждает диск.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

_log = logging.getLogger(__name__)
_EPOCH_BYTES = 16


@dataclass(frozen=True)
class SavedState:
    epoch: str
    update: bytes


class YStateStore:
    def __init__(self, root: Path) -> None:
        self._root = root

    def _file(self, project_id: UUID, path: str) -> Path:
        digest = hashlib.sha256(path.encode("utf-8")).hexdigest()[:32]
        return self._root / str(project_id) / f"{digest}.ystate"

    def load(self, project_id: UUID, path: str) -> SavedState | None:
        target = self._file(project_id, path)
        try:
            raw = target.read_bytes()
        except OSError:
            return None
        if len(raw) <= _EPOCH_BYTES:
            return None
        return SavedState(epoch=raw[:_EPOCH_BYTES].hex(), update=raw[_EPOCH_BYTES:])

    def save(self, project_id: UUID, path: str, state: SavedState) -> None:
        target = self._file(project_id, path)
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".tmp")
            tmp.write_bytes(bytes.fromhex(state.epoch) + state.update)
            os.replace(tmp, target)
        except OSError:
            # Состояние вторично: без него комната просто соберётся заново из файла.
            _log.warning("collab state not saved", exc_info=True)

    def drop(self, project_id: UUID, path: str) -> None:
        try:
            self._file(project_id, path).unlink(missing_ok=True)
        except OSError:
            _log.warning("collab state not dropped", exc_info=True)
