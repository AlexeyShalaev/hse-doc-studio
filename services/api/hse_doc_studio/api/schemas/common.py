from __future__ import annotations

from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str
    code: str


class LockResponse(BaseModel):
    pack_id: str
    template_id: str
    version: str
    engine: str


class AuthorSchema(BaseModel):
    name: str
    group: str | None = None
    email: str | None = None
    # Team mode: слаг папки автора, личная тема работы, «ведём ли комплект» и
    # авторские меты (пак-поля scope=author). В solo-проектах slug/topic=None.
    slug: str | None = None
    topic: str | None = None
    managed: bool = True
    meta: dict[str, object] = {}


class PersonSchema(BaseModel):
    name: str
    role: str
    title: str | None = None
    degree: str | None = None
