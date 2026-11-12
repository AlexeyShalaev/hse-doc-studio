"""Эффекты расчёта маршрута: что сделать сценариям (docs/design/signing-route.md, разделы 5.4 и 6).

Расчёт их только называет. Сценарии выполняют по порядку: сначала файлы проекта под `project_lock`
(придержать, открыть, заполнить плашки, зафиксировать), затем транзакция с маршрутом, событиями и уведомлениями
(раздел 5.8). Эффекты выводятся из разницы между нужным и текущим, поэтому повторный расчёт после их выполнения
ничего не повторяет.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from hse_doc_studio.core.signing_route.entities import Notice, RequestOutcome
from hse_doc_studio.core.value_objects import SignerInfo


@dataclass(frozen=True)
class Withhold:
    """Придержать картинку слота: место на странице есть, картинки нет нигде, включая фиксацию (раздел 6.1)."""

    doc_id: str
    slot_id: str


@dataclass(frozen=True)
class Release:
    """Открыть картинку слота: участник согласовал текущую версию.

    Если у размещения включена дата, ставится дата согласования участника (раздел 6.2).
    """

    doc_id: str
    slot_id: str
    participant_id: UUID


@dataclass(frozen=True)
class Skip:
    """Записать пропуск пары в состояние подписей (`SignaturesState.skipped`, раздел 13.3).

    Раунд, время и точку берёт исполнитель у участника, чей пропуск это (`Participant.skipped`). `keep_mark` метка уже
    стоит в зафиксированном PDF, над которым есть ЭП: она остаётся в нём. Без `keep_mark` пропущенная метка нигде не
    рисуется, и документ с меткой, уже попавшей в B, маршрут фиксирует заново.
    """

    doc_id: str
    slot_id: str
    keep_mark: bool = False


@dataclass(frozen=True)
class Unskip:
    """Убрать запись о пропуске пары: участник вернулся в маршрут новым раундом или пропуска больше нет (13.3)."""

    doc_id: str
    slot_id: str


@dataclass(frozen=True)
class FillPlate:
    """Записать в плашку слота без подписанта данные известного ключа участника; только перед фиксацией (6.2)."""

    slot_id: str
    participant_id: UUID
    signer: SignerInfo


@dataclass(frozen=True)
class Freeze:
    """Зафиксировать документ: видимый слой больше никто не меняет (раздел 4.2, правило 3).

    Если у плашки включена дата, ставится дата фиксации (раздел 6.2).
    """

    doc_id: str


@dataclass(frozen=True)
class Notify:
    """Уведомить участников (`participant_ids`) и, если `sender`, отправившего маршрут.

    `outcome` только у запроса (`Notice.request`). Один человек в двух ролях получает одно уведомление: это
    решает тот, кто доставляет.
    """

    notice: Notice
    participant_ids: tuple[UUID, ...] = ()
    sender: bool = False
    outcome: RequestOutcome | None = None


type Effect = Withhold | Release | Skip | Unskip | FillPlate | Freeze | Notify
