from __future__ import annotations

from typing import Protocol

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.update.entities import ReleaseEntry, UpdateCheckState, UpdateFeedProbe


class IUpdateFeedGateway(Protocol):
    """Read-only access to the release feed that says which version is newest.

    Implementations MUST never raise: a disabled feed, a network failure, a rate
    limit or a malformed answer all come back as a probe with `checked=False` and a
    human-readable `reason`. Checking for updates is never a reason to fail the
    request that asked.
    """

    async def probe(self) -> UpdateFeedProbe: ...


class IUpdateCheckRepository(Protocol):
    """Persisted last-known feed answer (data_dir/update-check.json)."""

    def get(self) -> UpdateCheckState | None: ...

    def save(self, state: UpdateCheckState) -> None: ...


class ISelfUpdateGateway(Protocol):
    """Replacing the running app with another version of itself.

    One protocol for the whole capability, because the three questions always come
    together: *can* this deployment do it, is it *safe* right now, and *do* it.
    Implemented against the Docker daemon (`infra/update/self_update_gateway.py`);
    the use cases and the API only see this.
    """

    async def can_self_update(self) -> bool: ...

    def target_image(self, version: str) -> str:
        """Образ, на который переключится установка — показываем его в ответе."""
        ...

    def is_busy(self) -> bool:
        """True while a compile or an agent turn is in flight.

        Recreating the container kills them mid-run, so an *automatic* update
        waits for the next tick. A user who clicks «Обновить» is not blocked by
        this — they can see what they're interrupting.
        """
        ...

    async def start(self, target_version: str) -> bool: ...


class IReleaseNotesRepository(Protocol):
    """Curated release notes that ship with the build (release-notes.json).

    Read once at startup, not per request: the file changes only with the build.
    Implementations MUST never raise — a malformed file degrades to an empty list
    (the app is perfectly usable without a "what's new" screen); the release gate
    `make changelog-check` is what refuses to ship one.
    """

    def list(self, lang: Lang) -> tuple[ReleaseEntry, ...]: ...
