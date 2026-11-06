from __future__ import annotations

import asyncio

from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.runner_install import InstallError
from hse_doc_studio.use_cases.jobs.runners import RunnerRegistry


async def wait_token_used(
    registry: RunnerRegistry, actor: Actor, token_id: str, *, timeout_s: float, poll_s: float
) -> None:
    """Ждёт, пока раннер потратит выданный ему токен регистрации, то есть реально подключится к Студии."""
    waited = 0.0
    while waited < timeout_s:
        for token in await registry.list_registration_tokens(actor):
            if token.id == token_id and token.uses >= 1:
                return
        await asyncio.sleep(poll_s)
        waited += poll_s
    raise InstallError("register_timeout")
