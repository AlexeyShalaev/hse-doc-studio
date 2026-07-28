"""Pure HTML parsers for the HSE staff directory.

The backend ships no HTML-parser dependency, so these use stdlib ``re`` +
``html.unescape`` (the same approach as the Ollama registry scraper). The HSE
markup is server-rendered and stable; every regex here is anchored on durable
structure (the ``/org/persons/<id>`` card anchor, the ``og:*`` meta tags, the
``hse-value`` filter items) rather than volatile CSS classes.

All functions are pure and side-effect free so they can be unit-tested against
saved page fixtures.
"""

from __future__ import annotations

import html as html_lib
import re

from hse_doc_studio.core.hse_persons.entities import (
    HseFacetOption,
    HseFacets,
    HsePersonDetail,
    HsePersonSummary,
)

_SITE_BASE = "https://www.hse.ru"

# ── listing cards ─────────────────────────────────────────────────────────────
# <a href="/org/persons/728931370" class="link link_dark large b">
#   <div class="g-pic …" title="Абаева Фатима Руслановна" …></div>ФИО</a>
# (the avatar URL is deterministic — /org/persons/cimage/<id> — so it isn't parsed).
_CARD_RE = re.compile(
    r'<a href="/org/persons/(?P<id>\d+)" class="link link_dark large b">\s*'
    r'<div class="g-pic[^"]*" title="(?P<name>[^"]+)"',
    re.S,
)
_AFFIL_RE = re.compile(r'<p class="with-indent7">(?P<affil>.*?)</p>', re.S)
_AFFIL_WINDOW = 1400

# ── profile page ──────────────────────────────────────────────────────────────
_OG_TITLE_RE = re.compile(r'<meta property="og:title"\s+content="([^"]*)"')
_OG_DESC_RE = re.compile(r'<meta property="og:description"\s+content="([^"]*)"')
# A comma-segment that carries a phone/extension (≥5 consecutive digits) is not a
# department — drop it. Real unit names never contain a 5-digit run.
_PHONE_HINT_RE = re.compile(r"\d{5,}")
_ORG_HINT = "Национальный исследовательский университет"
# «кандидат технических наук», «доктор экономических наук», «PhD», «Ph.D.»
_DEGREE_RE = re.compile(
    r"(кандидат|доктор)\s+(?:[а-яё-]+\s+){0,2}наук|\bPhD\b|\bPh\.\s?D\.?",
    re.IGNORECASE,
)

# ── filter sidebar vocabulary ─────────────────────────────────────────────────
_HSE_VALUE_RE = re.compile(r'<li hse-value="(?P<val>\d+)"[^>]*>(?P<label>.*?)(?:<ul|<li|</li>)', re.S)
_CAMPUS_LABEL_PREFIX = "Кампус:"
# Match ONLY the input tag (no trailing capture) so finditer never swallows the
# next option; the label (a following <label>…</label>) is read from a bounded
# window and cut at the next control so options don't bleed together.
_RADIO_LABEL_WINDOW = 220
_LABEL_STOP_RE = re.compile(r"<input|<li|</li|<div")


def _clean(text: str) -> str:
    """Strip tags, unescape entities and collapse whitespace."""
    stripped = re.sub(r"<[^>]+>", " ", text)
    return html_lib.unescape(re.sub(r"\s+", " ", stripped)).strip()


def parse_cards(html: str) -> list[HsePersonSummary]:
    """Parse the person cards from a directory listing page."""
    out: list[HsePersonSummary] = []
    seen: set[str] = set()
    for m in _CARD_RE.finditer(html):
        pid = m.group("id")
        if pid in seen:
            continue
        seen.add(pid)
        affil_m = _AFFIL_RE.search(html, m.end(), m.end() + _AFFIL_WINDOW)
        out.append(
            HsePersonSummary(
                id=pid,
                full_name=html_lib.unescape(m.group("name").strip()),
                profile_url=f"{_SITE_BASE}/org/persons/{pid}",
                photo_url=f"{_SITE_BASE}/org/persons/cimage/{pid}",
                affiliation=_clean(affil_m.group("affil")) if affil_m else "",
            )
        )
    return out


def _split_description(desc: str) -> tuple[str, str, str]:
    """Split ``og:description`` ("ФИО, Должность, Подразделение, …, НИУ ВШЭ")."""
    parts = [p.strip() for p in desc.split(",") if p.strip()]
    if not parts:
        return "", "", ""
    full_name = parts[0]
    position = parts[1] if len(parts) > 1 else ""
    dept_parts: list[str] = []
    for part in parts[2:]:
        if _ORG_HINT in part or "Высшая школа экономики" in part:
            break
        if _PHONE_HINT_RE.search(part):
            continue
        dept_parts.append(part)
    return full_name, position, ", ".join(dept_parts)


def parse_profile(html: str, person_id: str) -> HsePersonDetail:
    """Parse an individual profile page into precise fields."""
    title_m = _OG_TITLE_RE.search(html)
    desc_m = _OG_DESC_RE.search(html)
    desc = html_lib.unescape(desc_m.group(1)) if desc_m else ""
    name_from_desc, position, department = _split_description(desc)
    full_name = html_lib.unescape(title_m.group(1)).strip() if title_m else name_from_desc
    degree_m = _DEGREE_RE.search(_clean(html))
    degree = degree_m.group(0).strip() if degree_m else ""
    if degree:
        degree = degree[0].upper() + degree[1:]
    return HsePersonDetail(
        id=person_id,
        full_name=full_name,
        position=position,
        department=department,
        degree=degree,
        profile_url=f"{_SITE_BASE}/org/persons/{person_id}",
        photo_url=f"{_SITE_BASE}/org/persons/cimage/{person_id}",
    )


def _parse_radio_group(html: str, group: str) -> tuple[HseFacetOption, ...]:
    """Parse a `js-side_filter` radio group (category/scirank/position) into options."""
    regex = re.compile(r'<input[^>]*id="' + re.escape(group) + r'\d+"[^>]*value="([^"]*)"[^>]*>')
    out: list[HseFacetOption] = []
    seen: set[str] = set()
    for m in regex.finditer(html):
        value = m.group(1)
        if value in seen:
            continue
        seen.add(value)
        window = html[m.end() : m.end() + _RADIO_LABEL_WINDOW]
        stop = _LABEL_STOP_RE.search(window)
        label = _clean(window[: stop.start()] if stop else window)
        if label:
            out.append(HseFacetOption(value=value, label=label))
    return tuple(out)


def parse_facets(html: str) -> HseFacets:
    """Parse the directory filter sidebar into the lookup filter vocabulary."""
    campuses: list[HseFacetOption] = [HseFacetOption(value="", label="Москва")]
    departments: list[HseFacetOption] = []
    seen_dept: set[str] = set()
    for m in _HSE_VALUE_RE.finditer(html):
        value = m.group("val")
        label = _clean(m.group("label"))
        if not label or value in seen_dept:
            continue
        seen_dept.add(value)
        if label.startswith(_CAMPUS_LABEL_PREFIX):
            campuses.append(HseFacetOption(value=value, label=label[len(_CAMPUS_LABEL_PREFIX) :].strip()))
        else:
            departments.append(HseFacetOption(value=value, label=label))
    return HseFacets(
        campuses=tuple(campuses),
        departments=tuple(departments),
        categories=_parse_radio_group(html, "category"),
        sciranks=_parse_radio_group(html, "scirank"),
        positions=_parse_radio_group(html, "position"),
    )


# <a … href="…intst=191890994…">история права России</a>
_INTST_RE = re.compile(r'href="[^"]*intst=(\d+)[^"]*"[^>]*>(.*?)</a>', re.S)


def parse_interests(html: str, limit: int) -> tuple[HseFacetOption, ...]:
    """Parse the научные-интересы chips present on a listing page (contextual)."""
    out: list[HseFacetOption] = []
    seen: set[str] = set()
    for m in _INTST_RE.finditer(html):
        value = m.group(1)
        if value in seen:
            continue
        label = _clean(m.group(2))
        if not label:
            continue
        seen.add(value)
        out.append(HseFacetOption(value=value, label=label))
        if len(out) >= limit:
            break
    return tuple(out)
