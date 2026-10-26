"""Слияние текста: разбор вывода diff3 на участки и сборка файла по решениям.

`git merge-file --diff3` зовётся с подписями `hse:ours`, `hse:base`, `hse:theirs`. Вывод
разбирается на чистые куски и конфликтные участки; участок получает ключ от своего
содержимого, а не номер, поэтому решения переживают пересчёт плана, как у git rerere.

Результат не зависит от того, кто «я»: движок всегда зовётся с сторонами в порядке
содержимого, а потом стороны возвращаются на место. Две машины, сливающие одну пару
коммитов, получают один и тот же файл, иначе синхронизация ходила бы по кругу.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from hse_doc_studio.core.git_sync.errors import GitErrorCode, GitSyncError
from hse_doc_studio.core.git_sync.merge.choices import HunkChoice, HunkDecision
from hse_doc_studio.core.template_update.protocols import IMergeEngine
from hse_doc_studio.core.template_update.text import normalize_text

OURS_LABEL = "hse:ours"
BASE_LABEL = "hse:base"
THEIRS_LABEL = "hse:theirs"

_OURS_MARKER = f"<<<<<<< {OURS_LABEL}".encode()
_BASE_MARKER = f"||||||| {BASE_LABEL}".encode()
_SEPARATOR = b"======="
_THEIRS_MARKER = f">>>>>>> {THEIRS_LABEL}".encode()
_MARKER_LINES = frozenset({_OURS_MARKER, _BASE_MARKER, _SEPARATOR, _THEIRS_MARKER})
_HSE_MARKER_RE = re.compile(rb"^(?:<{7} hse:ours|\|{7} hse:base|>{7} hse:theirs)\r?$", re.MULTILINE)
# git merge-file возвращает число конфликтов, но не больше этого.
_MAX_REPORTED_CONFLICTS = 127


@dataclass(frozen=True)
class CleanText:
    """Кусок текста, слитый без конфликта."""

    content: bytes


@dataclass(frozen=True)
class TextHunk:
    """Конфликтный участок: что стало с одним и тем же местом у каждой из сторон."""

    key: str
    ours: bytes
    base: bytes
    theirs: bytes
    # Номер первой строки участка в файле каждой стороны (с 1).
    ours_start: int
    theirs_start: int


Segment = CleanText | TextHunk


@dataclass(frozen=True)
class TextMerge:
    segments: tuple[Segment, ...]
    # Кончается ли файл стороны переводом строки: без него git склеивает последнюю строку иначе.
    ours_final_newline: bool = True
    theirs_final_newline: bool = True
    # Слияние конфликтует, но на участки не делится: решается файлом целиком.
    opaque: bool = False

    @property
    def hunks(self) -> tuple[TextHunk, ...]:
        return tuple(segment for segment in self.segments if isinstance(segment, TextHunk))

    @property
    def conflicted(self) -> bool:
        return self.opaque or bool(self.hunks)

    @property
    def clean_content(self) -> bytes:
        """Итог слияния без конфликтов."""
        return b"".join(segment.content for segment in self.segments if isinstance(segment, CleanText))


def has_hse_markers(content: bytes) -> bool:
    """Остались ли в тексте маркеры конфликта Студии (в историю они не попадают никогда)."""
    return _HSE_MARKER_RE.search(content) is not None


def split_lines(content: bytes) -> list[bytes]:
    """Строки с переводом строки в конце каждой; последняя может быть без него."""
    parts = content.split(b"\n")
    lines = [part + b"\n" for part in parts[:-1]]
    if parts[-1]:
        lines.append(parts[-1])
    return lines


def to_text_lines(content: bytes) -> list[str]:
    """Строки для показа: без переводов строк."""
    return [line.rstrip(b"\n").decode("utf-8", "replace") for line in split_lines(content)]


def hunk_key(ours: bytes, theirs: bytes) -> str:
    digest = hashlib.sha256(normalize_text(ours) + b"\0" + normalize_text(theirs)).hexdigest()
    return f"h:{digest[:8]}"


def _with_keys(segments: tuple[Segment, ...]) -> tuple[Segment, ...]:
    """Ключи участков; одинаковые участки одного файла различаются суффиксом по порядку."""
    seen: dict[str, int] = {}
    keyed: list[Segment] = []
    for segment in segments:
        if not isinstance(segment, TextHunk):
            keyed.append(segment)
            continue
        key = hunk_key(segment.ours, segment.theirs)
        seen[key] = seen.get(key, 0) + 1
        keyed.append(replace(segment, key=key if seen[key] == 1 else f"{key}.{seen[key]}"))
    return tuple(keyed)


def _count_lines(content: bytes) -> int:
    return len(split_lines(content))


@dataclass
class _Diff3Parser:
    """Конечный автомат по строкам вывода: чистый текст → моё → база → чужое → чистый текст."""

    segments: list[Segment] = field(default_factory=list)
    clean: list[bytes] = field(default_factory=list)
    ours: list[bytes] = field(default_factory=list)
    base: list[bytes] = field(default_factory=list)
    theirs: list[bytes] = field(default_factory=list)
    state: str = "clean"
    ours_line: int = 1
    theirs_line: int = 1
    start: tuple[int, int] = (1, 1)

    def feed(self, line: bytes) -> None:
        getattr(self, f"_in_{self.state}")(line, line.removesuffix(b"\n"))

    def finish(self) -> tuple[Segment, ...] | None:
        if self.state != "clean":
            return None
        self._flush_clean()
        return _with_keys(tuple(self.segments))

    def _in_clean(self, line: bytes, marker: bytes) -> None:
        if marker != _OURS_MARKER:
            self.clean.append(line)
            return
        self._flush_clean()
        self.start = (self.ours_line, self.theirs_line)
        self.state = "ours"

    def _flush_clean(self) -> None:
        if self.clean:
            content = b"".join(self.clean)
            self.segments.append(CleanText(content))
            self.ours_line += _count_lines(content)
            self.theirs_line += _count_lines(content)
            self.clean = []

    def _in_ours(self, line: bytes, marker: bytes) -> None:
        if marker == _BASE_MARKER:
            self.state = "base"
        else:
            self.ours.append(line)

    def _in_base(self, line: bytes, marker: bytes) -> None:
        if marker == _SEPARATOR:
            self.state = "theirs"
        else:
            self.base.append(line)

    def _in_theirs(self, line: bytes, marker: bytes) -> None:
        if marker != _THEIRS_MARKER:
            self.theirs.append(line)
            return
        hunk = TextHunk("", b"".join(self.ours), b"".join(self.base), b"".join(self.theirs), *self.start)
        self.segments.append(hunk)
        self.ours_line += _count_lines(hunk.ours)
        self.theirs_line += _count_lines(hunk.theirs)
        self.ours, self.base, self.theirs = [], [], []
        self.state = "clean"


def parse_diff3(output: bytes) -> tuple[Segment, ...] | None:
    """Разобрать вывод `git merge-file --diff3`; None, если маркеры расставлены не по порядку."""
    parser = _Diff3Parser()
    for line in split_lines(output):
        parser.feed(line)
    return parser.finish()


def swap_sides(merge: TextMerge) -> TextMerge:
    """То же слияние с поменянными местами «моим» и «чужим»."""
    segments = tuple(
        replace(s, ours=s.theirs, theirs=s.ours, ours_start=s.theirs_start, theirs_start=s.ours_start)
        if isinstance(s, TextHunk)
        else s
        for s in merge.segments
    )
    return replace(
        merge,
        segments=_with_keys(segments),
        ours_final_newline=merge.theirs_final_newline,
        theirs_final_newline=merge.ours_final_newline,
    )


def _ends_with_newline(content: bytes) -> bool:
    return not content or content.endswith(b"\n")


def _is_ambiguous(*contents: bytes) -> bool:
    """В тексте есть строки, похожие на маркеры: границы участков в выводе git не определить."""
    return any(line.removesuffix(b"\n") in _MARKER_LINES for content in contents for line in split_lines(content))


def single_hunk(ours: bytes, theirs: bytes) -> TextMerge:
    """Оба добавили файл: общей базы нет, и склейка двух чужих текстов — только решение человека."""
    ours, theirs = normalize_text(ours), normalize_text(theirs)
    hunk = TextHunk("", ours, b"", theirs, 1, 1)
    return TextMerge(
        _with_keys((hunk,)),
        ours_final_newline=_ends_with_newline(ours),
        theirs_final_newline=_ends_with_newline(theirs),
    )


def _from_outcome(output: bytes, conflicts: int, ours: bytes, base: bytes, theirs: bytes) -> TextMerge:
    flags = {"ours_final_newline": _ends_with_newline(ours), "theirs_final_newline": _ends_with_newline(theirs)}
    if conflicts == 0:
        return TextMerge((CleanText(output),) if output else (), **flags)
    segments = None if _is_ambiguous(ours, base, theirs) else parse_diff3(output)
    if segments is not None:
        found = sum(isinstance(segment, TextHunk) for segment in segments)
        if conflicts in (found, _MAX_REPORTED_CONFLICTS):
            return TextMerge(segments, **flags)
    return TextMerge((), opaque=True, **flags)


def merge_text(engine: IMergeEngine, ours: bytes, base: bytes, theirs: bytes) -> TextMerge:
    """Трёхстороннее слияние. Движок должен подписывать маркеры OURS_LABEL, BASE_LABEL, THEIRS_LABEL."""
    ours, base, theirs = normalize_text(ours), normalize_text(base), normalize_text(theirs)
    # Порядок сторон для движка не зависит от того, кто «я»: результат симметричен.
    swapped = hashlib.sha256(ours).digest() > hashlib.sha256(theirs).digest()
    if swapped:
        ours, theirs = theirs, ours
    outcome = engine.merge(ours, base, theirs)
    merge = _from_outcome(outcome.content, outcome.conflicts, ours, base, theirs)
    return swap_sides(merge) if swapped else merge


def _terminate(content: bytes) -> bytes:
    return content if _ends_with_newline(content) else content + b"\n"


def _sides(hunk: TextHunk, merge: TextMerge, *, last: bool) -> tuple[bytes, bytes]:
    """Моё и чужое участка; в конце файла без перевода строки он остаётся без него, как у git."""
    ours, theirs = hunk.ours, hunk.theirs
    if last and not merge.ours_final_newline:
        ours = ours.removesuffix(b"\n")
    if last and not merge.theirs_final_newline:
        theirs = theirs.removesuffix(b"\n")
    return ours, theirs


def _piece(hunk: TextHunk, decision: HunkDecision, *, last: bool, merge: TextMerge) -> bytes:
    ours, theirs = _sides(hunk, merge, last=last)
    if decision.choice is HunkChoice.custom:
        if decision.text is None:
            raise GitSyncError(GitErrorCode.invalid_resolution, hunk=hunk.key)
        return _terminate(decision.text.encode()) if decision.text else b""
    return {
        HunkChoice.mine: ours,
        HunkChoice.theirs: theirs,
        HunkChoice.both: _terminate(ours) + theirs,
        HunkChoice.both_reverse: _terminate(theirs) + ours,
        HunkChoice.base: hunk.base,
    }[decision.choice]


def render(merge: TextMerge, decisions: Mapping[str, HunkDecision], default: HunkChoice | None = None) -> bytes:
    """Файл по решениям; участок без решения берёт `default`, а без него — ошибка."""
    return b"".join(_pieces(merge, decisions, default))


def result_starts(
    merge: TextMerge, decisions: Mapping[str, HunkDecision], default: HunkChoice | None = None
) -> dict[str, int]:
    """Номер первой строки каждого участка в собранном по решениям файле (с 1)."""
    starts: dict[str, int] = {}
    line = 1
    for segment, piece in zip(merge.segments, _pieces(merge, decisions, default), strict=True):
        if isinstance(segment, TextHunk):
            starts[segment.key] = line
        line += _count_lines(piece)
    return starts


def _pieces(merge: TextMerge, decisions: Mapping[str, HunkDecision], default: HunkChoice | None) -> list[bytes]:
    pieces: list[bytes] = []
    missing: list[str] = []
    for index, segment in enumerate(merge.segments):
        if isinstance(segment, CleanText):
            pieces.append(segment.content)
            continue
        decision = decisions.get(segment.key) or (HunkDecision(default) if default is not None else None)
        if decision is None:
            missing.append(segment.key)
        else:
            pieces.append(_piece(segment, decision, last=index == len(merge.segments) - 1, merge=merge))
    if missing:
        raise GitSyncError(GitErrorCode.unresolved_conflicts, hunks=missing)
    return pieces
