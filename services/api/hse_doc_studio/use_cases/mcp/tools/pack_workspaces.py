"""Пространства Студии шаблонов через MCP: создать, удалить, «Обновить базу», официальные паки, каталог этой Студии.

Тулы зовут `PackWorkspaceService`, `OfficialPacks` и `PackCatalogService`, как маршруты `/pack-studio/workspaces*`,
`/pack-studio/official*` и `/pack-studio/workspaces/{id}/catalog*`, с теми же проверками и пределами.

Токены доступа git через MCP не проходят ни в одну сторону: пространство над репозиторием ссылается на уже
сохранённый доступ по `credential_id` (список без секретов даёт `pack_list_credentials`). Аргумент с токеном, паролем
или ключом отвечает отказом с подсказкой «добавьте доступ в интерфейсе». Удаление пространства и отключение от
каталога требуют `confirm: true`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, Final

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.agent.entities import ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.git_sync.protocols import IGitCredentialRepository
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.pack_catalog.errors import CatalogError
from hse_doc_studio.core.pack_studio.entities import WorkspaceKind
from hse_doc_studio.use_cases.mcp.tools._base import ArgumentError, bool_arg, optional_text, uuid_arg
from hse_doc_studio.use_cases.mcp.tools.pack_view import (
    CONFIRM_PROP,
    FORMAT_PROP,
    coded_error,
    confirmed,
    layout_arg,
    layout_result,
)
from hse_doc_studio.use_cases.mcp.tools.packs import _WORKSPACE_ID, PackTool, _schema, _workspace
from hse_doc_studio.use_cases.pack_catalog.service import PackCatalogService, SourceInput
from hse_doc_studio.use_cases.pack_studio.official import OfficialPacks
from hse_doc_studio.use_cases.pack_studio.workspaces import CreateWorkspaceInput, PackWorkspaceService

_SECRET_ARGS: Final = ("token", "access_token", "password", "secret", "private_key", "api_key", "key", "credentials")
_CATALOG_ACTIONS: Final = ("status", "check", "apply", "enable", "disable", "disconnect")


def _reject_secrets(args: Mapping[str, object]) -> None:
    """Токены и пароли в аргументах не принимаются: доступ git добавляется в интерфейсе, тул берёт его id."""
    bad = next((k for k in args if k.lower() in _SECRET_ARGS), None)
    if bad is not None:
        raise ArgumentError(
            localized_error(
                f"Аргумент {bad!r} не принимается: токены и пароли через MCP не передаются. Добавьте доступ git в "
                "интерфейсе (Настройки, Git) и передайте его id как credential_id (pack_list_credentials).",
                f"The {bad!r} argument is not accepted: tokens and passwords are never passed through MCP. Add git "
                "access in the interface (Settings, Git) and pass its id as credential_id (pack_list_credentials).",
            )
        )


def _ws_text(view: dict[str, object], head: str) -> str:
    lines = [
        head,
        f"id: {view['id']}",
        f"{view['label']}: {view['kind']}, состояние {view['state']}" + (" (идёт операция)" if view["busy"] else ""),
    ]
    if view.get("source"):
        lines.append(f"Источник: {view['source']}; база {view.get('base_branch')}")
    err = view.get("error")
    if err:
        lines.append(f"Ошибка: {err}")
    if view["state"] == "cloning":
        lines.append("Клон идёт в фоне: проверяйте pack_list_workspaces, пока состояние не станет ready.")
    return "\n".join(lines)


class PackListCredentialsTool(PackTool):
    spec = ToolSpec(
        name="pack_list_credentials",
        description=(
            "Студия шаблонов: сохранённые доступы git человека (id, вид, подпись, хост, имя пользователя, "
            "статус) для credential_id в pack_workspace_create и pack_official_open. Секретов в ответе нет; "
            "нового доступа через MCP не добавить: добавьте его в интерфейсе (Настройки, Git)."
        ),
        parameters=_schema({"format": FORMAT_PROP}),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        items = await (await self._deps.get(IGitCredentialRepository)).list()  # type: ignore[type-abstract]  # порт из контейнера
        data = [
            {
                "id": str(c.id),
                "kind": c.kind.value,
                "label": c.label,
                "host": c.host,
                "port": c.port,
                "username": c.username,
                "status": c.status.value,
            }
            for c in items
        ]
        text = "\n".join(f"{d['id']}  {d['label']} ({d['kind']}, {d['host']}, {d['status']})" for d in data)
        if not data:
            text = localized_error(
                "Сохранённых доступов нет: добавьте доступ git в интерфейсе (Настройки, Git).",
                "No saved access: add git access in the interface (Settings, Git).",
            )
        return layout_result(layout_arg(args), text, {"credentials": data})


class PackWorkspaceCreateTool(PackTool):
    spec = ToolSpec(
        name="pack_workspace_create",
        description=(
            "Студия шаблонов: создать рабочее пространство, как «Новое пространство». kind git (по умолчанию): "
            "репозиторий паков по url; доступ только ссылкой credential_id на уже сохранённый (pack_list_"
            "credentials), публичный репозиторий без него. Клон идёт в фоне: состояние cloning, затем ready "
            "(pack_list_workspaces). kind folder (только локальная Студия): папка folder на диске. packs_path "
            "папка паков внутри репозитория (по умолчанию packs), base_branch базовая ветка (по умолчанию ветка "
            "сервера по умолчанию). Токены и пароли не принимаются. Официальные паки: pack_official_open."
        ),
        parameters=_schema(
            {
                "kind": {"type": "string", "enum": ["git", "folder"], "default": "git"},
                "url": {"type": "string", "description": "Адрес репозитория (https или ssh), для kind git"},
                "credential_id": {"type": "string", "description": "Id сохранённого доступа из pack_list_credentials"},
                "base_branch": {"type": "string"},
                "packs_path": {"type": "string"},
                "folder": {"type": "string", "description": "Путь папки (kind folder, только локально)"},
                "label": {"type": "string"},
                "format": FORMAT_PROP,
            }
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        _reject_secrets(args)
        kind = optional_text(args, "kind") or "git"
        if kind not in {"git", "folder"}:
            raise ArgumentError(localized_error("kind: git или folder", "kind: git or folder"))
        credential = optional_text(args, "credential_id")
        view = await (await self._deps.get(PackWorkspaceService)).create(
            actor,
            CreateWorkspaceInput(
                kind=WorkspaceKind(kind),
                label=optional_text(args, "label"),
                url=optional_text(args, "url"),
                credential_id=uuid_arg(args, "credential_id") if credential else None,
                base_branch=optional_text(args, "base_branch"),
                folder=optional_text(args, "folder"),
                packs_path=optional_text(args, "packs_path"),
            ),
        )
        data = _workspace(view, await self._deps.get(OfficialPacks))
        return layout_result(layout_arg(args), _ws_text(data, "Пространство создано."), data)


class PackWorkspaceRefreshTool(PackTool):
    spec = ToolSpec(
        name="pack_workspace_refresh",
        description=(
            "Студия шаблонов: «Обновить базу»: выборка базовой ветки пространства над git и пересчёт выпущенных "
            "версий; у неудачного или прерванного клона клон заново. Идёт в фоне: проверяйте "
            "pack_list_workspaces (busy). Ваши правки и ветка не меняются: влить базу в ветку делает "
            "pack_git_merge_base."
        ),
        parameters=_schema({"workspace_id": _WORKSPACE_ID, "format": FORMAT_PROP}, ("workspace_id",)),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        view = await (await self._deps.get(PackWorkspaceService)).refresh(actor, uuid_arg(args, "workspace_id"))
        data = _workspace(view, await self._deps.get(OfficialPacks))
        return layout_result(layout_arg(args), _ws_text(data, "Обновление базы запущено."), data)


class PackWorkspaceDeleteTool(PackTool):
    spec = ToolSpec(
        name="pack_workspace_delete",
        description=(
            "Студия шаблонов: удалить рабочее пространство. ДЕСТРУКТИВНО для пространства над git: его копия, "
            "ветки и несохранённые правки на этой Студии пропадают (отправленное на сервер остаётся). Папку "
            "пользователя Студия не трогает никогда: забывается только запись. Без confirm: true только "
            "описывает последствия."
        ),
        parameters=_schema(
            {"workspace_id": _WORKSPACE_ID, "confirm": CONFIRM_PROP, "format": FORMAT_PROP}, ("workspace_id",)
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        workspace_id = uuid_arg(args, "workspace_id")
        service = await self._deps.get(PackWorkspaceService)
        view = await service.get(actor, workspace_id)
        ws = view.workspace
        git = ws.kind is WorkspaceKind.git
        if not confirmed(args):
            data: dict[str, Any] = {
                "confirm_required": True,
                "workspace": {"id": str(ws.id), "label": ws.label, "kind": ws.kind.value},
                "loses_local_copy": git,
                "hint": localized_error(
                    "Ничего не удалено. Покажите человеку, что пространство "
                    + (
                        "со всеми локальными ветками и несохранёнными правками "
                        if git
                        else "(только запись, папка остаётся) "
                    )
                    + "будет удалено, и вызовите с confirm: true.",
                    "Nothing was deleted. Show the person that the workspace "
                    + ("with all local branches and unsaved edits " if git else "(the record only, the folder stays) ")
                    + "will be deleted, and call with confirm: true.",
                ),
            }
            return layout_result(layout_arg(args), f"{ws.label}: {data['hint']}", data)
        await service.delete(actor, workspace_id)
        data = {"deleted": True, "id": str(ws.id), "label": ws.label}
        return layout_result(layout_arg(args), f"Пространство «{ws.label}» удалено.", data)


class PackOfficialTool(PackTool):
    spec = ToolSpec(
        name="pack_official",
        description=(
            "Студия шаблонов: официальные паки этой установки: адрес репозитория, папка паков, базовая ветка, "
            "лицензия вклада и ваше уже созданное официальное пространство (workspace_id). repo null: "
            "официальных паков на установке нет. Открыть пространство: pack_official_open."
        ),
        parameters=_schema({"format": FORMAT_PROP}),
    )
    kind = ToolKind.read

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        info = await (await self._deps.get(OfficialPacks)).info(actor)
        repo = info.repo
        data: dict[str, Any] = {
            "repo": None
            if repo is None
            else {
                "url": repo.url,
                "packs_path": repo.packs_path,
                "base_branch": repo.base_branch,
                "license": repo.license,
                "license_url": repo.license_url,
                "contributing_url": repo.contributing_url,
            },
            "workspace_id": None if info.workspace_id is None else str(info.workspace_id),
        }
        if repo is None:
            text = localized_error("Официальных паков на установке нет.", "This installation has no official packs.")
        else:
            text = f"Официальный репозиторий: {repo.url} ({repo.base_branch}, лицензия {repo.license})\n" + (
                f"Ваше пространство: {info.workspace_id}"
                if info.workspace_id
                else "Пространства ещё нет: pack_official_open с credential_id."
            )
        return layout_result(layout_arg(args), text, data)


class PackOfficialOpenTool(PackTool):
    spec = ToolSpec(
        name="pack_official_open",
        description=(
            "Студия шаблонов: открыть пространство над официальным репозиторием паков вашим сохранённым доступом "
            "(credential_id из pack_list_credentials): уже созданное (created false) или новое (клон в фоне). "
            "Предложить изменения оттуда можно после согласия с лицензией (pack_propose с accept_license)."
        ),
        parameters=_schema({"credential_id": {"type": "string"}, "format": FORMAT_PROP}, ("credential_id",)),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:
        _reject_secrets(args)
        official = await self._deps.get(OfficialPacks)
        view, created = await official.open(actor, uuid_arg(args, "credential_id"))
        data = {**_workspace(view, official), "created": created}
        return layout_result(
            layout_arg(args), _ws_text(data, "Пространство создано." if created else "Уже есть."), data
        )


def _catalog_data(view: Any) -> dict[str, Any]:
    src = view.source
    return {
        "id": str(src.id),
        "label": src.label,
        "enabled": src.enabled,
        "replace_builtin": src.replace_builtin,
        "applied_revision": src.applied_revision,
        "checked_revision": src.checked_revision,
        "check_ok": src.check_ok,
        "pending_versions": src.pending_versions,
        "error": None if src.error is None else {"code": src.error.code, "detail": src.error.detail},
        "packs": [
            {"id": p.id, "listed": p.listed, "versions": [f"{v.template}/{v.version}" for v in p.versions]}
            for p in getattr(view, "packs", ())
        ],
    }


class PackCatalogTool(PackTool):
    spec = ToolSpec(
        name="pack_catalog",
        description=(
            "Студия шаблонов: «Подключить к каталогу этой Студии» (только локально и только пространство-папка): "
            "выпущенные версии папки появляются в мастере проектов. action: status (по умолчанию), check "
            "(проверка и план: blockers, новые версии; первая проверка подключает папку), apply (применить "
            "проверенную ревизию revision из check: ВИДНО ВСЕМ ПРОЕКТАМ этой Студии, нужен confirm: true), enable "
            "и disable (показать и спрятать паки), disconnect (отключить и убрать из каталога, нужен confirm: true)."
        ),
        parameters=_schema(
            {
                "workspace_id": _WORKSPACE_ID,
                "action": {"type": "string", "enum": list(_CATALOG_ACTIONS), "default": "status"},
                "revision": {"type": "string", "description": "Ревизия из check (для apply)"},
                "replace_builtin": {"type": "boolean", "default": False, "description": "Паки папки заменяют вшитые"},
                "confirm": CONFIRM_PROP,
                "format": FORMAT_PROP,
            },
            ("workspace_id",),
        ),
    )
    kind = ToolKind.write

    async def run(self, actor: Actor, args: dict[str, object]) -> ToolResult:  # noqa: C901, PLR0911, PLR0912, PLR0915
        action = optional_text(args, "action") or "status"
        if action not in _CATALOG_ACTIONS:
            raise ArgumentError(
                localized_error(f"action: {', '.join(_CATALOG_ACTIONS)}", f"action: {', '.join(_CATALOG_ACTIONS)}")
            )
        workspace_id = uuid_arg(args, "workspace_id")
        layout = layout_arg(args)
        catalog = await self._deps.get(PackCatalogService)
        workspaces = await self._deps.get(PackWorkspaceService)
        try:
            ws = (await workspaces.get(actor, workspace_id)).workspace
            if ws.kind is not WorkspaceKind.folder:
                return coded_error(
                    "source_kind_not_allowed",
                    "В каталог подключается только пространство-папка.",
                    "Only a folder workspace can be connected.",
                )
            source = await catalog.find_folder_source(actor, workspace_id)
            if action == "status":
                if source is None:
                    return layout_result(layout, "Папка не подключена к каталогу.", {"source": None})
                data = _catalog_data(await catalog.source(actor, source.id))
                return layout_result(
                    layout,
                    f"Источник {data['label']}: {'включён' if data['enabled'] else 'выключен'}, "
                    f"применена {data['applied_revision']}",
                    {"source": data},
                )
            if action == "check":
                if source is None:
                    source = await catalog.add_folder(
                        actor, folder=ws.folder or "", packs_path=ws.packs_path, label=ws.label, workspace_id=ws.id
                    )
                replace = bool_arg(args, "replace_builtin", False)
                if source.replace_builtin != replace:
                    source = await catalog.update(actor, source.id, SourceInput(replace_builtin=replace))
                checked = await catalog.check(actor, source.id)
                plan = checked.plan
                data = {
                    "revision": plan.revision,
                    "ok": plan.ok,
                    "blockers": [b.value for b in plan.blockers],
                    "new_count": plan.new_count,
                    "problems": list(plan.problems)[:20],
                    "packs": [
                        {
                            "id": p.id,
                            "conflict": None if p.conflict is None else p.conflict.value,
                            "versions": [
                                {
                                    "version": f"{v.template}/{v.version}",
                                    "verdict": v.verdict.value,
                                    "errors": list(v.errors)[:5],
                                }
                                for v in p.versions
                            ],
                        }
                        for p in plan.packs
                    ],
                }
                verdict = "можно применять" if plan.ok else "блокеры: " + ", ".join(b.value for b in plan.blockers)
                text = f"Проверка: ревизия {plan.revision}, {verdict}; новых версий {plan.new_count}"
                return layout_result(layout, text, data)
            if source is None:
                return coded_error(
                    "source_not_found",
                    "Сначала pack_catalog с action: check.",
                    "Call pack_catalog with action: check first.",
                )
            if action in {"apply", "disconnect"} and not confirmed(args):
                data = {
                    "confirm_required": True,
                    "hint": localized_error(
                        "Ничего не изменено. Действие меняет каталог шаблонов всей Студии: покажите это человеку и "
                        "повторите с confirm: true.",
                        "Nothing was changed. The action changes the template catalog of the whole Studio: show it "
                        "to the person and repeat with confirm: true.",
                    ),
                }
                return layout_result(layout, str(data["hint"]), data)
            if action == "apply":
                revision = optional_text(args, "revision")
                if revision is None:
                    raise ArgumentError(localized_error("укажите revision из check", "specify the revision from check"))
                if not source.enabled:
                    source = await catalog.set_enabled(actor, source.id, True)
                applied = await catalog.apply(actor, source.id, revision)
                data = {
                    "revision": applied.plan.revision,
                    "added": list(applied.added),
                    "catalog_revision": applied.catalog_revision,
                }
                return layout_result(layout, f"Применено, добавлено версий: {len(applied.added)}", data)
            if action == "disconnect":
                await catalog.remove(actor, source.id)
                return layout_result(layout, "Папка отключена от каталога.", {"disconnected": True})
            enabled = action == "enable"
            await catalog.set_enabled(actor, source.id, enabled)
            return layout_result(layout, "Источник включён." if enabled else "Источник выключен.", {"enabled": enabled})
        except CatalogError as exc:
            return ToolResult.error(json.dumps({"code": exc.code.value, "detail": exc.detail}, ensure_ascii=False))


__all__ = [
    "PackCatalogTool",
    "PackListCredentialsTool",
    "PackOfficialOpenTool",
    "PackOfficialTool",
    "PackWorkspaceCreateTool",
    "PackWorkspaceDeleteTool",
    "PackWorkspaceRefreshTool",
]
