"""Shared helpers for check engines.

The YAML rule format uses a few conventions that every engine needs to honour:
  - `params.message` can be a string or a LocalizedString dict (`{ru: "...", en: "..."}`)
  - File patterns can come as `file_glob` (preferred) or legacy `files`
  - Globs are resolved relative to the project root, not the document subfolder
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from hse_doc_studio.core.i18n import current_interface_language

logger = structlog.get_logger()

# A line of the logical (input-expanded) document, carrying its true origin so
# a diagnostic produced from the flattened stream can still point at the real
# file:line the student edits.
_INCLUDE_LINE_RE = re.compile(r"^\\(?:input|include|subfile)\s*\{([^}]+)\}\s*$")


@dataclass(frozen=True)
class SourceLine:
    file: str  # project-relative posix path of the originating file
    line: int  # 1-based line number within that file
    text: str  # the original line text


def _strip_tex_comment(line: str) -> str:
    """Drop an unescaped ``%`` comment (and everything after it) from a line."""
    out: list[str] = []
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if ch == "\\" and i + 1 < n:
            out.append(line[i : i + 2])
            i += 2
            continue
        if ch == "%":
            break
        out.append(ch)
        i += 1
    return "".join(out)


def _resolve_include(project_folder: Path, including_file_rel: str, target: str) -> Path | None:
    """Resolve an ``\\input``/``\\include`` target to a real file inside the project.

    LaTeX resolves include paths relative to the main file's directory and the
    job root; we try both. A missing extension defaults to ``.tex``. Anything
    that would escape the project folder is rejected.
    """
    target = target.strip()
    base_dir = (project_folder / including_file_rel).parent
    names = [target] if target.endswith(".tex") else [f"{target}.tex", target]
    root = project_folder.resolve()
    for name in names:
        for candidate in (base_dir / name, project_folder / name):
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved.is_file() and resolved.is_relative_to(root):
                return resolved
    return None


def _include_target_for_line(project_folder: Path, including_file_rel: str, line: str) -> str | None:
    """If a line is *only* an include command pointing at a real file, return
    that file's project-relative path; otherwise None (keep the line verbatim)."""
    match = _INCLUDE_LINE_RE.match(_strip_tex_comment(line).strip())
    if match is None:
        return None
    target = _resolve_include(project_folder, including_file_rel, match.group(1))
    if target is None:
        return None
    return target.relative_to(project_folder.resolve()).as_posix()


def expand_inputs(project_folder: Path, source_file: str, *, max_depth: int = 12) -> list[SourceLine]:
    """Flatten a multi-file LaTeX document by inlining ``\\input``/``\\include``.

    Returns the logical document as an ordered list of :class:`SourceLine`,
    each remembering the file and line it came from. A line that is *only* an
    include command is replaced by the included file's lines; everything else
    is kept verbatim. Cycles are broken (a file is expanded at most once) and
    missing/commented includes are left as plain text. Best-effort: unreadable
    files contribute nothing rather than raising.
    """
    result: list[SourceLine] = []
    visited: set[str] = set()

    def _walk(rel: str, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            key = str((project_folder / rel).resolve())
        except OSError:
            return
        if key in visited:
            return
        visited.add(key)

        for lineno, line in enumerate(read_text_safe(project_folder / rel).splitlines(), start=1):
            child = _include_target_for_line(project_folder, rel, line)
            if child is not None:
                _walk(child, depth + 1)
            else:
                result.append(SourceLine(file=Path(rel).as_posix(), line=lineno, text=line))

    _walk(Path(source_file).as_posix(), 0)
    return result


def _pick_lang(value: dict[str, Any], lang: str) -> str | None:
    v = value.get(lang) or value.get("ru") or value.get("en")
    return v if isinstance(v, str) and v else None


def localized_message(value: Any, fallback: str | dict[str, str], lang: str | None = None) -> str:
    """Extract a localized string from a YAML `message` field.

    Accepts either a raw string or a `{lang: str}` dict. ``lang`` defaults to the
    request's interface language (the `X-Interface-Language` header, independent
    from the document language), so pack-authored ``{ru, en}`` messages — and a
    ``{ru, en}`` ``fallback`` — follow the interface language automatically. A
    plain-string message stays as authored. Falls back to the given default when
    the field is missing or lacks the language.
    """
    if lang is None:
        lang = current_interface_language().value
    if isinstance(fallback, dict):
        resolved_fallback = _pick_lang(fallback, lang) or fallback.get("ru") or ""
    else:
        resolved_fallback = fallback
    if isinstance(value, dict):
        picked = _pick_lang(value, lang)
        return picked if picked is not None else resolved_fallback
    if isinstance(value, str) and value:
        return value
    return resolved_fallback


def match_files(project_folder: Path, params: dict[str, Any], base_dir: str = "") -> list[Path]:
    """Resolve the rule's file pattern against the instance base.

    Tries `file_glob` first (YAML convention), then `files` (legacy). Globs
    are relative to the document instance's BASE (`base_dir` от корня проекта;
    solo — сам корень, team — `shared/` или папка автора), so a rule for
    `tz/*.tex` or `common/meta.tex` finds the files of ITS base — not a
    teammate's copy. Returned paths are absolute (under the project root), so
    callers keep emitting project-relative locations.
    """
    glob = params.get("file_glob") or params.get("files") or "**/*.tex"
    root = project_folder / base_dir if base_dir else project_folder
    try:
        return sorted(p for p in root.glob(glob) if p.is_file())
    except (OSError, ValueError) as exc:
        logger.warning("match_files: glob error", glob=glob, exc=str(exc))
        return []


def read_text_safe(path: Path) -> str:
    """Read a UTF-8 text file, returning empty string on error."""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        logger.warning("read_text_safe: read error", path=str(path), exc=str(exc))
        return ""
