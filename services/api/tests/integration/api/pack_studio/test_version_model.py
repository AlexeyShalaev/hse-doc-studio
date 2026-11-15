"""Формы версии (template-studio.md, 5.2–5.3, срезы T11 и T12) в локальной Студии: настоящие роутер, DI и файлы."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .conftest import API, DRAFT, DRAFT_DIR, PACK_FILES, RELEASED, RELEASED_DIR, Stand, write_pack

_VERSION = """\
# Версия для форм.
id: "{version}"
status: {status}
summary: {{ ru: "Версия", en: "Version" }}
langs: [ru, en]

# Ростер: порядок = порядок в UI.
documents:
  - report
  - memo

dynamic_includes:
  - template: common/meta.tex.j2
    output:   common/meta.tex

meta_groups:
  - id: study
    label: {{ ru: Учёба, en: Studies }}
  - id: title
    label: {{ ru: Титул, en: Title }}

meta_fields:
  year:
    type: string
    group:       study
    label:       {{ ru: Учебный год, en: Academic year }}
    required_at: create
    # Год окончания учебного года.
    auto: academic_year

  name_en:
    type: string
    group:       title
    label:       {{ ru: Название на английском, en: Title in English }}
    required_at: never

signatures:
  slots:
    - id: author
      label: {{ ru: Автор, en: Author }}
      applies_to: [report, memo]
"""

_REPORT_DOC = """\
# Отчёт.
name:
  ru: Отчёт
  en: Report
source_file: report/report.tex
output_file: report/report.pdf
supported_langs:
- ru
group: work
"""

_MEMO_DOC = """\
name: { ru: Записка, en: Memo }
source_file: memo/memo.tex
output_file: memo/memo.pdf
"""

_META = r"""\newcommand{\hseYear}{((( project.meta.year )))}
\newcommand{\hseTitleEn}{((( project.meta.name_en | default('') )))}
\newcommand{\hseYearEnd}{((( project.meta.year_end )))}
"""


def _files(version_dir: str, version: str, status: str) -> dict[str, str]:
    return {
        f"{version_dir}/version.yaml": _VERSION.format(version=version, status=status),
        f"{version_dir}/files/common/meta.tex.j2": _META,
        f"{version_dir}/files/report/doc.yaml": _REPORT_DOC,
        f"{version_dir}/files/report/report.ru.tex": "\\input{../common/meta}\n\\hseYear\n",
        f"{version_dir}/files/report/preamble.tex": "% preamble\n",
        f"{version_dir}/files/memo/doc.yaml": _MEMO_DOC,
        f"{version_dir}/files/memo/memo.tex": "\\input{../common/meta}\n\\hseTitleEn ((( project.meta.name_en )))\n",
    }


FILES: Mapping[str, str] = {
    **{k: v for k, v in PACK_FILES.items() if not k.endswith("version.yaml") and "/files/" not in k},
    **_files(RELEASED_DIR, RELEASED, "stable"),
    **_files(DRAFT_DIR, DRAFT, "beta"),
}


async def _workspace(stand: Stand) -> tuple[str, Path]:
    await stand.enable()
    root = write_pack(stand.root / "packs", FILES)
    ws = await stand.folder_workspace(root.parent, packs_path=root.name)
    return str(ws["id"]), root


def _url(ws: str, version: str = DRAFT) -> str:
    return f"{API}/workspaces/{ws}/versions/demo/report/{version}/model"


async def _model(stand: Stand, ws: str, version: str = DRAFT) -> dict[str, Any]:
    resp = await stand.client.get(_url(ws, version))
    assert resp.status_code == 200, resp.text
    assert resp.headers["ETag"] == resp.json()["manifest"]["etag"]
    return dict(resp.json())


async def test__get__manifests_documents_languages_and_usage(stand: Stand) -> None:
    ws, _ = await _workspace(stand)

    body = await _model(stand, ws)

    assert body["read_only"] is None
    assert body["manifest"]["path"] == f"{DRAFT_DIR}/version.yaml"
    assert list(body["manifest"]["data"]["meta_fields"]) == ["year", "name_en"]
    report, memo = body["documents"]
    assert report["id"] == "report"
    assert report["manifest"]["path"] == f"{DRAFT_DIR}/files/report/doc.yaml"
    assert report["data"]["group"] == "work"
    assert {(f["path"], f["bare"], f["lang"]) for f in report["files"]} == {
        ("report/preamble.tex", "report/preamble.tex", ""),
        ("report/report.ru.tex", "report/report.tex", "ru"),
    }
    assert report["references"] == ["signatures.slots[author].applies_to"]
    usage = {(u["field"], u["document"]): u for u in body["usage"]}
    assert usage[("year", "report")]["macros"] == ["hseYear"]
    assert usage[("name_en", "memo")]["direct"] is True
    assert ("name_en", "report") not in usage
    assert body["problems"] == []
    assert memo["files"][0]["lang"] == ""


async def test__get__released_version_is_read_only(stand: Stand) -> None:
    ws, _ = await _workspace(stand)

    body = await _model(stand, ws, RELEASED)

    assert body["read_only"] == "version_released"


async def test__patch__label_written_in_place_with_comments(stand: Stand) -> None:
    ws, root = await _workspace(stand)
    etag = (await _model(stand, ws))["manifest"]["etag"]
    body = {
        "file": "version.yaml",
        "ops": [
            {
                "op": "set",
                "path": ["meta_fields", "year", "label"],
                "value": {"ru": "Год защиты", "en": "Academic year"},
            },
            {"op": "move", "path": ["meta_groups"], "index": 1, "to": 0},
        ],
    }

    resp = await stand.client.patch(_url(ws), json=body, headers={"If-Match": etag})

    assert resp.status_code == 200, resp.text
    assert resp.json()["changed"] == [f"{DRAFT_DIR}/version.yaml"]
    assert resp.json()["manifest"]["etag"] != etag
    text = (root / DRAFT_DIR / "version.yaml").read_text(encoding="utf-8")
    assert "    label:       { ru: Год защиты, en: Academic year }\n" in text
    assert "    # Год окончания учебного года.\n    auto: academic_year\n" in text
    assert text.index("- id: title") < text.index("- id: study")

    stale = await stand.client.patch(_url(ws), json=body, headers={"If-Match": etag})

    assert stale.status_code == 409
    assert stale.json()["code"] == "stale_file"


async def test__patch__doc_manifest(stand: Stand) -> None:
    ws, root = await _workspace(stand)
    report = (await _model(stand, ws))["documents"][0]
    body = {"file": "files/report/doc.yaml", "ops": [{"op": "set", "path": ["group"], "value": "report"}]}

    resp = await stand.client.patch(_url(ws), json=body, headers={"If-Match": report["manifest"]["etag"]})

    assert resp.status_code == 200, resp.text
    assert resp.json()["documents"][0]["data"]["group"] == "report"
    assert (root / DRAFT_DIR / "files/report/doc.yaml").read_text(encoding="utf-8").startswith("# Отчёт.\n")


async def test__patch__edit_the_loader_would_drop_is_refused(stand: Stand) -> None:
    ws, root = await _workspace(stand)
    before = (root / DRAFT_DIR / "version.yaml").read_text(encoding="utf-8")
    body = {"file": "version.yaml", "ops": [{"op": "set", "path": ["meta_fields", "year", "type"], "value": "number"}]}

    resp = await stand.client.patch(_url(ws), json=body)

    assert resp.status_code == 400
    assert resp.json()["code"] == "model_invalid"
    assert "/meta_fields/year/type" in resp.json()["reason"]
    assert (root / DRAFT_DIR / "version.yaml").read_text(encoding="utf-8") == before


async def test__patch__other_files_are_not_model_files(stand: Stand) -> None:
    ws, _ = await _workspace(stand)
    body = {"file": "files/report/report.ru.tex", "ops": [{"op": "delete", "path": ["x"]}]}

    resp = await stand.client.patch(_url(ws), json=body)

    assert resp.status_code == 400
    assert resp.json()["code"] == "model_invalid"


async def test__patch__released_version_is_refused(stand: Stand) -> None:
    ws, _ = await _workspace(stand)
    body = {"file": "version.yaml", "ops": [{"op": "set", "path": ["summary", "ru"], "value": "x"}]}

    resp = await stand.client.patch(_url(ws, RELEASED), json=body)

    assert resp.status_code == 409
    assert resp.json()["code"] == "version_released"


async def test__rename_field__key_and_template_refs(stand: Stand) -> None:
    ws, root = await _workspace(stand)
    etag = (await _model(stand, ws))["manifest"]["etag"]

    resp = await stand.client.post(
        f"{_url(ws)}/actions", json={"action": "rename_field", "field": "year", "to": "defence_year"}
    )
    assert resp.status_code == 200, resp.text
    resp = await stand.client.post(
        f"{_url(ws)}/actions",
        json={"action": "rename_field", "field": "name_en", "to": "title_en"},
        headers={"If-Match": resp.json()["manifest"]["etag"]},
    )

    assert resp.status_code == 200, resp.text
    assert etag != resp.json()["manifest"]["etag"]
    assert list(resp.json()["manifest"]["data"]["meta_fields"]) == ["defence_year", "title_en"]
    assert sorted(resp.json()["changed"]) == [
        f"{DRAFT_DIR}/files/common/meta.tex.j2",
        f"{DRAFT_DIR}/files/memo/memo.tex",
        f"{DRAFT_DIR}/version.yaml",
    ]
    meta = (root / DRAFT_DIR / "files/common/meta.tex.j2").read_text(encoding="utf-8")
    assert "project.meta.defence_year )" in meta
    assert "project.meta.year_end" in meta
    assert "project.meta.title_en | default" in meta
    text = (root / DRAFT_DIR / "version.yaml").read_text(encoding="utf-8")
    assert "  defence_year:\n    type: string\n" in text
    assert "    # Год окончания учебного года.\n" in text


async def test__rename_field__person_and_taken_keys_refused(stand: Stand) -> None:
    ws, _ = await _workspace(stand)

    taken = await stand.client.post(
        f"{_url(ws)}/actions", json={"action": "rename_field", "field": "year", "to": "name_en"}
    )
    person = await stand.client.post(
        f"{_url(ws)}/actions", json={"action": "rename_field", "field": "year", "to": "supervisor"}
    )

    assert taken.status_code == 400
    assert taken.json()["code"] == "model_invalid"
    assert person.status_code == 400


async def test__add_document__blank_and_from_library(stand: Stand) -> None:
    ws, root = await _workspace(stand)

    blank = await stand.client.post(
        f"{_url(ws)}/actions",
        json={"action": "add_document", "document": "review", "name": {"ru": "Отзыв", "en": "Review"}},
    )
    assert blank.status_code == 200, blank.text
    library = await stand.client.get(f"{API}/workspaces/{ws}/doc-library")
    assert library.status_code == 200
    memo = next(d for d in library.json()["documents"] if d["id"] == "memo")
    assert memo["version"] == DRAFT
    copy = await stand.client.post(
        f"{_url(ws)}/actions", json={"action": "add_document", "document": "memo2", "source": memo["path"]}
    )

    assert copy.status_code == 200, copy.text
    model = copy.json()
    assert [d["id"] for d in model["documents"]] == ["report", "memo", "review", "memo2"]
    review = model["documents"][2]
    assert review["data"]["source_file"] == "review/review.tex"
    assert review["data"]["supported_langs"] == ["ru", "en"]
    assert (root / DRAFT_DIR / "files/review/review.tex").read_text(encoding="utf-8").count("\\input{../common/meta}")
    assert model["documents"][3]["data"]["source_file"] == "memo2/memo.tex"
    assert (root / DRAFT_DIR / "files/memo2/memo.tex").is_file()
    assert model["problems"] == []
    text = (root / DRAFT_DIR / "version.yaml").read_text(encoding="utf-8")
    assert "documents:\n  - report\n  - memo\n  - review\n  - memo2\n" in text


async def test__add_document__existing_id_refused(stand: Stand) -> None:
    ws, _ = await _workspace(stand)

    resp = await stand.client.post(f"{_url(ws)}/actions", json={"action": "add_document", "document": "memo"})

    assert resp.status_code == 400
    assert resp.json()["code"] == "model_invalid"


async def test__remove_document__roster_entry_and_folder(stand: Stand) -> None:
    ws, root = await _workspace(stand)

    resp = await stand.client.post(f"{_url(ws)}/actions", json={"action": "remove_document", "document": "memo"})

    assert resp.status_code == 200, resp.text
    assert [d["id"] for d in resp.json()["documents"]] == ["report"]
    assert not (root / DRAFT_DIR / "files/memo").exists()
    assert f"{DRAFT_DIR}/files/memo" in resp.json()["changed"]


async def test__remove_document__released_version_untouched(stand: Stand) -> None:
    ws, root = await _workspace(stand)

    resp = await stand.client.post(
        f"{_url(ws, RELEASED)}/actions", json={"action": "remove_document", "document": "memo"}
    )

    assert resp.status_code == 409
    assert resp.json()["code"] == "version_released"
    assert (root / RELEASED_DIR / "files/memo/doc.yaml").is_file()


async def test__add_translation__default_edition_copied_and_lang_listed(stand: Stand) -> None:
    ws, root = await _workspace(stand)

    resp = await stand.client.post(
        f"{_url(ws)}/actions", json={"action": "add_translation", "document": "report", "lang": "en"}
    )

    assert resp.status_code == 200, resp.text
    folder = root / DRAFT_DIR / "files/report"
    assert (folder / "report.en.tex").read_bytes() == (folder / "report.ru.tex").read_bytes()
    assert not (folder / "preamble.en.tex").exists()
    assert resp.json()["documents"][0]["data"]["supported_langs"] == ["ru", "en"]


async def test__add_translation__shared_file_split_on_request(stand: Stand) -> None:
    ws, root = await _workspace(stand)

    resp = await stand.client.post(
        f"{_url(ws)}/actions",
        json={"action": "add_translation", "document": "memo", "lang": "en", "files": ["memo/memo.tex"]},
    )

    assert resp.status_code == 200, resp.text
    folder = root / DRAFT_DIR / "files/memo"
    assert sorted(p.name for p in folder.iterdir()) == ["doc.yaml", "memo.en.tex", "memo.ru.tex"]
    nothing = await stand.client.post(
        f"{_url(ws)}/actions", json={"action": "add_translation", "document": "memo", "lang": "en"}
    )
    assert nothing.status_code == 400
    default = await stand.client.post(
        f"{_url(ws)}/actions", json={"action": "add_translation", "document": "memo", "lang": "ru"}
    )
    assert default.status_code == 400
