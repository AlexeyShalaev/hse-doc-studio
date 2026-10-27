from __future__ import annotations

import pytest

from tests.unit.infra.git_sync.conftest import Repo

pytestmark = pytest.mark.unit


@pytest.mark.parametrize("key", ["commit.gpgsign", "tag.gpgsign"])
def test__store_git__signing_is_off_for_commits_and_tags(repo: Repo, key: str) -> None:
    assert repo.git.text(repo.folder, ["config", "--get", key]).strip() == "false"
