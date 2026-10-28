"""Чтение и отмена длительных операций синхронизации по идентификатору."""

from __future__ import annotations

from hse_doc_studio.core.access.context import current_actor
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import GitOperation
from hse_doc_studio.core.git_sync.protocols import IGitOperationRegistry
from hse_doc_studio.core.i18n import localized_error


def _not_found() -> NotFoundError:
    return NotFoundError(
        localized_error("Операция не найдена или уже забыта", "Operation not found or already forgotten")
    )


def _visible(operation: GitOperation | None) -> GitOperation:
    """Операцию видит только начавший её: реестр общий на процесс, а идентификатор не секрет.

    Чужая операция отвечает так же, как несуществующая. У локального режима владельца нет.
    """
    if operation is None:
        raise _not_found()
    if operation.owner is not None:
        actor = current_actor()
        if actor is None or actor.key != operation.owner:
            raise _not_found()
    return operation


class GetOperationUC:
    def __init__(self, operations: IGitOperationRegistry) -> None:
        self._operations = operations

    async def execute(self, operation_id: str) -> GitOperation:
        return _visible(self._operations.get(operation_id))


class CancelOperationUC:
    def __init__(self, operations: IGitOperationRegistry) -> None:
        self._operations = operations

    async def execute(self, operation_id: str) -> GitOperation:
        _visible(self._operations.get(operation_id))
        return _visible(self._operations.cancel(operation_id))
