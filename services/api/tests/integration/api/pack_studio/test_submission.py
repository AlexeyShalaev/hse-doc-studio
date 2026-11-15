"""Профили сдачи, пункты и порядок маршрута формой (template-studio.md, 5.5-5.8, срез T13) в локальной Студии.

Настоящие роутер, DI и запись файлов; «Маршрут в этой комбинации» считается на синтетическом проекте предпросмотра
(разбор версии в отдельном процессе, как у сборки), без сборки PDF.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml

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

signatures:
  slots:
    - id: author
      label: {{ ru: Автор, en: Author }}
      applies_to: [report, memo]
    - id: supervisor
      label: {{ ru: Руководитель, en: Supervisor }}
      applies_to: [report]
    - id: academic_supervisor
      label: {{ ru: Академрук, en: Academic supervisor }}
      applies_to: [report]

# Точки сдачи.
pack_submission:
  profiles:
    - id: final
      name:        {{ ru: "Защита", en: "Defence" }}
      items:
        # Отчёт подписывают автор и руководитель.
        - doc_id: report
          signatures: [author, supervisor]
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
    return f"{API}/workspaces/{ws}/versions/demo/report/{version}/submission"


def _manifest(root: Path, directory: str = DRAFT_DIR) -> str:
    return (root / directory / "version.yaml").read_text(encoding="utf-8")


async def test__get__profiles_slots_and_etag(stand: Stand) -> None:
    ws, _ = await _workspace(stand)

    resp = await stand.client.get(_url(ws))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["etag"] == resp.headers["ETag"]
    assert body["read_only"] is None
    assert body["documents"] == ["report", "memo"]
    assert [s["id"] for s in body["slots"]] == ["author", "supervisor", "academic_supervisor"]
    assert body["route"] is None
    assert body["builtin_route"] == [["author"], ["supervisor", "co_supervisor"], ["academic_supervisor"]]
    (profile,) = body["profiles"]
    assert profile["id"] == "final"
    assert profile["error"] is None
    assert profile["items"] == [
        {
            "index": 0,
            "entry": {
                "doc_id": "report",
                "signatures": ["author", "supervisor"],
                "methods": {},
                "skip_if_nda": False,
                "supported_kinds": [],
            },
            "error": None,
        }
    ]


async def test__patch__methods_preset_and_hint_written_with_comments_kept(stand: Stand) -> None:
    ws, root = await _workspace(stand)
    etag = (await stand.client.get(_url(ws))).json()["etag"]
    ops = [
        {
            "op": "set_entry",
            "profile": 0,
            "entries": "items",
            "index": 0,
            "item": {"doc_id": "report", "signatures": ["author", "supervisor"], "methods": {"author": ["image"]}},
        },
        {
            "op": "add_entry",
            "profile": 0,
            "entries": "signing_slots",
            "slot": {"doc_id": "report", "slot_id": "academic_supervisor", "when": {"person": "supervisor"}},
        },
        {"op": "set_profile_route", "profile": 0, "steps": [["author"], ["supervisor", "academic_supervisor"]]},
        {
            "op": "set_profile",
            "profile": 0,
            "head": {
                "id": "final",
                "name": {"ru": "Защита", "en": "Defence"},
                "deadline_hint": {"ru": "Обычно в июне", "en": "Usually in June"},
            },
        },
    ]

    resp = await stand.client.patch(_url(ws), json={"ops": ops}, headers={"If-Match": etag})

    assert resp.status_code == 200, resp.text
    profile = resp.json()["profiles"][0]
    assert profile["items"][0]["entry"]["methods"] == {"author": ["image"]}
    assert profile["signing_slots"][0]["entry"]["when"] == {"person": "supervisor", "role": None}
    assert profile["signing_route"] == [["author"], ["supervisor", "academic_supervisor"]]
    assert profile["deadline_hint"] == {"ru": "Обычно в июне", "en": "Usually in June"}
    text = _manifest(root)
    assert "# Точки сдачи.\n" in text
    assert "        # Отчёт подписывают автор и руководитель.\n" in text
    assert "          methods: { author: [image] }\n" in text

    stale = await stand.client.patch(_url(ws), json={"ops": ops[:1]}, headers={"If-Match": etag})

    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_file"


async def test__patch__value_the_loader_would_drop_is_submission_invalid(stand: Stand) -> None:
    ws, root = await _workspace(stand)
    before = _manifest(root)
    head = {
        "id": "final",
        "name": {"ru": "Защита", "en": "Defence"},
        "deadline_hint": {"ru": "До 20 июня 2027 года", "en": "By 20 June"},
    }

    resp = await stand.client.patch(_url(ws), json={"ops": [{"op": "set_profile", "profile": 0, "head": head}]})

    assert resp.status_code == 400
    assert resp.json()["code"] == "submission_invalid"
    assert "concrete date" in resp.json()["reason"]
    assert _manifest(root) == before


async def test__patch__released_version_is_read_only(stand: Stand) -> None:
    ws, root = await _workspace(stand)
    before = _manifest(root, RELEASED_DIR)

    got = await stand.client.get(_url(ws, RELEASED))
    resp = await stand.client.patch(
        _url(ws, RELEASED), json={"ops": [{"op": "set_route", "steps": [["author"], ["supervisor"]]}]}
    )

    assert got.json()["read_only"] == "version_released"
    assert resp.status_code == 409
    assert resp.json()["code"] == "version_released"
    assert _manifest(root, RELEASED_DIR) == before


async def test__patch__op_without_its_fields_is_rejected(stand: Stand) -> None:
    ws, _ = await _workspace(stand)

    resp = await stand.client.patch(_url(ws), json={"ops": [{"op": "add_entry", "profile": 0, "entries": "items"}]})

    assert resp.status_code == 422


async def test__routes__preset_slot_follows_the_supervisor_switch(stand: Stand) -> None:
    ws, _ = await _workspace(stand)
    ops: list[dict[str, Any]] = [
        {
            "op": "add_entry",
            "profile": 0,
            "entries": "signing_slots",
            "slot": {
                "doc_id": "report",
                "slot_id": "academic_supervisor",
                "when": {"person": "supervisor", "role": "company"},
            },
        }
    ]
    assert (await stand.client.patch(_url(ws), json={"ops": ops})).status_code == 200

    company = await stand.client.post(f"{_url(ws)}/routes", json={"combination": {"supervisor": "company"}})
    university = await stand.client.post(f"{_url(ws)}/routes", json={"combination": {"supervisor": "university"}})

    assert company.status_code == 200, company.text
    body = company.json()
    assert body["example"] == "auto:normal"
    assert body["combination"]["supervisor"] == "company"
    (route,) = body["profiles"]
    assert [[p["persona"] for p in step] for step in route["steps"]] == [
        ["author"],
        ["supervisor"],
        ["academic_supervisor"],
    ]
    assert route["preset"] is True
    assert {(p["slot_id"], p["source"]) for p in route["pairs"]} == {
        ("author", "point"),
        ("supervisor", "point"),
        ("academic_supervisor", "preset"),
    }
    (other,) = university.json()["profiles"]
    assert [p["persona"] for step in other["steps"] for p in step] == ["author", "supervisor"]
    assert other["skipped"] == [
        {"doc_id": "report", "slot_id": "academic_supervisor", "when": {"person": "supervisor", "role": "company"}}
    ]


async def test__routes__unknown_switch_is_preview_invalid(stand: Stand) -> None:
    ws, _ = await _workspace(stand)

    resp = await stand.client.post(f"{_url(ws)}/routes", json={"combination": {"weather": "rain"}})

    assert resp.status_code == 400
    assert resp.json()["code"] == "preview_invalid"
    assert yaml.safe_load(_manifest(stand.root / "packs"))["pack_submission"]["profiles"][0]["id"] == "final"
