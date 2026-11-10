"""Ошибки работы с открепленными подписями: общие для infra и use_cases."""

from __future__ import annotations


class GpgUnavailableError(RuntimeError):
    """The gpg binary is not installed."""


class GpgError(ValueError):
    """gpg refused the operation (bad key, wrong passphrase, ...)."""


class CmsParseError(ValueError):
    """The blob is not a CMS SignedData structure."""


class UnknownSignatureFormatError(ValueError):
    """The file is neither an OpenPGP nor a CMS signature."""


class StampingError(ValueError):
    """Видимый слой (картинка подписи, плашка, дата) не нанесен на PDF: штампованный файл не пишется.

    Без метки фиксация и печатная копия юридически неверны, а поверх фиксации ставятся электронные подписи,
    поэтому штамповщик не продолжает молча. Наследует `ValueError`: роутеры отвечают 400 с текстом, задача
    пакета сдачи отдает его как ошибку входа, MCP как отказ с этим текстом. Текст уже на языке интерфейса.

    `page` страница метки (с 1), `slot_id` слот, если он известен, `cause` исходная ошибка для журнала.
    """

    code = "stamping_failed"

    def __init__(self, message: str, *, page: int | None = None, slot_id: str | None = None, cause: str = "") -> None:
        super().__init__(message)
        self.page = page
        self.slot_id = slot_id
        self.cause = cause


class StampImageError(StampingError):
    """Картинка подписи слота не читается (битый или не PNG-файл): ее нужно загрузить заново."""

    code = "stamp_image_unreadable"


class StampPageMissingError(StampingError):
    """Место подписи стоит на странице, которой нет в собранном PDF: место нужно передвинуть."""

    code = "stamp_page_missing"
