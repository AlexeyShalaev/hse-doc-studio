from __future__ import annotations


def describe_run_error(exc: BaseException) -> str:
    """Человекочитаемая причина падения рана.

    Уезжает в run.error и оттуда — терминальным событием в чат: пользователь
    должен видеть «модель не поддерживает инструменты», а не «BadRequestError».
    """
    name = type(exc).__name__
    detail = str(exc).strip()
    if not detail:
        return name
    return f"{name}: {detail[:400]}"
