from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from hse_doc_studio.core.git_sync.entities import SharedFolderInfo
from hse_doc_studio.core.git_sync.protocols import ISharedFolderDetector


@dataclass
class DetectSharedFolderInput:
    folder: Path


class DetectSharedFolderUC:
    """Предупреждение «папка внутри синхронизируемого каталога»; никогда ничего не запрещает."""

    def __init__(self, detector: ISharedFolderDetector) -> None:
        self._detector = detector

    async def execute(self, inp: DetectSharedFolderInput) -> SharedFolderInfo | None:
        return await asyncio.to_thread(self._detector.detect, inp.folder)
