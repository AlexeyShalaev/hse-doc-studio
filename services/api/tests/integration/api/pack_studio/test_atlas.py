"""Атлас результата версии (срез O4, раздел 4.4 дизайна результата) в локальной Студии.

Настоящие роутер, DI и чтение файлов пространства; разбор версии идёт в отдельном процессе, как у предпросмотра.
Проверяются тело ответа по контракту, ETag и 304 по `If-None-Match`, закрепления, ошибки кодами и учёт правки
манифеста между запросами."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from hse_doc_studio.api.schemas.pack_studio_outcome import PackOutcomeAtlasResponse

from .conftest import API, DRAFT, DRAFT_DIR, PACK_FILES, RELEASED, RELEASED_DIR, Stand, write_pack

_VERSION = """\
id: "{version}"
status: {status}
summary: {{ ru: "Версия", en: "Version" }}
langs: [ru]
documents:
  - id: report
    name: {{ ru: "Отчёт", en: "Report" }}
    source_file: report/report.tex
    output_file: report/report.pdf
  - id: memo
    name: {{ ru: "Записка", en: "Memo" }}
    source_file: memo/memo.tex
    output_file: memo/memo.pdf
    supported_kinds: [research]

signatures:
  slots:
    - id: author
      label: {{ ru: Автор, en: Author }}
      applies_to: [report]
    - id: supervisor
      label: {{ ru: Руководитель, en: Supervisor }}
      applies_to: [report]
    - id: co_supervisor
      label: {{ ru: Консультант, en: Co-supervisor }}
      applies_to: [report]

pack_submission:
  profiles:
    - id: final
      name: {{ ru: "Защита", en: "Defence" }}
      items:
        - doc_id: report
          signatures: [author, supervisor]
      signing_slots:
        - {{ doc_id: report, slot_id: co_supervisor, when: {{ person: co_supervisor }} }}
"""

FILES: Mapping[str, str] = {
    **{k: v for k, v in PACK_FILES.items() if not k.endswith("version.yaml") and "/files/" not in k},
    f"{RELEASED_DIR}/version.yaml": _VERSION.format(version=RELEASED, status="stable"),
    f"{RELEASED_DIR}/files/report/report.tex": "\\documentclass{article}\n",
    f"{RELEASED_DIR}/files/memo/memo.tex": "\\documentclass{article}\n",
    f"{DRAFT_DIR}/version.yaml": _VERSION.format(version=DRAFT, status="beta"),
    f"{DRAFT_DIR}/files/report/report.tex": "\\documentclass{article}\n",
    f"{DRAFT_DIR}/files/memo/memo.tex": "\\documentclass{article}\n",
}


async def _workspace(stand: Stand) -> tuple[str, Path]:
    await stand.enable()
    root = write_pack(stand.root / "packs", FILES)
    ws = await stand.folder_workspace(root.parent, packs_path=root.name)
    return str(ws["id"]), root


def _url(ws: str, version: str = DRAFT) -> str:
    return f"{API}/workspaces/{ws}/versions/demo/report/{version}/outcome/atlas"


async def test__atlas__dimensions_rows_and_outcomes_come_from_the_version(stand: Stand) -> None:
    ws, _ = await _workspace(stand)

    resp = await stand.client.get(_url(ws))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    PackOutcomeAtlasResponse.model_validate(body)
    assert (body["pack"], body["template"], body["version"], body["state"]) == ("demo", "report", DRAFT, "work_tree")
    dims = {d["input"]: d for d in body["dimensions"]}
    assert set(dims) == {"kind", "supervisor", "co_supervisor", "academic_supervisor"}
    assert "route" in dims["co_supervisor"]["affects"]
    assert dims["co_supervisor"]["rules"][0]["pointer"] == "/pack_submission/profiles/0/signing_slots/0/when"
    assert {i["input"]: i["reason"] for i in body["ignored"]} == {"lang": "no_effect", "staffing": "no_effect"}
    assert body["rows_total"] == len(body["rows"]) == 2 * 3 * 2 * 2
    assert body["combinations_total"] == 2 * 3 * 2 * 2
    assert body["revision"].startswith("sha256-")
    assert resp.headers["ETag"].startswith('W/"atlas-')
    assert resp.headers["Cache-Control"] == "private, no-cache"


async def test__atlas__if_none_match_answers_304_until_the_manifest_changes(stand: Stand) -> None:
    ws, root = await _workspace(stand)
    first = await stand.client.get(_url(ws))
    etag = first.headers["ETag"]

    same = await stand.client.get(_url(ws), headers={"If-None-Match": etag})
    assert same.status_code == 304
    assert same.headers["ETag"] == etag
    assert same.content == b""

    manifest = root / DRAFT_DIR / "version.yaml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace("co_supervisor }", "supervisor, role: company }"), encoding="utf-8"
    )
    changed = await stand.client.get(_url(ws), headers={"If-None-Match": etag})

    assert changed.status_code == 200, changed.text
    assert changed.headers["ETag"] != etag
    assert changed.json()["revision"] != first.json()["revision"]


async def test__atlas__pins_cut_the_table_and_change_the_etag(stand: Stand) -> None:
    ws, _ = await _workspace(stand)
    full = await stand.client.get(_url(ws))

    pinned = await stand.client.get(_url(ws), params=[("pin", "supervisor:none"), ("pin", "kind:research")])

    assert pinned.status_code == 200, pinned.text
    body = pinned.json()
    assert body["rows_total"] == 4
    assert {r["key"].split("|")[0] for r in body["rows"]} == {"research"}
    assert pinned.headers["ETag"] != full.headers["ETag"]
    assert body["revision"] == full.json()["revision"]


async def test__atlas__errors_are_coded(stand: Stand) -> None:
    ws, _ = await _workspace(stand)

    unknown = await stand.client.get(_url(ws), params={"pin": "nope:x"})
    bad_value = await stand.client.get(_url(ws), params={"pin": "supervisor:boss"})
    junk = await stand.client.get(_url(ws), params={"pin": "supervisor"})
    twice = await stand.client.get(_url(ws), params=[("pin", "supervisor:none"), ("pin", "supervisor:company")])
    example = await stand.client.get(_url(ws), params={"example": "missing"})
    head = await stand.client.get(_url(ws), params={"state": "head"})
    missing = await stand.client.get(_url(ws, "9.9.9"))

    for resp, field in (
        (unknown, "nope"),
        (bad_value, "supervisor"),
        (junk, "pin"),
        (twice, "supervisor"),
        (example, "example"),
    ):
        assert resp.status_code == 400, resp.text
        assert resp.json()["code"] == "inputs_invalid"
        assert resp.json()["field"] == field
    assert head.status_code == 409
    assert head.json()["code"] == "diff_base_unavailable"
    assert missing.status_code == 404, missing.text


async def test__atlas__a_released_version_is_read_the_same_way(stand: Stand) -> None:
    ws, _ = await _workspace(stand)

    resp = await stand.client.get(_url(ws, RELEASED))

    assert resp.status_code == 200, resp.text
    body: dict[str, Any] = resp.json()
    assert body["version"] == RELEASED
    assert body["rows_total"] == 24
