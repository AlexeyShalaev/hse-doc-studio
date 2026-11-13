"""Якоря сборки на диске: свежесть файла позиций по `.fls`, `anchors.json` при публикации PDF (15.17)."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from uuid import uuid4

import pytest
from hse_doc_studio.core.jobs.artifacts import PositionsSource, PublishPdfRequest
from hse_doc_studio.infra.compile.build_anchors import fresh_positions, pdf_pages, publish_anchors
from hse_doc_studio.infra.jobs.artifact_store import LocalDiskArtifactStore
from pypdf import PdfWriter

A4_BP = (595.2756, 841.8898)
HEADER = "hsepos 1 39158276 55380990"
# Линия научрука: 169,5 мм от левого края, 186,9 мм от верха, ширина 25,5 мм.
SUPERVISOR = "sign supervisor - 1 31606323 20530125 4754934"


def pdf_bytes(pages: int = 1, *, rotate: int = 0, size: tuple[float, float] = A4_BP) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        page = writer.add_blank_page(width=size[0], height=size[1])
        if rotate:
            page.rotate(rotate)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def write_build(
    build: Path,
    *,
    positions: str | None = f"{HEADER}\n{SUPERVISOR}\n",
    recorded: bool = True,
    pdf: bytes | None = None,
    stem: str = "main",
) -> None:
    build.mkdir(parents=True, exist_ok=True)
    if positions is not None:
        (build / f"{stem}.hsepos").write_text(positions, encoding="ascii")
    lines = ["PWD /work/tz", "INPUT /usr/share/texmf/article.cls", f"OUTPUT .build/tz/{stem}.log"]
    if recorded:
        lines.append(f"OUTPUT .build/tz/{stem}.hsepos")
    (build / f"{stem}.fls").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if pdf is not None:
        (build / f"{stem}.pdf").write_bytes(pdf)


def read_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


# --- свежесть ---


def test__fresh_positions__written_by_last_tex_pass__found(tmp_path: Path) -> None:
    write_build(tmp_path)

    assert fresh_positions(tmp_path, "main") == tmp_path / "main.hsepos"


def test__fresh_positions__left_from_older_build__none(tmp_path: Path) -> None:
    # Шаблон перестал подключать макросы: файл остался, последний проход TeX его не открывал.
    write_build(tmp_path, recorded=False)

    assert fresh_positions(tmp_path, "main") is None


def test__fresh_positions__no_recorder_file__none(tmp_path: Path) -> None:
    write_build(tmp_path)
    (tmp_path / "main.fls").unlink()

    assert fresh_positions(tmp_path, "main") is None


def test__fresh_positions__symlink__none(tmp_path: Path) -> None:
    write_build(tmp_path, positions=None)
    target = tmp_path / "elsewhere"
    target.write_text(f"{HEADER}\n", encoding="ascii")
    (tmp_path / "main.hsepos").symlink_to(target)

    assert fresh_positions(tmp_path, "main") is None


def test__fresh_positions__other_document_output__none(tmp_path: Path) -> None:
    write_build(tmp_path, stem="other")
    write_build(tmp_path, recorded=False)

    assert fresh_positions(tmp_path, "main") is None


# --- публикация ---


def test__publish_anchors__fresh_positions__json_bound_to_pdf_sha(tmp_path: Path) -> None:
    pdf = pdf_bytes()
    write_build(tmp_path, pdf=pdf)

    anchors = publish_anchors(tmp_path, "main", tmp_path / "main.pdf", PositionsSource.tex)

    assert anchors is not None
    body = read_json(tmp_path / "main.anchors.json")
    assert body["pdf_sha256"] == hashlib.sha256(pdf).hexdigest()
    assert body["anchors"] == [
        {"id": "supervisor", "kind": "sign", "page": 1, "x_mm": 169.5, "y_mm": 186.9, "width_mm": 25.5}
    ]


def test__publish_anchors__stale_positions__previous_json_removed(tmp_path: Path) -> None:
    write_build(tmp_path, pdf=pdf_bytes())
    publish_anchors(tmp_path, "main", tmp_path / "main.pdf", PositionsSource.tex)
    write_build(tmp_path, recorded=False, pdf=pdf_bytes(2))

    anchors = publish_anchors(tmp_path, "main", tmp_path / "main.pdf", PositionsSource.tex)

    assert anchors is None
    assert not (tmp_path / "main.anchors.json").exists()


def test__publish_anchors__no_positions__previous_json_removed(tmp_path: Path) -> None:
    write_build(tmp_path, pdf=pdf_bytes())
    publish_anchors(tmp_path, "main", tmp_path / "main.pdf", PositionsSource.tex)
    (tmp_path / "main.hsepos").unlink()

    assert publish_anchors(tmp_path, "main", tmp_path / "main.pdf", PositionsSource.tex) is None
    assert not (tmp_path / "main.anchors.json").exists()


def test__publish_anchors__runner_upload__trusted_without_recorder(tmp_path: Path) -> None:
    write_build(tmp_path, pdf=pdf_bytes())
    (tmp_path / "main.fls").unlink()

    anchors = publish_anchors(tmp_path, "main", tmp_path / "main.pdf", PositionsSource.runner)

    assert anchors is not None
    assert [a.id for a in anchors.anchors] == ["supervisor"]


def test__publish_anchors__runner_without_file__stale_positions_and_json_removed(tmp_path: Path) -> None:
    # Раннер прежней версии: файл позиций в `.build` от прошлой сборки, свежего нет.
    write_build(tmp_path, pdf=pdf_bytes())
    publish_anchors(tmp_path, "main", tmp_path / "main.pdf", PositionsSource.runner)

    anchors = publish_anchors(tmp_path, "main", tmp_path / "main.pdf", PositionsSource.absent)

    assert anchors is None
    assert not (tmp_path / "main.anchors.json").exists()
    assert not (tmp_path / "main.hsepos").exists()


def test__publish_anchors__unknown_format__unknown_not_empty(tmp_path: Path) -> None:
    write_build(tmp_path, positions="hsepos 9 1 1\n", pdf=pdf_bytes())

    assert publish_anchors(tmp_path, "main", tmp_path / "main.pdf", PositionsSource.tex) is None
    assert not (tmp_path / "main.anchors.json").exists()


def test__publish_anchors__unreadable_pdf__unknown(tmp_path: Path) -> None:
    write_build(tmp_path, pdf=b"%PDF-1.5 broken")

    assert publish_anchors(tmp_path, "main", tmp_path / "main.pdf", PositionsSource.tex) is None
    assert not (tmp_path / "main.anchors.json").exists()


def test__publish_anchors__no_pdf__unknown(tmp_path: Path) -> None:
    write_build(tmp_path)

    assert publish_anchors(tmp_path, "main", tmp_path / "main.pdf", PositionsSource.tex) is None


def test__publish_anchors__template_without_lines__known_and_empty(tmp_path: Path) -> None:
    write_build(tmp_path, positions=f"{HEADER}\n", pdf=pdf_bytes())

    anchors = publish_anchors(tmp_path, "main", tmp_path / "main.pdf", PositionsSource.tex)

    assert anchors is not None
    assert anchors.anchors == ()
    assert read_json(tmp_path / "main.anchors.json")["anchors"] == []


def test__pdf_pages__size_in_mm_and_rotation(tmp_path: Path) -> None:
    path = tmp_path / "x.pdf"
    path.write_bytes(pdf_bytes(2, rotate=90))

    pages = pdf_pages(path)

    assert len(pages) == 2
    assert round(pages[0].width_mm, 1) == 210.0
    assert round(pages[0].height_mm, 1) == 297.0
    assert pages[0].rotate == 90


# --- через LocalDiskArtifactStore.publish_pdf ---


def _request(workspace: Path, positions: PositionsSource = PositionsSource.tex) -> PublishPdfRequest:
    return PublishPdfRequest(
        workspace=workspace, doc_id="tz", job_id=uuid4(), source_file="tz/main.tex", positions=positions
    )


@pytest.mark.asyncio
async def test__publish_pdf__anchors_next_to_positions_bound_to_published_pdf(tmp_path: Path) -> None:
    pdf = pdf_bytes()
    build = tmp_path / "tz/.build/tz"
    write_build(build, pdf=pdf)

    outcome = await LocalDiskArtifactStore().publish_pdf(_request(tmp_path))

    assert outcome.replaced is True
    assert (tmp_path / "tz/main.pdf").read_bytes() == pdf
    assert read_json(build / "main.anchors.json")["pdf_sha256"] == hashlib.sha256(pdf).hexdigest()


@pytest.mark.asyncio
async def test__publish_pdf__move_failed__anchors_of_the_build_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hse_doc_studio.infra.jobs import artifact_store  # noqa: PLC0415

    pdf = pdf_bytes()
    build = tmp_path / "tz/.build/tz"
    write_build(build, pdf=pdf)
    (tmp_path / "tz/main.pdf").write_bytes(b"old")

    def locked(src: str, dst: str) -> None:
        raise PermissionError("open in a viewer")

    monkeypatch.setattr(artifact_store.shutil, "move", locked)

    outcome = await LocalDiskArtifactStore(move_attempts=1, retry_delay_s=0).publish_pdf(_request(tmp_path))

    assert outcome.replaced is False
    # Якоря от свежего PDF в `.build`, а не от старого рядом с исходником: источник подписи их не получит.
    assert read_json(build / "main.anchors.json")["pdf_sha256"] == hashlib.sha256(pdf).hexdigest()


@pytest.mark.asyncio
async def test__publish_pdf__failed_build_left_partial_positions__next_old_runner_build_has_no_anchors(
    tmp_path: Path,
) -> None:
    build = tmp_path / "tz/.build/tz"
    write_build(build, pdf=pdf_bytes())
    await LocalDiskArtifactStore().publish_pdf(_request(tmp_path))
    write_build(build, pdf=pdf_bytes(2), positions=f"{HEADER}\nsign author - 1 1 1 1\n")

    await LocalDiskArtifactStore().publish_pdf(_request(tmp_path, PositionsSource.absent))

    assert not (build / "main.anchors.json").exists()
