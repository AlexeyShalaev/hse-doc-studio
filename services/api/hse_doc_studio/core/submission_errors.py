"""Отказы сборки пакета сдачи: закрытый список кодов и двуязычные тексты (docs/design/signing-route.md, 12.8.1).

Ответ API `400 {detail, code, doc_id, ...}`: поля рядом с кодом (`doc`, `slot`, `who`, `step`, `total`, `hint`,
`format`) это подстановки текста `errors:code.<код>` на фронтенде, `detail` тот же текст на языке интерфейса для
MCP, агента и клиентов без каталога. `PackError` наследует `ValueError`: тулы агента и MCP, которые ловят
`ValueError`, показывают `detail` как раньше.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum

from hse_doc_studio.core.i18n import localized_error


class PackErrorCode(StrEnum):
    # Формат архива неизвестен или для него нет утилиты на этой машине.
    archive_format_unknown = "pack_archive_format_unknown"
    archive_format_unavailable = "pack_archive_format_unavailable"
    # Обязательная подпись точки не готова по плану подписей.
    slot_not_signed = "pack_slot_not_signed"
    # Документ на маршруте подписания, который ещё не дошёл до конца.
    route_in_progress = "pack_route_in_progress"
    route_paused = "pack_route_paused"
    route_returned = "pack_route_returned"
    # Зафиксированный PDF и подписи над ним не сходятся с источником подписи.
    frozen_missing = "pack_frozen_missing"
    rebuilt_after_freeze = "pack_rebuilt_after_freeze"
    version_not_frozen = "pack_version_not_frozen"
    marks_changed = "pack_marks_changed"
    signed_pdf_changed = "pack_signed_pdf_changed"
    signature_missing = "pack_signature_missing"


class PackError(ValueError):
    """Пакет собрать нельзя: код, документ и подстановки текста. Текст уже на языке интерфейса."""

    def __init__(
        self,
        code: PackErrorCode,
        message: str,
        *,
        doc_id: str | None = None,
        params: Mapping[str, str | int] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.doc_id = doc_id
        self.params: dict[str, str | int] = dict(params or {})

    def body(self) -> dict[str, object]:
        """Тело ответа API: `{detail, code, doc_id, ...подстановки}`."""
        return {"detail": str(self), "code": self.code.value, "doc_id": self.doc_id, **self.params}


def archive_format_unknown(fmt: str) -> PackError:
    return PackError(
        PackErrorCode.archive_format_unknown,
        localized_error(f"Формат архива «{fmt}» не поддерживается", f"Archive format «{fmt}» is not supported"),
        params={"format": fmt},
    )


def archive_format_unavailable(fmt: str) -> PackError:
    return PackError(
        PackErrorCode.archive_format_unavailable,
        localized_error(
            f"Формат архива «{fmt}» недоступен: на этом компьютере нет нужной утилиты. Выберите ZIP",
            f"Archive format «{fmt}» is unavailable: the tool it needs is not installed here. Choose ZIP",
        ),
        params={"format": fmt},
    )


def slot_not_signed(doc_id: str, doc: str, slot: str, hint: str) -> PackError:
    tail = f" {hint}" if hint else ""
    return PackError(
        PackErrorCode.slot_not_signed,
        localized_error(
            f"Документ «{doc}»: подпись «{slot}» ещё не готова.{tail}",
            f"Document «{doc}»: the signature «{slot}» is not ready yet.{tail}",
        ),
        doc_id=doc_id,
        params={"doc": doc, "slot": slot, "hint": hint},
    )


def route_in_progress(doc_id: str, who: str, step: int, total: int) -> PackError:
    return PackError(
        PackErrorCode.route_in_progress,
        localized_error(
            f"Маршрут подписания не завершён (шаг {step} из {total}, ждём: {who}): пакет можно собрать, "
            "когда все подпишут",
            f"The signing route is not finished (step {step} of {total}, waiting for: {who}): the package can be "
            "built once everyone has signed",
        ),
        doc_id=doc_id,
        params={"who": who, "step": step, "total": total},
    )


def route_paused(doc_id: str) -> PackError:
    return PackError(
        PackErrorCode.route_paused,
        localized_error(
            "Маршрут подписания остановлен. Причина и что делать дальше указаны в карточке «Подписание»",
            "The signing route is paused. The «Signing» card shows why and what to do next",
        ),
        doc_id=doc_id,
    )


def route_returned(doc_id: str) -> PackError:
    return PackError(
        PackErrorCode.route_returned,
        localized_error(
            "Документы вернули на доработку. Исправьте их и отправьте заново в карточке «Подписание»",
            "The documents were returned for rework. Fix them and send them again from the «Signing» card",
        ),
        doc_id=doc_id,
    )


def frozen_missing(doc_id: str, doc: str) -> PackError:
    return PackError(
        PackErrorCode.frozen_missing,
        localized_error(
            f"Нет зафиксированного PDF документа «{doc}». Зафиксируйте документ заново и подпишите его",
            f"The frozen PDF of «{doc}» is missing. Freeze the document again and sign it",
        ),
        doc_id=doc_id,
        params={"doc": doc},
    )


def rebuilt_after_freeze(doc_id: str, doc: str) -> PackError:
    return PackError(
        PackErrorCode.rebuilt_after_freeze,
        localized_error(
            f"Документ «{doc}» пересобран после фиксации PDF. Зафиксируйте его заново и подпишите новую версию",
            f"«{doc}» was rebuilt after its PDF was frozen. Freeze it again and sign the new version",
        ),
        doc_id=doc_id,
        params={"doc": doc},
    )


def version_not_frozen(doc_id: str, doc: str) -> PackError:
    return PackError(
        PackErrorCode.version_not_frozen,
        localized_error(
            f"Версия на подписи документа «{doc}» ещё не зафиксирована: маршрут подписания зафиксирует её сам, "
            "когда все согласуют",
            f"The version of «{doc}» sent for signing is not frozen yet: the signing route freezes it once everyone "
            "has approved",
        ),
        doc_id=doc_id,
        params={"doc": doc},
    )


def marks_changed(doc_id: str, doc: str) -> PackError:
    return PackError(
        PackErrorCode.marks_changed,
        localized_error(
            f"Картинки или плашки подписей документа «{doc}» изменились после фиксации PDF. Зафиксируйте его "
            "заново и подпишите новую версию",
            f"Signature images or plates of «{doc}» changed after its PDF was frozen. Freeze it again and sign the "
            "new version",
        ),
        doc_id=doc_id,
        params={"doc": doc},
    )


def signed_pdf_changed(doc_id: str, doc: str) -> PackError:
    return PackError(
        PackErrorCode.signed_pdf_changed,
        localized_error(
            f"PDF документа «{doc}» со встроенными подписями изменён вне Студии. Зафиксируйте документ заново",
            f"The PDF of «{doc}» with embedded signatures was changed outside the Studio. Freeze the document again",
        ),
        doc_id=doc_id,
        params={"doc": doc},
    )


def signature_missing(doc_id: str, doc: str, slot: str) -> PackError:
    return PackError(
        PackErrorCode.signature_missing,
        localized_error(
            f"Нет файла подписи «{slot}» документа «{doc}». Приложите подпись заново",
            f"The signature file «{slot}» of «{doc}» is missing. Attach the signature again",
        ),
        doc_id=doc_id,
        params={"doc": doc, "slot": slot},
    )
