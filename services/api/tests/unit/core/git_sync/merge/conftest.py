from __future__ import annotations

import pytest
from hse_doc_studio.core.git_sync.merge.text import BASE_LABEL, OURS_LABEL, THEIRS_LABEL
from hse_doc_studio.infra.template_update.merge_engine import GitMergeFileEngine


@pytest.fixture(scope="session")
def engine() -> GitMergeFileEngine:
    return GitMergeFileEngine(OURS_LABEL, BASE_LABEL, THEIRS_LABEL)
