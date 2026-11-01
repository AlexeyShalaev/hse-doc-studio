"""Единая политика доступа: одна чистая функция для локального и серверного режима."""

from __future__ import annotations

from enum import StrEnum

from hse_doc_studio.core.access.actions import GUEST_DENIED, LINK_DENIED, ROLE_ACTIONS, Action
from hse_doc_studio.core.access.entities import Actor, Grant, ProjectAcl, Role
from hse_doc_studio.core.access.paths import classify_path, path_in_author_scope
from hse_doc_studio.core.team import split_instance_id

_ROLE_ORDER = (Role.reader, Role.reviewer, Role.editor, Role.owner)


class Decision(StrEnum):
    allow = "allow"
    # Нет членства: существование проекта скрываем, API отвечает 404.
    not_found = "not_found"
    # Участник, которому роли не хватает: API отвечает 403.
    forbidden = "forbidden"


def decide(actor: Actor, action: Action, acl: ProjectAcl | None, path: str | None = None) -> Decision:
    """Решение по действию.

    `path` значит разное по действию: путь файла (FILES_READ, FILES_WRITE) или
    id слота подписи (SIGN) либо слаг автора пакета (SUBMISSION_CREATE).
    """
    if actor.is_local:
        return Decision.allow
    grant = acl.grant_for(actor) if acl is not None else None
    if acl is None or grant is None:
        return Decision.not_found
    if _denied_by_source(actor, grant, action):
        return Decision.forbidden
    return Decision.allow if _allowed(action, acl, grant, path) else Decision.forbidden


def required_role(actor: Actor, action: Action, acl: ProjectAcl | None) -> Role | None:
    """Слабейшая роль, дающая действие, если отказ вышел из-за нехватки роли.

    Для гостя, личных условий (общий доступ, область автора) и участников без членства роли нет: отказ
    нельзя объяснить словом «нужна роль X», и клиент показывает обычный отказ.
    """
    grant = acl.grant_for(actor) if acl is not None else None
    if grant is None or _denied_by_source(actor, grant, action) or action in ROLE_ACTIONS[grant.role]:
        return None
    return next((role for role in _ROLE_ORDER if action in ROLE_ACTIONS[role]), None)


def _denied_by_source(actor: Actor, grant: Grant, action: Action) -> bool:
    """Гостю и ссылочному праву часть действий закрыта при любой роли ссылки."""
    if actor.is_guest and action in GUEST_DENIED:
        return True
    return grant.via_link and action in LINK_DENIED


def can(actor: Actor, action: Action, acl: ProjectAcl | None = None, path: str | None = None) -> bool:
    return decide(actor, action, acl, path) is Decision.allow


def _allowed(action: Action, acl: ProjectAcl, grant: Grant, path: str | None) -> bool:
    if action is Action.FILES_READ:
        action = Action.OUTPUT_READ if classify_path(path) == "output" else Action.SOURCES_READ
    if action in (Action.SOURCES_READ, Action.GIT_FETCH) and grant.role is Role.reader:
        return grant.show_sources
    if action not in ROLE_ACTIONS[grant.role]:
        return False
    return _extra_condition(action, acl, grant, path)


def _extra_condition(action: Action, acl: ProjectAcl, grant: Grant, path: str | None) -> bool:
    """Условия поверх матрицы ролей: общий доступ, привязка к персоне, область автора."""
    match action:
        case Action.SHARE | Action.ACCESS_MANAGE:
            return grant.role is Role.owner or grant.can_share
        case Action.SIGN:
            return _may_sign_slot(grant, path)
        case Action.SUBMISSION_CREATE:
            return grant.role is Role.owner or not acl.team or _is_own_package(grant, path)
        case Action.FILES_WRITE:
            return path_in_author_scope(acl, grant, path)
        case Action.HISTORY_REWRITE:
            return not acl.team or grant.role is Role.owner or grant.can_edit_all
        case _:
            return True


def _may_sign_slot(grant: Grant, slot_id: str | None) -> bool:
    """Слот `<slot>--<slug>` подписывает только привязанный к автору `<slug>`.

    Слот без суффикса не принадлежит персоне, его подписывает только владелец проекта.
    """
    owner = split_instance_id(slot_id)[1] if slot_id else None
    if owner is None:
        return grant.role is Role.owner
    return grant.persona_slug == owner


def _is_own_package(grant: Grant, author_slug: str | None) -> bool:
    """Редактор team-проекта сдаёт только пакет автора, к которому привязан.

    Без слага (гард маршрута, тело запроса ещё не прочитано) хватает привязки к персоне; слаг из запроса
    сценарий сдачи проверяет сам через IProjectAccessChecker.
    """
    return grant.persona_slug is not None and (author_slug is None or author_slug == grant.persona_slug)
