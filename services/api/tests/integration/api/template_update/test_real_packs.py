"""База обновлений на настоящих паках репозитория: запись при создании полна и точна."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from httpx import AsyncClient

from tests.factories import project_api_payload

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git binary not available")


@pytest.mark.parametrize(("template_id", "lang"), [("vkr", "ru"), ("coursework", "ru"), ("pp", "en")])
async def test__real_template__fresh_project_matches_its_recorded_base(
    test_app: AsyncClient, tmp_path: Path, template_id: str, lang: str
) -> None:
    folder = tmp_path / template_id
    folder.mkdir()
    # Скрытый файл пользователя, лежавший в папке до создания, — не часть шаблона.
    (folder / ".vscode").mkdir()
    (folder / ".vscode" / "settings.json").write_text("{}", encoding="utf-8")
    payload = {**project_api_payload(str(folder)), "template_id": template_id, "lang": lang}
    project = (await test_app.post("/api/v1/projects", json=payload)).json()

    compare = await test_app.get(f"/api/v1/projects/{project['id']}/template/compare")

    assert compare.status_code == 200, compare.text
    body = compare.json()
    assert body["provenance"] == "recorded"
    assert body["files"] == []
    git_dir = folder / ".hse-studio" / "git"
    base_files = subprocess.run(
        ["git", "--git-dir", str(git_dir), "ls-tree", "-r", "--name-only", "refs/hse/template/2026.1"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert base_files
    assert not any(p.startswith((".vscode/", ".hse-studio/")) for p in base_files)
    assert "common/meta.tex" not in base_files
    # Рендер шаблона не дописал в базу ничего «приблизительного»: запись при создании полна.
    message = subprocess.run(
        ["git", "--git-dir", str(git_dir), "log", "-1", "--format=%B", "refs/hse/template/2026.1"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "Hse-Base-Approximate" not in message
