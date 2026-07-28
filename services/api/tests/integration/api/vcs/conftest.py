from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest_asyncio
from httpx import AsyncClient

from tests.factories import project_api_payload

# A random-but-well-formed UUID that no test ever creates a project under —
# used across every sub-file to exercise the "project not found" → 404 path.
FAKE_PROJECT_ID = "00000000-0000-0000-0000-000000000000"

# A real, tracked (non-excluded) LaTeX source that every hse-cs-se `vkr`
# project renders at creation time. Editing it gives dirty/diff/snapshot flows
# a real file change to work with, instead of poking VCS internals directly.
TRACKED_FILE = "thesis/thesis.tex"


async def create_project(client: AsyncClient, folder: Path) -> dict[str, Any]:
    folder.mkdir(parents=True, exist_ok=True)
    resp = await client.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest_asyncio.fixture
async def project(test_app: AsyncClient, tmp_path: Path) -> dict[str, Any]:
    """A freshly created real project. `CreateProjectUC` already runs a real
    `git init` + root commit as a side effect (see create_project.py step 8), so
    by the time this fixture returns, VCS is initialized and the tree is clean."""
    return await create_project(test_app, tmp_path / "proj")


def edit_tracked_file(project: dict[str, Any], marker: str) -> None:
    """Append a real, diff-visible line to the shared tracked LaTeX file."""
    path = Path(project["folder"]) / TRACKED_FILE
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n% {marker}\n")
