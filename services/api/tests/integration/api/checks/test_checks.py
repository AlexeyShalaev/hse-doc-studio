from __future__ import annotations

from pathlib import Path

import pytest
from httpx import AsyncClient

from tests.factories import project_api_payload

_FAKE_ID = "00000000-0000-0000-0000-000000000000"
_KNOWN_SEVERITIES = {"info", "warn", "err"}


async def _create_project(client: AsyncClient, folder: Path) -> dict:
    folder.mkdir(exist_ok=True)
    resp = await client.post("/api/v1/projects", json=project_api_payload(str(folder)))
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _run_checks(client: AsyncClient, project_id: str, doc_id: str):
    return await client.post(
        f"/api/v1/projects/{project_id}/documents/{doc_id}/checks/run",
        params={"include_external": "false"},
    )


def _inject_quote_issue(project_folder: Path) -> None:
    """Append a straight-quotes sentence to the (real, pack-rendered) thesis.tex.

    `typography-ru/quotes` (packs/hse-cs-se/.../checks/typography-ru.yaml) applies
    only to `thesis`, scanning `thesis/**/*.tex` — same issue already exercised at
    the unit level in tests/unit/infra/checks/test_typography_engine.py.
    """
    thesis_path = project_folder / "thesis" / "thesis.tex"
    content = thesis_path.read_text(encoding="utf-8")
    assert "\\end{document}" in content
    content = content.replace(
        "\\end{document}",
        'Это слово "важное" здесь.\n\n\\end{document}',
    )
    thesis_path.write_text(content, encoding="utf-8")


# --- run checks --------------------------------------------------------------


async def test__api__run_checks__every_document__returns_well_shaped_results(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]
    docs = (await test_app.get(f"/api/v1/projects/{project_id}/documents")).json()
    assert len(docs) >= 1

    for doc in docs:
        resp = await _run_checks(test_app, project_id, doc["id"])

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["doc_id"] == doc["id"]
        assert body["compile_id"] is None
        assert isinstance(body["results"], list)
        for r in body["results"]:
            assert isinstance(r["rule_id"], str)
            assert r["rule_id"]
            assert r["severity"] in _KNOWN_SEVERITIES
            assert isinstance(r["message"], str)
            assert r["message"]
            assert "location" in r


async def test__api__run_checks__pristine_thesis__flags_real_content_issues(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await _run_checks(test_app, project["id"], "thesis")

    assert resp.status_code == 200, resp.text
    results = resp.json()["results"]
    assert len(results) >= 1
    rule_sources = {r["rule_id"].split("/", 1)[0] for r in results}
    assert rule_sources & {"hse-pi-content-2026", "hse-pi-methodology-2026"}


async def test__api__run_checks__nonexistent_doc__returns_404(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await _run_checks(test_app, project["id"], "no-such-doc")

    assert resp.status_code == 404


# --- rules ---------------------------------------------------------------


async def test__api__list_project_check_rules__returns_rules_with_expected_fields(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/checks/rules")

    assert resp.status_code == 200, resp.text
    rules = resp.json()
    assert isinstance(rules, list)
    assert len(rules) > 0
    item = rules[0]
    assert set(item.keys()) == {
        "rule_id",
        "title",
        "description",
        "category",
        "effective_severity",
        "enabled",
        "source",
        "source_label",
    }
    assert item["effective_severity"] in _KNOWN_SEVERITIES
    # Подпись группы объявляет пак (checks/<source>.yaml -> label), приложение
    # названий стандартов и ОП не знает. У hse-cs-se она есть у всех источников.
    assert item["source_label"].get("ru"), item
    assert item["source_label"].get("en"), item


async def test__api__list_document_check_rules__scoped_to_document_includes_typography(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/documents/thesis/checks/rules")

    assert resp.status_code == 200, resp.text
    rules = resp.json()
    assert isinstance(rules, list)
    assert len(rules) > 0
    assert any(r["rule_id"] == "typography-ru/quotes" for r in rules)


async def test__api__list_document_check_rules__nonexistent_doc__returns_404(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.get(f"/api/v1/projects/{project['id']}/documents/no-such-doc/checks/rules")

    assert resp.status_code == 404


# --- normcontrol report ----------------------------------------------------


async def test__api__get_normcontrol_report__pristine_project__all_documents_clean(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project = await _create_project(test_app, tmp_path / "proj")
    project_id = project["id"]
    docs = (await test_app.get(f"/api/v1/projects/{project_id}/documents")).json()

    resp = await test_app.get(f"/api/v1/projects/{project_id}/normcontrol-report")

    assert resp.status_code == 200, resp.text
    report = resp.json()
    # No document has been compiled yet, so there is nothing to aggregate:
    # this must hold regardless of which/how many documents the pack defines.
    assert report["docs_total"] == len(docs)
    assert report["docs_clean"] == len(docs)
    assert report["readiness_pct"] == 100
    assert report["totals"] == {"errors": 0, "warnings": 0, "infos": 0, "total": 0}
    assert report["by_category"] == []
    assert report["by_source"] == []


# --- 404s across every checks endpoint, given a nonexistent project ----------


@pytest.mark.parametrize(
    ("method", "path_suffix"),
    [
        ("GET", "/checks/rules"),
        ("GET", "/documents/thesis/checks/rules"),
        ("POST", "/documents/thesis/checks/run"),
        ("GET", "/normcontrol-report"),
    ],
)
async def test__api__checks_endpoints__nonexistent_project__returns_404(
    test_app: AsyncClient, method: str, path_suffix: str
) -> None:
    resp = await test_app.request(method, f"/api/v1/projects/{_FAKE_ID}{path_suffix}")

    assert resp.status_code == 404


# --- apply-fix --------------------------------------------------------------


async def test__api__apply_check_fix__typography_quote_issue__fixes_file_and_stale_retry_returns_409(
    test_app: AsyncClient, tmp_path: Path
) -> None:
    project_folder = tmp_path / "proj"
    project = await _create_project(test_app, project_folder)
    project_id = project["id"]
    _inject_quote_issue(project_folder)

    run_resp = await _run_checks(test_app, project_id, "thesis")
    results = run_resp.json()["results"]
    quote_result = next(r for r in results if r["rule_id"] == "typography-ru/quotes")
    fix = quote_result["fix"]
    assert fix is not None
    assert fix["search"] == '"важное"'
    assert fix["replace"] == "«важное»"

    apply_body = {
        "path": quote_result["location"]["file"],
        "search": fix["search"],
        "replace": fix["replace"],
        "line": fix["line"],
    }
    apply_resp = await test_app.post(f"/api/v1/projects/{project_id}/checks/apply-fix", json=apply_body)

    assert apply_resp.status_code == 204, apply_resp.text
    new_content = (project_folder / "thesis" / "thesis.tex").read_text(encoding="utf-8")
    assert '"важное"' not in new_content
    assert "«важное»" in new_content

    stale_resp = await test_app.post(f"/api/v1/projects/{project_id}/checks/apply-fix", json=apply_body)
    assert stale_resp.status_code == 409, stale_resp.text


async def test__api__apply_check_fix__search_text_not_found__returns_409(test_app: AsyncClient, tmp_path: Path) -> None:
    project = await _create_project(test_app, tmp_path / "proj")

    resp = await test_app.post(
        f"/api/v1/projects/{project['id']}/checks/apply-fix",
        json={"path": "thesis/thesis.tex", "search": "NO_SUCH_TEXT_XYZ", "replace": "x", "line": None},
    )

    assert resp.status_code == 409


async def test__api__apply_check_fix__nonexistent_project__returns_404(test_app: AsyncClient) -> None:
    resp = await test_app.post(
        f"/api/v1/projects/{_FAKE_ID}/checks/apply-fix",
        json={"path": "thesis/thesis.tex", "search": "x", "replace": "y", "line": None},
    )

    assert resp.status_code == 404
