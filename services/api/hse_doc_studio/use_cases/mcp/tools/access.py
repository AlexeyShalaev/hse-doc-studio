"""Доступ к проекту на сервере: кто в проекте, приглашение по почте, отзыв приглашения и снятие участника.

Те же сценарии, что у панели «Доступ» в вебе (`api/routers/v1/project_members.py`, `project_invitations.py`), и те
же права из таблицы каталога, что у маршрутов: список видит любой участник (PROJECT_VIEW), приглашения ведёт
владелец или редактор с правом делиться (ACCESS_MANAGE), участника снимает владелец (PROJECT_SETTINGS). Сценарии
сами пишут аудит (`project.invitation.create`, `project.invitation.revoke`, `project.member.remove`) и проверяют,
что выдаваемая роль не выше своей. Локально доступа как понятия нет: в каталоге тулы только серверные.

Ссылка приглашения несёт одноразовый секрет. Как и окно приглашения в вебе, тул отдаёт её, только когда письмо не
ушло (`delivery: manual`) и переслать её должен сам приглашающий; токен отдельно и его хеш в ответ не попадают.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from hse_doc_studio.core.access.actions import Action
from hse_doc_studio.core.access.checker import IProjectAccessChecker, ProjectForbiddenError
from hse_doc_studio.core.access.context import require_actor
from hse_doc_studio.core.access.entities import Role
from hse_doc_studio.core.access.repositories import AccessQuery, ProjectAccessRow
from hse_doc_studio.core.agent.entities import AgentToolContext, ToolResult, ToolSpec
from hse_doc_studio.core.enums import ToolKind
from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.identity.session_policy import utc_now
from hse_doc_studio.core.invitations.entities import (
    GRANTABLE_ROLES,
    MAX_INVITATION_DAYS,
    MESSAGE_MAX,
    MIN_INVITATION_DAYS,
    InvitationView,
    MemberTerms,
)
from hse_doc_studio.core.listing import Window
from hse_doc_studio.use_cases.mcp.tools._base import (
    ArgumentError,
    McpTool,
    bool_arg,
    int_arg,
    json_result,
    optional_text,
    project_schema,
    text_arg,
)
from hse_doc_studio.use_cases.projects.access_panel import ListProjectAccessUC
from hse_doc_studio.use_cases.projects.invitations import (
    CreateInvitationUC,
    InvitationCreated,
    ListProjectInvitationsUC,
    NewInvitation,
    RevokeInvitationUC,
)
from hse_doc_studio.use_cases.projects.members import RemoveProjectMemberUC

_ROLE_NAMES = [r.value for r in GRANTABLE_ROLES]
_PAGE = 50
_MAX_PAGE = 100
_EMAIL_MAX = 320
_PERSONA_MAX = 64
_ID_MAX = 64
_MEMBER_KINDS = ("user", "group")


def _row_view(row: ProjectAccessRow) -> dict[str, object]:
    view: dict[str, object] = {
        "kind": row.subject_kind,
        "id": row.subject_id,
        "name": row.name,
        "detail": row.detail,
        "role": row.role.value,
        "locked": row.locked,
    }
    if row.subject_kind in _MEMBER_KINDS and not row.locked:
        view["member"] = f"{row.subject_kind}:{row.subject_id}"
    return view


def _invitation_view(view: InvitationView, now: datetime) -> dict[str, object]:
    """Как строка «Ожидают» в вебе (`api/invitation_views.py`): приглашающему видна введённая им почта."""
    inv = view.invitation
    return {
        "invitation_id": inv.id,
        "email": inv.invitee_email,
        "invitee_name": view.invitee_name if inv.invitee_email is None else None,
        "role": inv.terms.role.value,
        "persona": inv.terms.persona,
        "can_share": inv.terms.can_share,
        "show_sources": inv.terms.show_sources,
        "can_edit_all": inv.terms.can_edit_all,
        "status": inv.effective_status(now).value,
        "invited_by": view.inviter_name,
        "created_at": inv.created_at,
        "expires_at": inv.expires_at,
        "sent_count": inv.sent_count,
    }


class ListProjectAccessTool(McpTool):
    spec = ToolSpec(
        name="list_project_access",
        description=(
            "Кто имеет доступ к проекту, как панель «Доступ»: владелец, люди и группы с ролями (reader, reviewer, "
            "editor, owner). Тем, кто ведёт приглашения (владелец или редактор с правом делиться), ещё и ожидающие "
            "приглашения с invitation_id. Поле member строки нужно для remove_project_member. Пример: "
            '{"project_id": "<uuid>", "q": "петров"}.'
        ),
        parameters=project_schema(
            {
                "q": {"type": "string", "description": "Поиск по имени или почте"},
                "limit": {"type": "integer", "default": _PAGE, "description": f"Сколько строк (1..{_MAX_PAGE})"},
                "offset": {"type": "integer", "default": 0, "description": "Сколько строк пропустить"},
            }
        ),
    )
    kind = ToolKind.read

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        window = Window(int_arg(args, "limit", _PAGE, lo=1, hi=_MAX_PAGE), int_arg(args, "offset", 0, lo=0, hi=10**6))
        query = AccessQuery(q=optional_text(args, "q"), window=window)
        found = await (await self._deps.get(ListProjectAccessUC)).execute(ctx.project_id, query)
        result: dict[str, object] = {
            "members": [_row_view(r) for r in found.items],
            "total": found.total,
            "invitations": await self._invitations(ctx),
        }
        return json_result(result)

    async def _invitations(self, ctx: AgentToolContext) -> list[dict[str, object]] | None:
        """Ожидающие приглашения видит только тот, кому их список открывает маршрут (ACCESS_MANAGE)."""
        checker = await self._deps.get(IProjectAccessChecker)  # type: ignore[type-abstract]  # порт из контейнера
        try:
            await checker.require(ctx.project_id, Action.ACCESS_MANAGE)
        except ProjectForbiddenError:
            return None
        uc = await self._deps.get(ListProjectInvitationsUC)
        found = await uc.execute(ctx.project_id, pending_only=True, window=Window(_MAX_PAGE, 0))
        now = utc_now()
        return [_invitation_view(v, now) for v in found.items]


def _role(args: Mapping[str, object]) -> Role:
    raw = text_arg(args, "role", required=False) or Role.reviewer.value
    if raw not in _ROLE_NAMES:
        raise ArgumentError(
            localized_error(f"role: одно из {', '.join(_ROLE_NAMES)}", f"role: one of {', '.join(_ROLE_NAMES)}")
        )
    return Role(raw)


def _limited(args: Mapping[str, object], key: str, limit: int) -> str | None:
    value = optional_text(args, key)
    if value is not None and len(value) > limit:
        raise ArgumentError(
            localized_error(f"{key}: не длиннее {limit} символов", f"{key}: at most {limit} characters")
        )
    return value


def _required(args: Mapping[str, object], key: str, limit: int) -> str:
    text_arg(args, key)
    return str(_limited(args, key, limit))


def _days(args: Mapping[str, object]) -> int:
    raw = args.get("expires_in_days", 7)
    if isinstance(raw, bool) or not isinstance(raw, int) or not MIN_INVITATION_DAYS <= raw <= MAX_INVITATION_DAYS:
        raise ArgumentError(
            localized_error(
                f"expires_in_days: целое от {MIN_INVITATION_DAYS} до {MAX_INVITATION_DAYS}",
                f"expires_in_days: an integer from {MIN_INVITATION_DAYS} to {MAX_INVITATION_DAYS}",
            )
        )
    return raw


def invitation_terms(args: Mapping[str, object]) -> MemberTerms:
    """Флаги как в окне приглашения: делиться только редактору, исходники скрываются только у читателя."""
    role = _role(args)
    return MemberTerms(
        role=role,
        persona=_limited(args, "persona", _PERSONA_MAX),
        can_share=role is Role.editor and bool_arg(args, "can_share", False),
        show_sources=bool_arg(args, "show_sources", True) if role is Role.reader else True,
        can_edit_all=role is Role.editor and bool_arg(args, "can_edit_all", False),
    )


def _delivery_hint(created: InvitationCreated) -> str:
    if created.delivery == "manual":
        return localized_error(
            "Почта не настроена: отправьте ссылку человеку сами. Ссылка одноразовая, не публикуйте её.",
            "Email is not configured: send the link to the person yourself. The link is single-use, do not publish it.",
        )
    if created.delivery == "email":
        return localized_error("Приглашение отправлено на почту.", "The invitation was sent by email.")
    return localized_error("Приглашение во «Входящих» у человека.", "The invitation is in the person's inbox.")


class InviteToProjectTool(McpTool):
    spec = ToolSpec(
        name="invite_to_project",
        description=(
            "Пригласить человека в проект по e-mail, как кнопка «Пригласить» в панели «Доступ». Доступ появится "
            "после того, как он примет приглашение. Роль: reader, reviewer или editor, не выше своей. persona "
            "привязывает к роли в проекте: supervisor, co_supervisor, academic_supervisor или slug автора из "
            "get_project. Если почта на сервере не настроена, в ответе link: её нужно переслать самому. Пример "
            'руководителя-рецензента: {"project_id": "<uuid>", "email": "petrov@hse.ru", "role": "reviewer", '
            '"persona": "supervisor"}.'
        ),
        parameters=project_schema(
            {
                "email": {"type": "string", "description": "Почта приглашаемого"},
                "role": {
                    "type": "string",
                    "enum": _ROLE_NAMES,
                    "default": Role.reviewer.value,
                    "description": "reader: читатель, reviewer: рецензент, editor: редактор",
                },
                "persona": {
                    "type": "string",
                    "description": "supervisor, co_supervisor, academic_supervisor или slug автора",
                },
                "can_share": {"type": "boolean", "default": False, "description": "Редактор может приглашать других"},
                "show_sources": {
                    "type": "boolean",
                    "default": True,
                    "description": "Читатель видит исходники (у остальных ролей всегда)",
                },
                "can_edit_all": {
                    "type": "boolean",
                    "default": False,
                    "description": "Редактор командного проекта правит части всех авторов",
                },
                "message": {"type": "string", "description": "Сообщение в приглашении"},
                "expires_in_days": {
                    "type": "integer",
                    "default": 7,
                    "description": f"Срок приглашения в днях ({MIN_INVITATION_DAYS}..{MAX_INVITATION_DAYS})",
                },
            },
            ("email",),
        ),
    )
    kind = ToolKind.write

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        email = _required(args, "email", _EMAIL_MAX)
        new = NewInvitation(
            terms=invitation_terms(args),
            email=email,
            message=_limited(args, "message", MESSAGE_MAX),
            expires_in_days=_days(args),
        )
        created = await (await self._deps.get(CreateInvitationUC)).execute(require_actor(), ctx.project_id, new)
        result: dict[str, object] = {
            "invitation": _invitation_view(created.view, utc_now()),
            "delivery": created.delivery,
            "hint": _delivery_hint(created),
        }
        if created.delivery == "manual" and created.link:
            result["link"] = created.link
        return json_result(result)


class RevokeProjectInvitationTool(McpTool):
    spec = ToolSpec(
        name="revoke_project_invitation",
        description=(
            "Отозвать ожидающее приглашение в проект, как «Отозвать» в разделе «Ожидают»: ссылка из письма "
            'перестаёт работать. invitation_id из list_project_access. Пример: {"project_id": "<uuid>", '
            '"invitation_id": "inv_..."}.'
        ),
        parameters=project_schema(
            {"invitation_id": {"type": "string", "description": "id приглашения из list_project_access"}},
            ("invitation_id",),
        ),
    )
    kind = ToolKind.write

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        invitation_id = _required(args, "invitation_id", _ID_MAX)
        await (await self._deps.get(RevokeInvitationUC)).execute(require_actor(), ctx.project_id, invitation_id)
        return json_result({"revoked": invitation_id})


def member_principal(raw: str) -> tuple[str, str]:
    """`user:<id>` или `group:<id>`, как в пути маршрута снятия участника."""
    kind, _, principal_id = raw.partition(":")
    if kind not in _MEMBER_KINDS or not principal_id.strip():
        raise ArgumentError(
            localized_error(
                "member: user:<id> или group:<id> из list_project_access",
                "member: user:<id> or group:<id> from list_project_access",
            )
        )
    return kind, principal_id.strip()


class RemoveProjectMemberTool(McpTool):
    spec = ToolSpec(
        name="remove_project_member",
        description=(
            "Снять с человека или группы доступ к проекту, как «Убрать» в панели «Доступ». Владельца снять нельзя. "
            'member из list_project_access. Пример: {"project_id": "<uuid>", "member": "user:<id>"}.'
        ),
        parameters=project_schema(
            {"member": {"type": "string", "description": "user:<id> или group:<id> из list_project_access"}},
            ("member",),
        ),
    )
    kind = ToolKind.write

    async def handle(self, ctx: AgentToolContext, args: dict[str, object]) -> ToolResult:
        kind, principal_id = member_principal(text_arg(args, "member"))
        await (await self._deps.get(RemoveProjectMemberUC)).execute(require_actor(), ctx.project_id, kind, principal_id)
        return json_result({"removed": f"{kind}:{principal_id}"})
