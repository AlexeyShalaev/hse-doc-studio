from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class HsePersonSummary:
    """One person row parsed from an HSE directory listing page.

    The listing gives the stable numeric id, ФИО and a coarse affiliation line
    (role + department). The precise должность/подразделение/степень come from the
    individual profile page (see HsePersonDetail)."""

    id: str
    full_name: str
    profile_url: str
    photo_url: str
    affiliation: str = ""


@dataclass(frozen=True)
class HsePersonDetail:
    """Precise fields parsed from an individual HSE profile page.

    `position` (должность) and `department` (подразделение) come from the page's
    canonical `og:description`; `degree` (учёная степень) is a best-effort parse of
    the profile prose and may be empty when the page doesn't state one."""

    id: str
    full_name: str
    position: str = ""
    department: str = ""
    degree: str = ""
    profile_url: str = ""
    photo_url: str = ""


@dataclass(frozen=True)
class HsePersonQuery:
    """A staff-search request.

    Facets are forwarded verbatim to hse.ru as server-side URL params (`ltr`,
    `udept`, `category`, `scirank`, `position`, `intst`); `name` is applied locally
    as a substring filter over the returned cards (hse.ru's own name box is
    disallowed by robots.txt, so we never use it). `campus` is a friendly key
    (moscow/spb/nn/perm) resolved to the top-level `udept` when no finer department
    is chosen."""

    name: str = ""
    campus: str = ""
    udept: str = ""
    ltr: str = ""
    category: str = ""
    scirank: str = ""
    position: str = ""
    intst: str = ""
    limit: int = 40


@dataclass(frozen=True)
class HseFacetOption:
    """A single selectable filter value (value forwarded to hse.ru, label shown)."""

    value: str
    label: str


@dataclass(frozen=True)
class HseFacets:
    """The filter vocabulary for the lookup UI, parsed from the directory sidebar."""

    campuses: tuple[HseFacetOption, ...] = ()
    departments: tuple[HseFacetOption, ...] = ()
    categories: tuple[HseFacetOption, ...] = ()
    sciranks: tuple[HseFacetOption, ...] = ()
    positions: tuple[HseFacetOption, ...] = ()


@dataclass(frozen=True)
class HseSearchResult:
    """A page of search results plus the научные-интересы present on that page.

    `interests` mirrors how hse.ru surfaces interests — as refine chips derived from
    the currently-listed people, not a global dictionary — so the UI can narrow the
    search by re-issuing it with `intst=<id>`."""

    persons: tuple[HsePersonSummary, ...] = ()
    interests: tuple[HseFacetOption, ...] = field(default_factory=tuple)
