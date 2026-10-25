from __future__ import annotations

import io
import zipfile

import pytest
from hse_doc_studio.core.enums import ConflictResolution, TemplateFileAction
from hse_doc_studio.core.template_update.entities import FileWriteKind, resolve_op
from hse_doc_studio.core.template_update.planner import MergeOutcome, PlanInput, plan_files, plan_fingerprint
from hse_doc_studio.core.template_update.text import (
    has_conflict_markers,
    is_binary,
    restore_text_style,
    same_content,
    unified_diff,
)

pytestmark = pytest.mark.unit


def _fake_merge(ours: bytes, base: bytes, theirs: bytes) -> MergeOutcome:
    """Сливает, только если одна из сторон не менялась построчно в конце; иначе конфликт."""
    if ours.startswith(base.rstrip(b"\n")) and theirs.startswith(base.rstrip(b"\n")):
        return MergeOutcome(ours + theirs[len(base) :], 0)
    return MergeOutcome(b"<<<<<<< ours\n" + ours + b"=======\n" + theirs + b">>>>>>> theirs\n", 1)


def _plan(base: dict[str, bytes], theirs: dict[str, bytes], ours: dict[str, bytes], **kw):  # type: ignore[no-untyped-def]
    ops = plan_files(PlanInput(base=base, theirs=theirs, ours=ours, **kw), _fake_merge)
    return {op.path: op for op in ops}


def test__template_unchanged__nothing_to_do_even_if_user_edited() -> None:
    assert _plan({"a.tex": b"x\n"}, {"a.tex": b"x\n"}, {"a.tex": b"mine\n"}) == {}


def test__untouched_file__takes_the_template() -> None:
    ops = _plan({"a.tex": b"x\n"}, {"a.tex": b"y\n"}, {"a.tex": b"x\n"})
    assert ops["a.tex"].action == TemplateFileAction.update


def test__user_already_has_new_content__nothing_to_do() -> None:
    assert _plan({"a.tex": b"x\n"}, {"a.tex": b"y\n"}, {"a.tex": b"y\n"}) == {}


def test__both_changed__merge_or_conflict() -> None:
    ops = _plan(
        {"m.tex": b"base\n", "c.tex": b"base\n"},
        {"m.tex": b"base\ntheirs\n", "c.tex": b"other\n"},
        {"m.tex": b"base\nmine\n", "c.tex": b"mine\n"},
    )
    assert ops["m.tex"].action == TemplateFileAction.merge
    assert ops["c.tex"].action == TemplateFileAction.conflict
    assert ops["c.tex"].conflicts == 1


def test__new_removed_and_user_deleted_files() -> None:
    ops = _plan(
        {"gone.tex": b"g\n", "edited.tex": b"e\n", "deleted_by_me.tex": b"d\n"},
        {"new.tex": b"n\n", "deleted_by_me.tex": b"d2\n"},
        {"gone.tex": b"g\n", "edited.tex": b"mine\n"},
    )
    assert ops["new.tex"].action == TemplateFileAction.add
    assert ops["gone.tex"].action == TemplateFileAction.delete
    assert ops["edited.tex"].action == TemplateFileAction.orphan
    assert ops["deleted_by_me.tex"].action == TemplateFileAction.user_deleted


def test__new_template_file_colliding_with_a_user_file__conflict() -> None:
    ops = _plan({}, {"x.tex": b"template\n"}, {"x.tex": b"mine\n"})
    assert ops["x.tex"].action == TemplateFileAction.conflict


def test__binary_both_changed__conflict_without_markers() -> None:
    ops = _plan({"l.png": b"\x00a"}, {"l.png": b"\x00b"}, {"l.png": b"\x00c"})
    op = ops["l.png"]
    assert op.action == TemplateFileAction.conflict
    assert op.binary
    assert op.allowed_resolutions() == (ConflictResolution.mine, ConflictResolution.theirs)
    assert resolve_op(op, ConflictResolution.markers) is None  # недопустимо — остаётся «моё»


def test__ignored_path__never_touched() -> None:
    ops = _plan({"a.tex": b"x\n"}, {"a.tex": b"y\n"}, {"a.tex": b"x\n"}, ignored=frozenset({"a.tex"}))
    assert ops["a.tex"].action == TemplateFileAction.ignored
    assert resolve_op(ops["a.tex"], None) is None


def test__crlf_and_bom_are_not_edits() -> None:
    ops = _plan({"a.tex": b"x\ny\n"}, {"a.tex": b"x\nz\n"}, {"a.tex": b"\xef\xbb\xbfx\r\ny\r\n"})
    op = ops["a.tex"]
    assert op.action == TemplateFileAction.update
    write = resolve_op(op, None)
    assert write is not None
    assert write.content == b"\xef\xbb\xbfx\r\nz\r\n"  # концы строк и BOM пользователя сохранены


def _zip(members: dict[str, bytes], level: int) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED, compresslevel=level) as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test__pptx_compared_by_members_not_by_bytes() -> None:
    members = {"ppt/slides/slide1.xml": b"<a/>" * 200}
    first, second = _zip(members, 1), _zip(members, 9)
    assert first != second
    assert same_content("p.pptx", first, second)
    assert not same_content("p.pptx", first, _zip({"ppt/slides/slide1.xml": b"<b/>"}, 1))
    assert is_binary("p.pptx", first)


def test__resolutions_map_to_writes() -> None:
    op = _plan({"c.tex": b"base\n"}, {"c.tex": b"other\n"}, {"c.tex": b"mine\n"})["c.tex"]
    assert resolve_op(op, None) is None
    assert resolve_op(op, ConflictResolution.mine) is None
    theirs = resolve_op(op, ConflictResolution.theirs)
    assert theirs is not None
    assert theirs.content == b"other\n"
    markers = resolve_op(op, ConflictResolution.markers)
    assert markers is not None
    assert markers.with_markers
    assert has_conflict_markers(markers.content or b"")

    delete = resolve_op(_plan({"g.tex": b"g\n"}, {}, {"g.tex": b"g\n"})["g.tex"], None)
    assert delete is not None
    assert delete.kind == FileWriteKind.delete


def test__fingerprint_depends_on_my_files_not_on_unrelated_ones() -> None:
    base, theirs = {"a.tex": b"x\n", "b.tex": b"same\n"}, {"a.tex": b"y\n", "b.tex": b"same\n"}
    first = plan_files(PlanInput(base, theirs, {"a.tex": b"x\n", "b.tex": b"same\n"}), _fake_merge)
    unrelated = plan_files(PlanInput(base, theirs, {"a.tex": b"x\n", "b.tex": b"edited\n"}), _fake_merge)
    related = plan_files(PlanInput(base, theirs, {"a.tex": b"x2\n", "b.tex": b"same\n"}), _fake_merge)

    def fp(ops):  # type: ignore[no-untyped-def]
        return plan_fingerprint(ops, to_version="2026.1.1", base_digest="d")

    assert fp(first) == fp(unrelated)
    assert fp(first) != fp(related)


def test__text_helpers() -> None:
    assert restore_text_style(b"a\nb\n", b"x\r\n") == b"a\r\nb\r\n"
    assert restore_text_style(b"a\n", None) == b"a\n"
    assert has_conflict_markers(b"x\n<<<<<<< mine\ny\n")
    assert not has_conflict_markers(b"<<<<<<<< not a marker\n")
    patch, truncated = unified_diff("a.tex", b"x\n", b"y\n", "old", "new")
    assert "-x" in patch
    assert "+y" in patch
    assert not truncated
