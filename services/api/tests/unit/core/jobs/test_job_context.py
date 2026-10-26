from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest
from hse_doc_studio.core.access.entities import Actor
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.jobs.files import ManifestFile
from hse_doc_studio.core.jobs.protocols import JobContext

from tests.unit.core.jobs.samples import JOB_ID, PROJECT_ID


def _ctx(workspace: Path) -> JobContext:
    return JobContext(
        job_id=JOB_ID,
        project_id=PROJECT_ID,
        actor=Actor.local(),
        locale=Lang.ru,
        workspace=workspace,
        outputs=Mock(),
    )


def test__job_context__path_of__joins_the_relative_path_under_the_workspace(tmp_path: Path) -> None:
    assert _ctx(tmp_path).path_of(ManifestFile("tz/main.tex")) == tmp_path / "tz" / "main.tex"


def test__job_context__path_of__symlink_leaving_the_workspace__rejected(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ValueError, match="escapes the workspace"):
        _ctx(workspace).path_of(ManifestFile("link/secret.txt"))
