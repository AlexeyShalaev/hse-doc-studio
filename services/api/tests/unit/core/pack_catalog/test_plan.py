"""План «Применить» (template-studio.md, 10.3 и 10.4): что появится, что пропускается, что не даёт применить."""

from __future__ import annotations

from hse_doc_studio.core.catalog import PackOrigin, PackOriginKind
from hse_doc_studio.core.pack_catalog.entities import InspectedPack, InspectedTemplate, InspectedTree, InspectedVersion
from hse_doc_studio.core.pack_catalog.plan import (
    Blocker,
    ExistingPack,
    PackConflict,
    Verdict,
    plan_catalog,
)
from hse_doc_studio.core.template_versions import MANIFEST_FORMAT

D1 = "sha256:" + "1" * 64
D2 = "sha256:" + "2" * 64


def _v(version: str, **kw: object) -> InspectedVersion:
    data: dict[str, object] = {
        "template": "report",
        "version": version,
        "released": True,
        "registry_digest": D1,
        "digest": D1,
        "readable": True,
    }
    data.update(kw)
    return InspectedVersion(**data)  # type: ignore[arg-type]


def _tree(*versions: InspectedVersion, pack: str = "acme", readable: bool = True) -> InspectedTree:
    return InspectedTree(
        packs=(
            InspectedPack(
                id=pack,
                path=pack,
                name={"ru": "Acme"},
                templates=(InspectedTemplate(id="report", path=f"{pack}/templates/report", versions=versions),),
                readable=readable,
            ),
        )
    )


def _plan(tree: InspectedTree, *, existing=None, digests=None, replace_builtin=False, app="1.0.0"):  # type: ignore[no-untyped-def]
    digests = digests or {}
    return plan_catalog(
        tree,
        revision="abc",
        source_id="src",
        replace_builtin=replace_builtin,
        existing=existing or {},
        existing_digest=lambda p, t, v: digests.get((p, t, v)),
        app_version=app,
        labels={"other": "Архив кафедры"},
    )


def _verdicts(plan) -> dict[str, Verdict]:  # type: ignore[no-untyped-def]
    return {v.version: v.verdict for p in plan.packs for v in p.versions}


def test__released_new_versions_appear_and_drafts_do_not() -> None:
    plan = _plan(_tree(_v("2026.1.0"), _v("2026.1.1", released=False, registry_digest=None)))

    assert _verdicts(plan) == {"2026.1.0": Verdict.new, "2026.1.1": Verdict.unreleased}
    assert plan.ok
    assert plan.new_count == 1


def test__same_number_other_digest__version_changed_blocks() -> None:
    plan = _plan(_tree(_v("2026.1.0"), _v("2026.1.1")), digests={("acme", "report", "2026.1.0"): D2})

    assert _verdicts(plan)["2026.1.0"] is Verdict.changed
    assert plan.blockers == (Blocker.version_changed,)


def test__same_digest__present_even_with_new_lint_errors() -> None:
    plan = _plan(_tree(_v("2026.1.0", errors=("новое правило линтера",))), digests={("acme", "report", "2026.1.0"): D1})

    assert _verdicts(plan)["2026.1.0"] is Verdict.present
    assert plan.ok


def test__too_new_for_this_studio__skipped_not_blocking() -> None:
    plan = _plan(
        _tree(_v("2026.1.0", min_studio="9.0.0"), _v("2026.1.1", manifest_format=MANIFEST_FORMAT + 1)),
    )

    assert set(_verdicts(plan).values()) == {Verdict.incompatible}
    assert plan.ok
    assert plan.new_count == 0


def test__lint_errors_or_dir_changed_after_release__invalid_blocks() -> None:
    plan = _plan(_tree(_v("2026.1.0", errors=("files/x.tex не найден",)), _v("2026.1.1", digest=D2)))

    assert set(_verdicts(plan).values()) == {Verdict.invalid}
    assert Blocker.version_invalid in plan.blockers


def test__builtin_pack__needs_replace_builtin() -> None:
    existing = {"acme": ExistingPack(origin=PackOrigin())}

    refused = _plan(_tree(_v("2026.1.0")), existing=existing)
    allowed = _plan(_tree(_v("2026.1.0")), existing=existing, replace_builtin=True)

    assert refused.packs[0].conflict is PackConflict.builtin
    assert refused.blockers == (Blocker.pack_conflict,)
    assert allowed.ok
    assert allowed.packs[0].replaces_builtin


def test__pack_of_another_live_source__conflict_names_it() -> None:
    origin = PackOrigin(kind=PackOriginKind.subscribed, source_id="other", label="old")

    live = _plan(_tree(_v("2026.1.0")), existing={"acme": ExistingPack(origin=origin, source_alive=True)})
    removed = _plan(_tree(_v("2026.1.0")), existing={"acme": ExistingPack(origin=origin, source_alive=False)})
    own = _plan(
        _tree(_v("2026.1.0")),
        existing={"acme": ExistingPack(origin=PackOrigin(kind=PackOriginKind.subscribed, source_id="src"))},
    )

    assert live.packs[0].conflict is PackConflict.other_source
    assert live.packs[0].conflict_with == "Архив кафедры"
    assert removed.ok
    assert own.ok


def test__unsafe_or_unreadable_pack__invalid_conflict_and_empty_tree_blocks() -> None:
    assert _plan(_tree(_v("2026.1.0"), pack="../x")).packs[0].conflict is PackConflict.invalid
    assert _plan(_tree(_v("2026.1.0"), readable=False)).packs[0].conflict is PackConflict.invalid
    assert _plan(InspectedTree()).blockers == (Blocker.no_packs,)
