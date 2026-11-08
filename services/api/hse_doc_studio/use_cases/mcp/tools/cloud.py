"""Только локальная Студия: проект облачной Студии в локальную по его адресу (docs/design/local-from-cloud.md).

Доступ к серверу берётся из сохранённого входа кодом устройства, как у кнопки «Открыть» в списке проектов.
Токен из хранилища доступов не выходит: в ответе тула только адрес сервера, проект, папка и состояние.
"""

from __future__ import annotations

from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.errors import NotFoundError
from hse_doc_studio.core.git_remote.client import StudioServerError, StudioServerErrorCode
from hse_doc_studio.core.git_sync.entities import CloneResult
from hse_doc_studio.core.git_sync.errors import GitSyncError
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.use_cases.git_sync.cloud_projects import (
    CloneCloudProjectUC,
    CloudAddressError,
    CloudCloneOutcome,
    CloudServerNotConnectedError,
    parse_cloud_project_address,
)
from hse_doc_studio.use_cases.mcp.tools._base import McpTool, int_arg, json_result, optional_text

DEFAULT_WAIT_S = 60
MAX_WAIT_S = 240


def _not_connected(host: str | None) -> str:
    if host is None:
        return localized_error(
            "Локальная Студия не подключена ни к одному облачному серверу. Подключите её: на экране «Проекты» "
            "кнопка «Подключиться к серверу», вход кодом устройства. Затем повторите.",
            "The local Studio is not connected to any cloud server. Connect it: “Connect to a server” on the "
            "Projects screen, sign in with a device code. Then try again.",
        )
    return localized_error(
        f"Сервер {host} не подключён к локальной Студии. Подключите его: на экране «Проекты» кнопка "
        "«Подключиться к серверу», вход кодом устройства. Затем повторите.",
        f"The server {host} is not connected to the local Studio. Connect it: “Connect to a server” on the "
        "Projects screen, sign in with a device code. Then try again.",
    )


def _server_error(exc: StudioServerError) -> str:
    if exc.code == StudioServerErrorCode.unauthorized:
        return localized_error(
            "Сервер отклонил сохранённый вход: войдите на сервер заново и повторите.",
            "The server rejected the saved login: sign in to the server again and retry.",
        )
    return localized_error("Сервер Студии недоступен, повторите позже.", "The Studio server is unreachable.")


def _refusal(exc: Exception) -> str:
    """Текст отказа. Адрес из аргументов в него не попадает: в адресе мог оказаться токен."""
    if isinstance(exc, CloudServerNotConnectedError):
        return _not_connected(exc.host)
    if isinstance(exc, NotFoundError):
        return localized_error(
            "Проекта нет на сервере или у вас нет к нему доступа.",
            "The project is not on the server or you have no access to it.",
        )
    if isinstance(exc, StudioServerError):
        return _server_error(exc)
    if isinstance(exc, GitSyncError):
        # detail уже локализован и очищен от секретов (core/git_sync/errors.py).
        return exc.detail
    return str(exc)


def _view(outcome: CloudCloneOutcome) -> dict[str, object]:
    view: dict[str, object] = {
        "project_id": outcome.project_id,
        "server_url": outcome.server_url,
        "status": outcome.status,
    }
    operation = outcome.operation
    if operation is not None:
        view["operation_id"] = operation.id
        view["phase"] = operation.phase
        if isinstance(operation.result, CloneResult):
            view["folder"] = operation.result.folder
            view["warnings"] = [w.code for w in operation.result.warnings]
        if operation.error is not None:
            view["error"] = {"code": operation.error.code, "detail": operation.error.detail}
    view["hint"] = _hint(outcome.status)
    return view


def _hint(status: str) -> str:
    if status == "running":
        return localized_error(
            "Скачивание ещё идёт: вызовите clone_cloud_project с теми же аргументами, чтобы дождаться итога.",
            "Still downloading: call clone_cloud_project again with the same arguments to wait for the result.",
        )
    if status in {"succeeded", "already_local"}:
        return localized_error(
            "Проект в локальной Студии под тем же project_id, что на сервере.",
            "The project is in the local Studio under the same project_id as on the server.",
        )
    return localized_error("Проект не скачан.", "The project was not downloaded.")


class CloneCloudProjectTool(McpTool):
    spec = ToolSpec(
        name="clone_cloud_project",
        description=(
            "Скачать проект облачной Студии в локальную, как кнопка «Открыть» у облачного проекта. Передай url "
            "проекта (https://<сервер>/projects/<id>/) или project_id, если сервер уже подключён; server нужен, "
            "только если подключено несколько серверов. Вход на сервер берётся сохранённый, токен не нужен. "
            "Проект попадает в стандартную папку и остаётся связан с сервером. Если проект уже на компьютере, "
            "ничего не скачивается."
        ),
        parameters={
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Адрес облачного проекта, например https://host/projects/<id>/",
                },
                "project_id": {"type": "string", "description": "Идентификатор проекта на сервере (UUID)"},
                "server": {"type": "string", "description": "Адрес сервера, например https://host"},
                "wait_s": {
                    "type": "integer",
                    "default": DEFAULT_WAIT_S,
                    "description": f"Сколько секунд ждать окончания скачивания (0..{MAX_WAIT_S})",
                },
            },
        },
    )
    kind = ToolKind.exec_
    requires_project = False

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        try:
            address = parse_cloud_project_address(
                optional_text(args, "url"), optional_text(args, "project_id"), optional_text(args, "server")
            )
            wait_s = int_arg(args, "wait_s", DEFAULT_WAIT_S, lo=0, hi=MAX_WAIT_S)
            outcome = await (await self._deps.get(CloneCloudProjectUC)).execute(address, wait_s=wait_s)
        except (CloudAddressError, CloudServerNotConnectedError, NotFoundError, StudioServerError, GitSyncError) as exc:
            return ToolResult.error(_refusal(exc))
        result = json_result(_view(outcome))
        if outcome.status in {"failed", "cancelled"}:
            return ToolResult.error(result.text)
        return result
