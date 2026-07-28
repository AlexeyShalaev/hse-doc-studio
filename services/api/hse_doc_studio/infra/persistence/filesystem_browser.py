from __future__ import annotations

from pathlib import Path

import structlog

from hse_doc_studio.core.repositories import BrowseEntry

logger = structlog.get_logger()


class LocalFilesystemBrowser:
    """Lists subdirectories and files of an arbitrary local path."""

    def browse(self, path: Path) -> tuple[Path | None, list[BrowseEntry]]:
        if not path.exists():
            raise FileNotFoundError(f"Path does not exist: '{path}'")
        if not path.is_dir():
            raise NotADirectoryError(f"Not a directory: '{path}'")

        entries: list[BrowseEntry] = []
        # PermissionError from iterdir() propagates to the caller (the router
        # maps it to 403); per-entry stat failures below are skipped instead.
        for child in path.iterdir():
            try:
                is_dir = child.is_dir()
            except OSError as exc:
                logger.warning("could not stat entry", path=str(child), exc=str(exc))
                continue
            entries.append(
                BrowseEntry(
                    name=child.name,
                    path=child,
                    is_dir=is_dir,
                    is_hidden=child.name.startswith("."),
                )
            )

        entries.sort(key=lambda e: (not e.is_dir, e.name.casefold()))

        parent = path.parent if path.parent != path else None
        return parent, entries
