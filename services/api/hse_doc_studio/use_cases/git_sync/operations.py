"""Чтение и отмена длительных операций синхронизации по идентификатору."""

from __future__ import annotations

from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_sync.entities import GitOperation
from hse_doc_studio.core.git_sync.protocols import IGitOperationRegistry
from hse_doc_studio.core.i18n import localized_error


def _not_found() -> NotFoundError:
    return NotFoundError(
        localized_error("Операция не найдена или уже забыта", "Operation not found or already forgotten")
    )


class GetOperationUC:
    def __init__(self, operations: IGitOperationRegistry) -> None:
        self._operations = operations

    async def execute(self, operation_id: str) -> GitOperation:
        operation = self._operations.get(operation_id)
        if operation is None:
            raise _not_found()
        return operation


class CancelOperationUC:
    def __init__(self, operations: IGitOperationRegistry) -> None:
        self._operations = operations

    async def execute(self, operation_id: str) -> GitOperation:
        operation = self._operations.cancel(operation_id)
        if operation is None:
            raise _not_found()
        return operation
