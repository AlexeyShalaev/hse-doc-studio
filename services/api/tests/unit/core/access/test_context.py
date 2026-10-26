import asyncio

from hse_doc_studio.core.access.context import current_actor, set_current_actor
from hse_doc_studio.core.access.entities import Actor


async def test__context__default_none_inherited_by_create_task_and_to_thread() -> None:
    async def in_task() -> Actor | None:
        return current_actor()

    async def run_in_fresh_context() -> tuple[Actor | None, Actor | None, Actor | None]:
        before = current_actor()
        actor = Actor.user("u1")
        set_current_actor(actor)
        from_task = await asyncio.create_task(in_task())
        from_thread = await asyncio.to_thread(current_actor)
        return before, from_task, from_thread

    before, from_task, from_thread = await asyncio.create_task(run_in_fresh_context())

    assert before is None
    assert from_task == Actor.user("u1")
    assert from_thread == Actor.user("u1")
    assert current_actor() is None


def test__context__set_none__clears_actor() -> None:
    set_current_actor(Actor.local())
    assert current_actor() == Actor.local()

    set_current_actor(None)

    assert current_actor() is None
