from __future__ import annotations

from typing import Any

import pytest
from hse_doc_studio.core.git_sync.entities import AuthorProfile
from hse_doc_studio.infra.vcs.profile_source import ConfigAuthorProfile

pytestmark = pytest.mark.unit


class _Repo:
    def __init__(self, data: Any = None, *, boom: bool = False) -> None:
        self._data = data if data is not None else {}
        self._boom = boom

    def read_local(self) -> Any:
        if self._boom:
            raise OSError("диск недоступен")
        return self._data


def test__get__valid_pair__returns_profile() -> None:
    repo = _Repo({"profile_name": "Алиса", "profile_email": "Alice@Example.ORG"})

    assert ConfigAuthorProfile(repo).get() == AuthorProfile("Алиса", "Alice@example.org")


@pytest.mark.parametrize(
    "stored",
    [
        {},
        {"profile_name": None, "profile_email": None},
        {"profile_name": "Алиса"},
        {"profile_email": "alice@example.org"},
        {"profile_name": "Алиса", "profile_email": "not-an-email"},
        {"profile_name": "<x>", "profile_email": "alice@example.org"},
        {"profile_name": 5, "profile_email": ["a@b.c"]},
        ["не словарь"],
    ],
)
def test__get__missing_or_invalid__returns_none(stored: Any) -> None:
    assert ConfigAuthorProfile(_Repo(stored)).get() is None


def test__get__repository_fails__returns_none_instead_of_raising() -> None:
    assert ConfigAuthorProfile(_Repo(boom=True)).get() is None
