from __future__ import annotations

# Patterns written verbatim into <git-dir>/info/exclude at init (and refreshed on
# connect). The version history holds the user's WORK — source documents,
# project settings, signatures and forms — and nothing else. Everything that is
# derived, generated, transient, or belongs to a different feature is excluded so
# that "compiled but didn't edit anything" never registers as a change (no
# million-entry history). PDFs are excluded per-commit via an :(exclude)*.pdf
# pathspec so the track_pdf toggle never has to rewrite this file.
DEFAULT_VCS_EXCLUDE: tuple[str, ...] = (
    "# LaTeX intermediates",
    "*.aux",
    "*.log",
    "*.synctex.gz",
    "*.out",
    "*.toc",
    "*.fls",
    "*.fdb_latexmk",
    "*.bbl",
    "*.blg",
    "*.nav",
    "*.snm",
    "*.vrb",
    "*.lof",
    "*.lot",
    "*.idx",
    "*.ind",
    "*.ilg",
    "*.run.xml",
    "# build dirs",
    ".build/",
    "**/.build/",
    "# generated from project.json before every compile (derived, not authored)",
    "common/meta.tex",
    "# the ChangeLog journal — a separate human log, not source",
    ".hse-studio/history.json",
    "# submission packaging — a separate feature, not version history",
    "submissions/",
    ".hse-studio/submissions/",
    "# our own store + a foreign user git",
    ".hse-studio/git/",
    ".git/",
    ".gitmodules",
    "# hse-studio caches (sources stay tracked)",
    ".hse-studio/compiles/",
    ".hse-studio/chats/",
)
