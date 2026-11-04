"""FsJobLogSink: голова и скользящий хвост, чтение всех попыток, живое чтение с смещения."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from hse_doc_studio.infra.jobs.storage_fs import LOG_GAP_MARK, FsJobLogSink


async def test__read__small_log__returned_whole(tmp_path: Path) -> None:
    sink, job = FsJobLogSink(tmp_path), uuid4()
    await sink.append(job, 1, 0, ["a", "b"])
    await sink.append(job, 1, 1, ["c"])

    assert await sink.read(job, max_bytes=1000) == "a\nb\nc\n"


async def test__read__unknown_job__empty(tmp_path: Path) -> None:
    assert await FsJobLogSink(tmp_path).read(uuid4(), max_bytes=1000) == ""


async def test__append__duplicate_seq__ignored(tmp_path: Path) -> None:
    sink, job = FsJobLogSink(tmp_path), uuid4()
    assert await sink.append(job, 1, 0, ["a"]) is True
    assert await sink.append(job, 1, 0, ["a"]) is False

    assert await sink.read(job, max_bytes=1000) == "a\n"


async def test__append__over_limit__tail_keeps_the_end_of_the_log(tmp_path: Path) -> None:
    sink, job = FsJobLogSink(tmp_path, max_bytes=20, tail_bytes=40), uuid4()
    for seq in range(30):
        await sink.append(job, 1, seq, [f"line {seq:02d}"])

    text = await sink.read(job, max_bytes=10_000)

    assert text.startswith("line 00\n")
    assert LOG_GAP_MARK in text
    assert text.endswith("line 29\n")
    assert "line 15\n" not in text


async def test__read__several_attempts__joined_in_order_with_headers(tmp_path: Path) -> None:
    sink, job = FsJobLogSink(tmp_path), uuid4()
    await sink.append(job, 1, 0, ["first try"])
    await sink.append(job, 2, 0, ["second try"])

    text = await sink.read(job, max_bytes=1000)

    assert text.index("first try") < text.index("second try")
    assert "attempt 2" in text


async def test__read__over_max_bytes__keeps_the_end(tmp_path: Path) -> None:
    sink, job = FsJobLogSink(tmp_path), uuid4()
    await sink.append(job, 1, 0, ["x" * 100, "THE END"])

    assert (await sink.read(job, max_bytes=20)).endswith("THE END\n")


async def test__read_from__returns_only_whole_new_lines(tmp_path: Path) -> None:
    sink, job = FsJobLogSink(tmp_path), uuid4()
    await sink.append(job, 1, 0, ["a", "b"])
    text, offset = await sink.read_from(job, 1, 0)
    assert (text, offset) == ("a\nb\n", 4)

    await sink.append(job, 1, 1, ["c"])
    assert await sink.read_from(job, 1, offset) == ("c\n", 6)
    assert await sink.read_from(job, 1, 6) == ("", 6)
    assert await sink.read_from(job, 9, 0) == ("", 0)
