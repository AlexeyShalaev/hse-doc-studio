"""Действия над проектом и матрица ролей (docs/design/collaboration.md, 7.1)."""

from __future__ import annotations

from enum import StrEnum

from hse_doc_studio.core.access.entities import Role


class Action(StrEnum):
    PROJECT_VIEW = "project.view"
    OUTPUT_READ = "output.read"
    SOURCES_READ = "sources.read"
    # Чтение по пути: политика сводит его к OUTPUT_READ или SOURCES_READ (access.paths).
    FILES_READ = "files.read"
    FILES_WRITE = "files.write"
    BUILD_RUN = "build.run"
    AGENT_USE = "agent.use"
    HISTORY_WRITE = "history.write"
    # Операции, переписывающие всё рабочее дерево (восстановление, смена ветки, синхронизация, импорт).
    # В team-проекте их делает только владелец и тот, у кого есть право правки везде.
    HISTORY_REWRITE = "history.rewrite"
    SUBMISSION_READ = "submission.read"
    SUBMISSION_CREATE = "submission.create"
    SIGN = "sign"
    PROJECT_SETTINGS = "project.settings"
    TEMPLATE_MANAGE = "template.manage"
    PROJECT_DELETE = "project.delete"
    # Зарезервировано: маршрутов пока нет.
    COMMENT = "comment"
    SHARE = "share"
    PROJECT_TRANSFER = "project.transfer"
    # Видеть и решать приглашения и запросы доступа проекта: то же условие, что у SHARE, без условий персоны.
    ACCESS_MANAGE = "access.manage"


class RouteExemption(StrEnum):
    """Маршрут, который авторизует не пользователь (не Action)."""

    system_callback = "system_callback"


_READER = frozenset({Action.PROJECT_VIEW, Action.OUTPUT_READ})
_REVIEWER = _READER | {Action.SOURCES_READ, Action.COMMENT, Action.SIGN}
_EDITOR = _REVIEWER | {
    Action.FILES_WRITE,
    Action.BUILD_RUN,
    Action.AGENT_USE,
    Action.HISTORY_WRITE,
    Action.HISTORY_REWRITE,
    Action.SUBMISSION_READ,
    Action.SUBMISSION_CREATE,
    Action.SHARE,
    Action.ACCESS_MANAGE,
}
_OWNER = _EDITOR | {
    Action.PROJECT_SETTINGS,
    Action.TEMPLATE_MANAGE,
    Action.PROJECT_DELETE,
    Action.PROJECT_TRANSFER,
}

# SOURCES_READ у читателя здесь нет: его открывает Grant.show_sources.
# SHARE и ACCESS_MANAGE у редактора дополнительно требуют Grant.can_share, SIGN и
# SUBMISSION_CREATE — привязки к персоне (см. policy).
ROLE_ACTIONS: dict[Role, frozenset[Action]] = {
    Role.reader: _READER,
    Role.reviewer: frozenset(_REVIEWER),
    Role.editor: frozenset(_EDITOR),
    Role.owner: frozenset(_OWNER),
}

# Гостю недоступны агент, приглашения, git, сдача, подписи и управление проектом.
GUEST_DENIED: frozenset[Action] = frozenset(
    {
        Action.AGENT_USE,
        Action.SHARE,
        Action.ACCESS_MANAGE,
        Action.SIGN,
        Action.SUBMISSION_READ,
        Action.SUBMISSION_CREATE,
        Action.HISTORY_WRITE,
        Action.HISTORY_REWRITE,
        Action.PROJECT_SETTINGS,
        Action.TEMPLATE_MANAGE,
        Action.PROJECT_DELETE,
        Action.PROJECT_TRANSFER,
    }
)
