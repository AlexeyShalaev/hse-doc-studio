from __future__ import annotations

from pydantic import BaseModel


class SyncTexBoxResponse(BaseModel):
    """A box on the page, in PDF points from the top-left."""

    page: int
    x: float
    y: float
    width: float
    height: float


class SyncTexForwardResponse(BaseModel):
    boxes: list[SyncTexBoxResponse]


class SyncTexInverseResponse(BaseModel):
    file: str
    line: int
    column: int
