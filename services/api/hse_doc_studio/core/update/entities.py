from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ReleaseEntry:
    """One release as the UI shows it: version, date and already-localized notes.

    Notes come from the curated bilingual list (release-notes.json), not from
    the release feed — the feed only tells us WHICH version is the newest.
    """

    version: str
    date: str  # YYYY-MM-DD
    notes: tuple[str, ...]


@dataclass(frozen=True)
class UpdateFeedProbe:
    """Outcome of one look at the release feed.

    `checked` is True only when the feed actually answered — a disabled feed and
    an unreachable one both leave it False, and `reason` says which, so the UI can
    tell "you're up to date" apart from "we couldn't ask".

    `releases` are ALL published releases, newest first — the user may switch to
    any of them, not just the newest. Their notes come from the feed because the
    curated list (release-notes.json) ships INSIDE a build and can never describe
    a version that isn't installed.
    """

    releases: tuple[ReleaseEntry, ...] = ()
    checked: bool = False
    reason: str = ""

    @property
    def latest(self) -> str:
        return self.releases[0].version if self.releases else ""


@dataclass(frozen=True)
class UpdateCheckState:
    """Last known feed answer, persisted so the check survives a restart.

    Without it an offline/air-gapped install would forget which versions exist the
    moment the app is restarted: no update banner, and nothing to offer in the
    version picker until the feed came back.

    Notes are stored with each version on purpose — they describe versions that
    aren't installed, so they exist nowhere else on this machine.
    """

    checked_at: datetime
    releases: tuple[ReleaseEntry, ...] = ()

    @property
    def latest(self) -> str:
        return self.releases[0].version if self.releases else ""
