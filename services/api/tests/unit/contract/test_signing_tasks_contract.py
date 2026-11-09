"""«На подпись» (`SigningTaskList`) против эталона фронтенда (entities/signing-route, срез W1).

Каталог `contracts/server/fixtures/SigningTaskList` появится вместе со схемами W1 в `CONTRACT_SCHEMAS`; до тех пор
модель сверяется с тем же телом здесь.
"""

from __future__ import annotations

import pytest
from hse_doc_studio.api.schemas.signing_tasks import SigningTaskList
from pydantic import ValidationError

EXAMPLE = {
    "items": [
        {
            "project": {"id": "p_01hxa1c4de", "name": "Bertie: курсовой проект"},
            "route_id": "sr_01hy2b7k9q",
            "profile": {"id": "topic-approval", "name": {"ru": "Заявка на тему КП", "en": "Course project topic"}},
            "round": 1,
            "sender": "Иванов И. И.",
            "deadline": "2026-11-15T20:59:00Z",
            "next_action": "approve_and_sign",
            "since": "2026-11-10T09:00:00Z",
        }
    ]
}


def test__signing_task_list__example_round_trips_without_losses() -> None:
    dumped = SigningTaskList.model_validate(EXAMPLE).model_dump(mode="json")

    assert dumped == EXAMPLE


@pytest.mark.parametrize(
    "change", [{"surprise": 1}, {"next_action": "wait"}, {"round": -1}], ids=["extra", "action", "round"]
)
def test__signing_task_list__rejects_extra_fields_and_foreign_values(change: dict[str, object]) -> None:
    body = {"items": [{**EXAMPLE["items"][0], **change}]}  # type: ignore[dict-item]

    with pytest.raises(ValidationError):
        SigningTaskList.model_validate(body)
