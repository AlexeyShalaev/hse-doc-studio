from __future__ import annotations

from pathlib import Path

from hse_doc_studio.core.entities import AgentRunRecord
from hse_doc_studio.core.enums import AgentRunStatus
from hse_doc_studio.infra.persistence.chat import JsonChatRepository
from hse_doc_studio.use_cases.chat.recover_stale_chat_runs import RecoverStaleChatRunsUC
from tests.unit.use_cases.chat.conftest import _FakeIndex


class _FakeSettings:
    def get(self) -> dict[str, str]:
        return {}


async def test__execute__running_run_left_from_a_dead_process__marked_interrupted(
    tmp_path: Path, project_index: _FakeIndex, chat_repo: JsonChatRepository, running_run: AgentRunRecord
) -> None:
    uc = RecoverStaleChatRunsUC(project_index, chat_repo, _FakeSettings())  # type: ignore[arg-type]

    out = await uc.execute()

    assert out.recovered_runs == 1
    recovered = chat_repo.get_run(tmp_path, running_run.id)
    assert recovered is not None
    assert recovered.status == AgentRunStatus.interrupted
