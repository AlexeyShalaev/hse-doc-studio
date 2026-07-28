from __future__ import annotations

import time
from typing import Any

import pytest
from hse_doc_studio.core.fonts.entities import FontCatalog, FontCatalogFile, FontCatalogItem
from hse_doc_studio.infra.fonts.gfonts_marketplace import GoogleFontsMarketplace, build_index

pytestmark = pytest.mark.unit


def _tree(*paths: str) -> dict[str, Any]:
    return {"tree": [{"path": p} for p in paths]}


def _meta(*families: tuple[str, str, list[str]]) -> dict[str, Any]:
    return {"familyMetadataList": [{"family": f, "category": c, "subsets": s} for f, c, s in families]}


def test__build_index__static_and_variable_font_files__keeps_static_drops_variable_and_unlisted() -> None:
    tree = _tree(
        "ofl/ptserif/PT_Serif-Web-Regular.ttf",
        "ofl/ptserif/PT_Serif-Web-Bold.ttf",
        "ofl/alegreya/Alegreya[wght].ttf",  # variable → excluded
        "ofl/ptserif/OFL.txt",  # non-font → ignored
        "axisregistry/whatever.ttf",  # not under a license dir → ignored
    )
    meta = _meta(
        ("PT Serif", "Serif", ["latin", "cyrillic"]),
        ("Alegreya", "Serif", ["latin", "cyrillic"]),  # variable-only → not in index
        ("Ghost Font", "Serif", ["latin"]),  # no files in tree → not in index
    )
    index = build_index(tree, meta)
    assert set(index.keys()) == {"ptserif"}
    entry = index["ptserif"]
    assert entry.family == "PT Serif"
    assert entry.category == "serif"
    assert entry.cyrillic is True
    assert [f.filename for f in entry.files] == ["PT_Serif-Web-Bold.ttf", "PT_Serif-Web-Regular.ttf"]
    assert entry.files[0].url.startswith("https://raw.githubusercontent.com/google/fonts/main/ofl/ptserif/")


def test__build_index__category_and_subsets__normalises_category_and_sets_cyrillic_flag() -> None:
    tree = _tree("ofl/firasans/FiraSans-Regular.ttf", "ofl/roboto/Roboto-Regular.ttf")
    meta = _meta(
        ("Fira Sans", "Sans Serif", ["latin", "cyrillic"]),
        ("Roboto", "Sans Serif", ["latin"]),  # no cyrillic
    )
    index = build_index(tree, meta)
    assert index["firasans"].category == "sans-serif"
    assert index["firasans"].cyrillic is True
    assert index["roboto"].cyrillic is False


def _market_with_index(
    monkeypatch: pytest.MonkeyPatch, tree: dict[str, Any], meta: dict[str, Any]
) -> GoogleFontsMarketplace:
    mp = GoogleFontsMarketplace(
        "meta-url", "tree-url", ttl_s=999.0, request_timeout_s=5.0, fallback=FontCatalog(items=())
    )
    # Pre-seed the cached index so search() doesn't hit the network.
    mp._index = build_index(tree, meta)  # noqa: SLF001 — test seam
    mp._built_at = time.monotonic()  # noqa: SLF001
    return mp


@pytest.fixture
def marketplace(monkeypatch: pytest.MonkeyPatch) -> GoogleFontsMarketplace:
    tree = _tree(
        "ofl/ptserif/PT_Serif-Web-Regular.ttf",
        "ofl/firasans/FiraSans-Regular.ttf",
        "ofl/ibmplexmono/IBMPlexMono-Regular.ttf",
        "ofl/roboto/Roboto-Regular.ttf",
    )
    meta = _meta(
        ("PT Serif", "Serif", ["cyrillic"]),
        ("Fira Sans", "Sans Serif", ["cyrillic"]),
        ("IBM Plex Mono", "Monospace", ["cyrillic"]),
        ("Roboto", "Sans Serif", ["latin"]),  # not cyrillic
    )
    return _market_with_index(monkeypatch, tree, meta)


@pytest.mark.parametrize(
    ("query", "family", "cyrillic_only", "limit", "expected_ids"),
    [
        pytest.param("", None, True, 50, {"ptserif", "firasans", "ibmplexmono"}, id="cyrillic_only-excludes-roboto"),
        pytest.param("", "serif", True, 50, {"ptserif"}, id="family-filter-narrows-to-serif"),
        pytest.param("fira", None, False, 50, {"firasans"}, id="name-query-matches-by-substring"),
    ],
)
async def test__search__cyrillic_family_and_name_filters__returns_expected_ids(
    marketplace: GoogleFontsMarketplace,
    query: str,
    family: str | None,
    cyrillic_only: bool,  # noqa: FBT001
    limit: int,
    expected_ids: set[str],
) -> None:
    result = await marketplace.search(query, family, cyrillic_only=cyrillic_only, limit=limit, offset=0)

    assert {f.id for f in result.items} == expected_ids


async def test__search__limit_smaller_than_total_matches__total_reflects_all_matches_items_are_the_page(
    marketplace: GoogleFontsMarketplace,
) -> None:
    page = await marketplace.search("", None, cyrillic_only=True, limit=2, offset=0)

    assert page.total == 3
    assert len(page.items) == 2


async def test__google_fonts_marketplace_get_files__known_and_unknown_id__returns_files_or_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tree = _tree("ofl/ptserif/PT_Serif-Web-Regular.ttf")
    meta = _meta(("PT Serif", "Serif", ["cyrillic"]))
    mp = _market_with_index(monkeypatch, tree, meta)
    files = await mp.get_files("ptserif")
    assert [f.filename for f in files] == ["PT_Serif-Web-Regular.ttf"]
    assert await mp.get_files("does-not-exist") == []


async def test__google_fonts_marketplace_search__remote_fetch_fails__falls_back_to_bundled_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fallback = FontCatalog(
        items=(
            FontCatalogItem(
                id="pt-serif",
                label="PT Serif",
                family="serif",
                description="",
                license="OFL-1.1",
                files=(FontCatalogFile(filename="PT_Serif-Web-Regular.ttf", url="https://x/r.ttf"),),
            ),
        )
    )
    mp = GoogleFontsMarketplace("meta-url", "tree-url", ttl_s=999.0, request_timeout_s=5.0, fallback=fallback)

    async def _boom(_url: str) -> dict[str, Any]:
        raise RuntimeError("network down")

    monkeypatch.setattr(mp, "_fetch_json", _boom)
    res = await mp.search("", None, cyrillic_only=True, limit=50, offset=0)
    assert {f.id for f in res.items} == {"pt-serif"}  # served from the bundled fallback
    assert (await mp.get_files("pt-serif"))[0].filename == "PT_Serif-Web-Regular.ttf"
