from __future__ import annotations

from pydantic import BaseModel


class FileTreeItemResponse(BaseModel):
    path: str
    size: int
    modified_at: str | None
    # User-added files are deletable; template-origin files (documents, preamble,
    # generated includes) are protected.
    deletable: bool = True
    # Directories are listed too (so empty user folders appear); inferred folders
    # in the tree don't need an explicit entry.
    is_dir: bool = False


class MoveFileRequest(BaseModel):
    src: str
    dst: str


class CreateDirRequest(BaseModel):
    path: str


class FileVersionResponse(BaseModel):
    """Версия файла на диске: по ней вкладка понимает, что его правили снаружи."""

    etag: str
    size: int
