from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class InstalledFont:
    """A font file present in the managed local fonts folder."""

    name: str
    size_bytes: int
    family: str = ""  # display family (from the font's name table), for preview/label


@dataclass(frozen=True)
class SystemFontFile:
    """A font file discovered in one of the OS's standard font directories."""

    name: str
    path: str
    family: str = ""  # display family (from the font's name table), for preview


@dataclass(frozen=True)
class FontCatalogFile:
    """One downloadable file of a curated catalog font (a single weight/style)."""

    filename: str
    url: str


@dataclass(frozen=True)
class FontCatalogItem:
    """A curated free font the user can download into the managed folder."""

    id: str
    label: str
    family: str
    description: str
    license: str
    files: tuple[FontCatalogFile, ...]


@dataclass(frozen=True)
class FontCatalog:
    """Thin DI wrapper around the curated catalog list (mirrors ModelCatalog)."""

    items: tuple[FontCatalogItem, ...]

    def get(self, item_id: str) -> FontCatalogItem | None:
        return next((i for i in self.items if i.id == item_id), None)


@dataclass(frozen=True)
class MarketplaceFont:
    """One searchable font in the online marketplace (Google Fonts inventory).

    `id` is the google/fonts folder slug. `category` is normalised to one of
    serif | sans-serif | display | handwriting | monospace. Only families that
    have static TTFs (usable by XeLaTeX) are surfaced.
    """

    id: str
    family: str
    category: str
    cyrillic: bool
    file_count: int


@dataclass(frozen=True)
class MarketplaceSearchResult:
    total: int  # total matches (for pagination); items is the current page
    items: tuple[MarketplaceFont, ...]
