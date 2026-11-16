"""Кэш, ETag и ключ ответа результата (`core/pack_studio/outcome/serving.py`) и выбор манифестов для `revision`."""

from __future__ import annotations

import pytest
from hse_doc_studio.core.pack_studio.outcome.revision import example_file_names, is_manifest_path, revision_of
from hse_doc_studio.core.pack_studio.outcome.serving import LruCache, etag_matches, etag_of, request_key

# ── LRU ──────────────────────────────────────────────────────────────────────


def test__lru__evicts_the_least_recently_read_entry() -> None:
    cache: LruCache[int] = LruCache(2)
    cache.put("a", 1)
    cache.put("b", 2)

    assert cache.get("a") == 1  # `a` прочитан и стал свежим
    cache.put("c", 3)

    assert cache.get("b") is None
    assert (cache.get("a"), cache.get("c")) == (1, 3)
    assert len(cache) == 2


def test__lru__replacing_a_key_does_not_grow_the_cache_or_the_cost() -> None:
    cache: LruCache[str] = LruCache(4, max_cost=100)
    cache.put("a", "x", cost=40)
    cache.put("a", "y", cost=10)

    assert (len(cache), cache.cost, cache.get("a")) == (1, 10, "y")


def test__lru__cost_limit_drops_old_entries_and_skips_an_entry_bigger_than_the_limit() -> None:
    cache: LruCache[str] = LruCache(10, max_cost=100)
    cache.put("a", "a", cost=60)
    cache.put("b", "b", cost=60)

    assert "a" not in cache
    assert cache.cost == 60
    cache.put("huge", "h", cost=101)
    assert "huge" not in cache
    assert "b" in cache


def test__lru__miss_clear_and_bad_size() -> None:
    cache: LruCache[int] = LruCache(1)
    cache.put("a", 1)
    assert cache.get("zzz") is None
    cache.clear()
    assert (len(cache), cache.cost, cache.get("a")) == (0, 0, None)
    with pytest.raises(ValueError, match="positive"):
        LruCache(0)


# ── ETag ─────────────────────────────────────────────────────────────────────


def test__request_key__does_not_depend_on_the_order_of_keys() -> None:
    a = request_key({"inputs": {"kind": "project", "lang": "ru"}, "state": "head"})
    b = request_key({"state": "head", "inputs": {"lang": "ru", "kind": "project"}})

    assert a == b
    assert request_key({"inputs": {"kind": "research"}}) != request_key({"inputs": {"kind": "project"}})


def test__etag__is_a_quoted_hash_of_the_key_and_differs_per_key() -> None:
    etag = etag_of("a")

    assert etag.startswith('"')
    assert etag.endswith('"')
    assert len(etag) == 26
    assert etag == etag_of("a")
    assert etag != etag_of("b")


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, False),
        ("", False),
        ('"other"', False),
        ("{etag}", True),
        ("W/{etag}", True),
        ('"x", {etag}', True),
        ('"x",W/{etag} , "y"', True),
        ("*", True),
        ("{etag}x", False),
    ],
)
def test__etag_matches__if_none_match_forms(header: str | None, expected: bool) -> None:
    etag = etag_of("key")

    assert etag_matches(header.format(etag=etag) if header else header, etag) is expected


# ── манифесты для revision ───────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("version.yaml", True),
        ("files/thesis/doc.yaml", True),
        ("files/thesis/main.tex", False),
        ("files/doc.yaml", False),
        ("files/a/b/doc.yaml", False),
        ("sub/version.yaml", False),
        ("checks/rules.yaml", False),
    ],
)
def test__is_manifest_path(path: str, expected: bool) -> None:
    assert is_manifest_path(path) is expected


def test__example_file_names__file_examples_only() -> None:
    assert example_file_names("ivanov") == ("examples/ivanov.yaml", "examples/ivanov.yml")
    assert example_file_names("auto:normal") == ()
    assert example_file_names("") == ()
    assert example_file_names("../x") == ()


def test__revision__changes_with_any_manifest_text_and_not_with_the_order() -> None:
    base = {"version.yaml": "a", "files/x/doc.yaml": "b"}

    assert revision_of(base) == revision_of(dict(reversed(list(base.items()))))
    assert revision_of(base) != revision_of({**base, "files/x/doc.yaml": "c"})
    assert revision_of(base) != revision_of({**base, "examples/e.yaml": "d"})
