from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class DocumentListItemResponse(BaseModel):
    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

    id: str
    name: dict[str, str]
    # Локализованный код определения («ТЗ», «ОТЗ», «ВКР») из пака — чип в
    # навигации; пустой словарь → фронтовый i18n-фолбэк по def_id.
    code: dict[str, str] = {}
    status: str
    chosen_variant: str | None
    last_compile_id: str | None
    last_compile_at: datetime | None
    pages: int | None
    warnings: int
    errors: int
    # Инстанс-модель (team mode): id определения пака, слаг и ФИО
    # автора-владельца (None — общий/solo-док), пути от корня проекта.
    # Фронтенд обязан использовать их вместо вывода из doc_id.
    def_id: str | None = None
    owner: str | None = None
    owner_name: str | None = None
    source_file: str | None = None
    output_file: str | None = None
    # Движок выбранного варианта (None — copy-only вариант pptx/reveal);
    # для доков без вариантов — движок из lock проекта.
    engine: str | None = None
    # Визуальный блок навигации из пака (espd/pdp/pres/…) — фронтенд рисует
    # дивайдер между соседними доками разных групп.
    group: str | None = None


class CustomFileOverrideResponse(BaseModel):
    original_filename: str
    stored_path: str
    ext: str
    uploaded_at: str
    convert_to_pdf_at_package: bool | None = None
    # Есть ли на диске sibling PDF-превью (для конвертируемых office-форматов);
    # вычисляется заново на каждый GET, не персистится.
    preview_available: bool = False


class DocumentDetailResponse(BaseModel):
    id: str
    status: str
    chosen_variant: str | None
    last_compile_id: str | None
    checks_override: dict[str, Any]
    # Резолв определения/инстанса — те же поля, что в списке: фронтенд
    # обязан использовать их вместо захардкоженных путей по doc_id.
    # Пустой словарь / None — пак не найден (или PATCH-ответ без резолва).
    name: dict[str, str] = {}
    code: dict[str, str] = {}
    source_file: str | None = None
    output_file: str | None = None
    gost_ref: str | None = None
    # Движок выбранного варианта (None — copy-only вариант pptx/reveal);
    # для доков без вариантов — движок из lock проекта.
    engine: str | None = None
    # PDF-предпросмотр не-PDF артефакта (pptx → соседний .pdf от Gotenberg);
    # None — предпросмотра нет, фронт показывает карточку скачивания.
    preview_file: str | None = None
    # mtime предпросмотра: сохранение из office-редактора переконвертирует PDF
    # без компиляции (last_compile_id не меняется) — фронт освежает вьювер по
    # этой метке.
    preview_updated_at: datetime | None = None
    # Пользовательский файл, замещающий шаблонный результат (None — обычный
    # шаблонный документ).
    custom_file: CustomFileOverrideResponse | None = None
    # True, если подписание возможно (custom_file=None, ИЛИ .pdf, ИЛИ есть
    # sibling-превью); не блокирует ничего, чисто сигнал для UI.
    signing_available: bool = True


class UpdateDocumentRequest(BaseModel):
    checks_override: dict[str, Any] | None = None
    chosen_variant: str | None = None
