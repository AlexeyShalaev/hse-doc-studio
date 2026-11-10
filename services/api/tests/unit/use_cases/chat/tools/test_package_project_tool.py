"""package_project: предупреждения пакета без пропуска (docs/design/signing-route.md, 12.8 и 12.10)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

from hse_doc_studio.core.agent.entities import AgentToolContext
from hse_doc_studio.core.enums import EditFormat
from hse_doc_studio.use_cases.chat.tools.package_project import PackageProjectTool
from hse_doc_studio.use_cases.submission.pack_planner import NOTICE_CHANGED_AFTER_SENT, PackNotice

_NOTICE = PackNotice(
    code=NOTICE_CHANGED_AFTER_SENT,
    doc_id="topic",
    arcname="Заявление.pdf",
    message="Документ «Заявление» изменён после отправки на подпись: в пакет попала версия на подписи от 10.11.2026",
    pinned_at="2026-11-10T14:32:00+00:00",
    route_id=str(uuid4()),
    round=1,
    source_sha256="a" * 64,
    working_sha256="b" * 64,
)


class _Profiles:
    async def execute(self, inp: Any) -> Any:
        return SimpleNamespace(profiles=[SimpleNamespace(id="topic-approval", name={"ru": "Тема"})])


class _Create:
    def __init__(self, notices: tuple[PackNotice, ...]) -> None:
        self._notices = notices

    async def execute(self, inp: Any) -> Any:
        record = SimpleNamespace(output_path=Path("/tmp/pack.zip"))  # noqa: S108 — только имя файла
        return SimpleNamespace(submission=record, notices=self._notices)


def _tool(notices: tuple[PackNotice, ...]) -> PackageProjectTool:
    return PackageProjectTool(_Create(notices), _Profiles())  # type: ignore[arg-type]


def _ctx() -> AgentToolContext:
    return AgentToolContext(project_id=uuid4(), model="m", edit_format=EditFormat.search_replace)


async def test__package_project__changed_after_sent__warning_and_who_sends_the_new_version() -> None:
    result = await _tool((_NOTICE,)).handle(_ctx(), {})

    assert result.is_error is False
    head, *lines = result.text.split("\n")
    assert head == "комплект собран по профилю «topic-approval»: архив pack.zip"
    assert lines[0] == "Предупреждения:"
    assert lines[1].startswith("- changed_after_sent (topic): Документ «Заявление» изменён после отправки")
    assert "«Отправить новую версию»" in lines[2]


async def test__package_project__no_warnings__one_line() -> None:
    result = await _tool(()).handle(_ctx(), {})

    assert result.text == "комплект собран по профилю «topic-approval»: архив pack.zip"
