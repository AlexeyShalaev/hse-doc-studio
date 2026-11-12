"""Поиск фрагмента, выделенного в превью PDF, в исходнике LaTeX (docs/design/stage5-review-realtime.md, 2.4).

Текст из PDF и исходник сравниваются по «видимому» тексту: из LaTeX убраны комментарии, имена команд и аргументы
команд, которые в PDF не видны как есть (`\\cite`, `\\ref`, `\\label`, окружения); обе стороны разложены NFKD без
диакритики (лигатуры, `ё` и `е`, `й` и `и` совпадают), без регистра, и остаются только буквы и цифры. Так переносы,
пробелы, кавычки, тире и разметка не мешают. Каждая буква проекции помнит своё смещение в исходнике, поэтому
найденный кусок возвращается как отрезок исходника.

Находка надёжна, если совпадение точное и не короче `EXACT_MIN` знаков, или нечёткое с долей от `FUZZY_MIN_SCORE`
при длине от `FUZZY_MIN_LEN`. Иначе поиск ничего не возвращает, и тред привязывается к месту в PDF.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from difflib import Match, SequenceMatcher

# Окно поиска вокруг строки SyncTeX: строка указывает на абзац, но не всегда на ту же строку исходника.
WINDOW_LINES = 40
EXACT_MIN = 4
FUZZY_MIN_LEN = 12
FUZZY_MIN_SCORE = 0.85
# Длинный фрагмент сравнивается по началу и концу: SequenceMatcher квадратичен.
_FUZZY_PART = 160
_SEED = 8
_SEEDS = 7
_CANDIDATES_MAX = 24
_OCCURRENCES_MAX = 64
_EDGE_MIN = 3

# Команды, чьи аргументы в PDF не видны как есть (ключи, метки, файлы, размеры, имена окружений).
_DROP_ARGS = frozenset(
    {
        "cite",
        "citep",
        "citet",
        "parencite",
        "textcite",
        "autocite",
        "footcite",
        "nocite",
        "ref",
        "eqref",
        "pageref",
        "autoref",
        "cref",
        "Cref",
        "nameref",
        "label",
        "input",
        "include",
        "includegraphics",
        "includepdf",
        "bibliography",
        "bibliographystyle",
        "addbibresource",
        "usepackage",
        "documentclass",
        "begin",
        "end",
        "vspace",
        "hspace",
        "setlength",
        "addtolength",
        "setcounter",
        "addtocounter",
        "newcommand",
        "renewcommand",
        "providecommand",
        "newenvironment",
        "renewenvironment",
        "def",
        "hypersetup",
        "color",
        "pagestyle",
        "thispagestyle",
        "newpage",
        "clearpage",
        "linespread",
        "fontsize",
    }
)
# Сноски: в PDF их текст внизу страницы, а в теле только знак. Тело ищется в проекции без сносок, сноска в полной.
_FOOTNOTES = frozenset({"footnote", "footnotetext", "thanks"})
# Подписи и номера, которые ставит LaTeX, а не автор: «Таблица 1.1 –», «Рисунок 2 —», «1.2 » перед заголовком.
_GENERATED_PREFIX = re.compile(
    r"^\s*(?:(?:Таблица|Рисунок|Рис\.|Листинг|Формула|Table|Figure|Fig\.|Listing)\s*[\dА-ЯA-Z]+(?:\.\d+)*\s*[–—:.-]?"
    r"|\d+(?:\.\d+)*\.?(?=\s))\s*"
)
# Что в исходнике может стоять между последней буквой цитаты и её знаком препинания: пробелы, `~`, лигатуры
# кавычек и тире.
_TEX_FILLER = frozenset(" \t\n~<>`'\"-")
_TAIL_SCAN = 120
# Таблицы: после имени окружения идёт спецификация колонок (у tabularx ещё ширина).
_TABLE_ENVS = {"tabular": 1, "tabular*": 2, "tabularx": 2, "longtable": 1, "array": 1, "tabulary": 2}


@dataclass(frozen=True)
class SourceSpan:
    """Отрезок исходника `[start, end)` и доля совпадения (1.0 у точного)."""

    start: int
    end: int
    score: float


def _fold(ch: str) -> str:
    """Буквы и цифры символа без диакритики и регистра; лигатура даёт несколько букв, знак препинания ничего."""
    out = []
    for part in unicodedata.normalize("NFKD", ch):
        if unicodedata.combining(part):
            continue
        low = part.lower()
        if low.isalnum():
            out.append(low)
    return "".join(out)


def fold_text(text: str) -> str:
    """Проекция обычного текста (выделения в PDF): только буквы и цифры."""
    return "".join(_fold(ch) for ch in text)


def _skip_group(source: str, at: int, hi: int, open_ch: str, close_ch: str) -> int:
    """Конец сбалансированной группы, начинающейся на `at` (там стоит `open_ch`)."""
    depth = 0
    i = at
    while i < hi:
        ch = source[i]
        if ch == "\\":
            i += 2
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return hi


def _skip_spaces(source: str, i: int, hi: int) -> int:
    while i < hi and source[i] in " \t":
        i += 1
    return i


def _skip_args(source: str, i: int, hi: int, mandatory: int | None) -> tuple[int, str]:
    """Пропускает `*`, необязательные `[…]` и обязательные `{…}` аргументы; возвращает позицию и первый `{…}`."""
    first = ""
    taken = 0
    if i < hi and source[i] == "*":
        i += 1
    while i < hi:
        j = _skip_spaces(source, i, hi)
        if j < hi and source[j] == "[":
            i = _skip_group(source, j, hi, "[", "]")
            continue
        if j < hi and source[j] == "{" and (mandatory is None or taken < mandatory):
            end = _skip_group(source, j, hi, "{", "}")
            if taken == 0:
                first = source[j + 1 : end - 1]
            taken += 1
            i = end
            if mandatory is None and taken >= 1:
                # Без явного числа: один обязательный аргумент, остальное считается текстом.
                return i, first
            continue
        break
    return i, first


def project_source(  # noqa: C901, PLR0912
    source: str, lo: int = 0, hi: int | None = None, *, footnotes: bool = True
) -> tuple[str, list[int]]:
    """Видимые буквы и цифры исходника LaTeX на `[lo, hi)` и смещение каждой в исходнике.

    `footnotes=False` убирает текст сносок: так ищется текст тела страницы, где от сноски остался только знак.
    """
    end = len(source) if hi is None else min(hi, len(source))
    chars: list[str] = []
    offsets: list[int] = []
    i = max(0, lo)
    while i < end:
        ch = source[i]
        if ch == "%":
            nl = source.find("\n", i, end)
            i = end if nl == -1 else nl + 1
            continue
        if ch == "\\":
            j = i + 1
            while j < end and source[j].isalpha():
                j += 1
            if j == i + 1:
                # Управляющий символ: `\%`, `\\`, `\,` и акценты `\'e` (буква после акцента остаётся видимой).
                i += 2
                continue
            name = source[i + 1 : j]
            j = _skip_spaces(source, j, end)
            if name in _DROP_ARGS or (not footnotes and name in _FOOTNOTES):
                if name == "begin":
                    j, env = _skip_args(source, j, end, 1)
                    extra = _TABLE_ENVS.get(env.strip(), 0)
                    if extra:
                        j, _ = _skip_args(source, j, end, extra)
                else:
                    j, _ = _skip_args(source, j, end, None)
            i = j
            continue
        folded = _fold(ch)
        for part in folded:
            chars.append(part)
            offsets.append(i)
        i += 1
    return "".join(chars), offsets


def _line_starts(source: str) -> list[int]:
    starts = [0]
    at = source.find("\n")
    while at != -1:
        starts.append(at + 1)
        at = source.find("\n", at + 1)
    return starts


def _occurrences(hay: str, needle: str) -> list[int]:
    found: list[int] = []
    at = hay.find(needle)
    while at != -1 and len(found) < _OCCURRENCES_MAX:
        found.append(at)
        at = hay.find(needle, at + 1)
    return found


def _displaced(left: Match, right: Match) -> bool:
    """Между соседними совпадениями в окне заметно больше текста, чем во фрагменте: правое (или левое) стоит не там."""
    gap_needle = right.a - (left.a + left.size)
    gap_hay = right.b - (left.b + left.size)
    return gap_hay > gap_needle + 2


def _fuzzy_part(needle: str, hay: str) -> list[tuple[float, int, int]]:  # noqa: C901
    """Нечёткие кандидаты `(доля, начало, конец)` в проекции окна по затравкам из нескольких мест фрагмента."""
    n = len(needle)
    seed = min(_SEED, max(4, n // 3))
    positions = sorted({round(k * (n - seed) / (_SEEDS - 1)) for k in range(_SEEDS)})
    starts: set[int] = set()
    for pos in positions:
        for at in _occurrences(hay, needle[pos : pos + seed]):
            starts.add(at - pos)
            if len(starts) >= _CANDIDATES_MAX:
                break
    slack = n // 4 + 4
    found: list[tuple[float, int, int]] = []
    seen: set[int] = set()
    for start in sorted(starts):
        bucket = start // max(1, slack)
        if bucket in seen:
            continue
        seen.add(bucket)
        lo = max(0, start - slack)
        region = hay[lo : start + n + slack]
        blocks = [b for b in SequenceMatcher(None, needle, region, autojunk=False).get_matching_blocks() if b.size]
        # Одна-две буквы с краю это случайные совпадения дальше по тексту, а не конец цитаты.
        while len(blocks) > 1 and blocks[-1].size < _EDGE_MIN and _displaced(blocks[-2], blocks[-1]):
            blocks.pop()
        while len(blocks) > 1 and blocks[0].size < _EDGE_MIN and _displaced(blocks[0], blocks[1]):
            blocks.pop(0)
        if not blocks:
            continue
        matched = sum(b.size for b in blocks)
        span_lo = blocks[0].b
        span_hi = blocks[-1].b + blocks[-1].size
        score = 2 * matched / (n + (span_hi - span_lo))
        found.append((score, lo + span_lo, lo + span_hi))
    return found


def _fuzzy(needle: str, hay: str) -> list[tuple[float, int, int]]:
    if len(needle) <= _FUZZY_PART * 2:
        return _fuzzy_part(needle, hay)
    # Длинный фрагмент: начало и конец ищутся отдельно, кусок между ними берётся целиком, если длина правдоподобна.
    heads = _fuzzy_part(needle[:_FUZZY_PART], hay)
    tails = _fuzzy_part(needle[-_FUZZY_PART:], hay)
    n = len(needle)
    found: list[tuple[float, int, int]] = []
    for h_score, h_lo, _h_hi in heads:
        for t_score, _t_lo, t_hi in tails:
            length = t_hi - h_lo
            if 0.75 * n <= length <= 1.25 * n:
                found.append((min(h_score, t_score), h_lo, t_hi))
    return found


def _to_span(offsets: list[int], lo: int, hi: int, score: float) -> SourceSpan:
    return SourceSpan(start=offsets[lo], end=offsets[hi - 1] + 1, score=score)


def _skip_invisible(source: str, i: int) -> int:
    """Позиция после пробелов, лигатур TeX и команд без видимых аргументов (`~\\cite{…}`, `>>`)."""
    limit = min(len(source), i + _TAIL_SCAN)
    while i < limit:
        ch = source[i]
        if ch in _TEX_FILLER:
            i += 1
            continue
        if ch == "\\":
            j = i + 1
            while j < limit and source[j].isalpha():
                j += 1
            if source[i + 1 : j] in _DROP_ARGS:
                i, _ = _skip_args(source, _skip_spaces(source, j, limit), limit, None)
                continue
        break
    return i


def _with_punctuation(source: str, text: str, span: SourceSpan) -> SourceSpan:
    """Хвост выделения после последней буквы (знак, ссылка `[3].`, кавычка `»;`) входит в цитату, если в исходнике
    за найденным после невидимого стоит тот же знак препинания."""
    stripped = text.rstrip()
    cut = len(stripped)
    while cut > 0 and not stripped[cut - 1].isalpha():
        cut -= 1
    tail = "".join(ch for ch in stripped[cut:] if not ch.isspace() and not ch.isalnum())
    if not tail:
        return span
    at = _skip_invisible(source, span.end)
    for k in range(len(tail), 0, -1):
        if source.startswith(tail[-k:], at):
            return SourceSpan(span.start, at + k, span.score)
    if source.startswith(tail[-1], at):
        return SourceSpan(span.start, at + 1, span.score)
    return span


def _search(needle: str, hay: str, offsets: list[int], hint: int) -> tuple[float, int, int] | None:
    """Лучшее совпадение в проекции: точное ближайшее к подсказке, иначе нечёткое с порогом."""
    exact = _occurrences(hay, needle)
    if exact:
        best = min(exact, key=lambda at: abs(offsets[at] - hint))
        return 1.0, best, best + len(needle)
    if len(needle) < FUZZY_MIN_LEN:
        return None
    candidates = [c for c in _fuzzy(needle, hay) if c[0] >= FUZZY_MIN_SCORE]
    if not candidates:
        return None
    return max(candidates, key=lambda c: (round(c[0], 3), -abs(offsets[c[1]] - hint)))


def locate_in_source(source: str, lines: list[int], text: str) -> SourceSpan | None:  # noqa: C901
    """Отрезок исходника с текстом выделения из PDF или None, если надёжной находки нет.

    `lines` это строки SyncTeX (с единицы) от начала и конца выделения; поиск идёт в окне вокруг них, ближайшее к
    ним совпадение побеждает. Точное совпадение за пределами окна принимается, только если оно в файле одно.
    """
    needle = fold_text(text)
    if len(needle) < EXACT_MIN:
        return None
    # Номер раздела или «Таблица 1.1 –» в начале выделения ставит LaTeX: второй заход ищет без них.
    needles = [needle]
    trimmed = fold_text(_GENERATED_PREFIX.sub("", text, count=1))
    if trimmed != needle and len(trimmed) >= EXACT_MIN:
        needles.append(trimmed)
    starts = _line_starts(source)
    known = [ln for ln in lines if ln >= 1] or [1]
    first = max(1, min(*known, len(starts)) - WINDOW_LINES)
    last = min(len(starts), max(known) + WINDOW_LINES)
    lo = starts[first - 1]
    hi = starts[last] if last < len(starts) else len(source)
    hint = starts[min(len(starts), known[0]) - 1]

    best: tuple[float, int, int, list[int]] | None = None
    projections = [project_source(source, lo, hi, footnotes=footnotes) for footnotes in (False, True)]
    for candidate in needles:
        for hay, offsets in projections:
            found = _search(candidate, hay, offsets, hint)
            if found is not None and (best is None or found[0] > best[0]):
                best = (*found, offsets)
            if best is not None and best[0] == 1.0:
                break
        if best is not None and best[0] == 1.0:
            break
    if best is None and len(needle) >= FUZZY_MIN_LEN:
        whole, whole_offsets = project_source(source)
        everywhere = _occurrences(whole, needle)
        if len(everywhere) == 1:
            best = (1.0, everywhere[0], everywhere[0] + len(needle), whole_offsets)
    if best is None:
        return None
    score, s_lo, s_hi, offsets = best
    return _with_punctuation(source, text, _to_span(offsets, s_lo, s_hi, score))


def visible_text(source_fragment: str) -> str:  # noqa: C901
    """Видимый текст цитаты из исходника для поиска на странице PDF: без команд, комментариев и лишних пробелов."""
    out: list[str] = []
    i = 0
    end = len(source_fragment)
    while i < end:
        ch = source_fragment[i]
        if ch == "%":
            nl = source_fragment.find("\n", i)
            i = end if nl == -1 else nl + 1
            continue
        if ch == "\\":
            j = i + 1
            while j < end and source_fragment[j].isalpha():
                j += 1
            if j == i + 1:
                nxt = source_fragment[i + 1] if i + 1 < end else ""
                out.append(" " if nxt in "\\ ,;!" else nxt if nxt in "%&$#_{}" else "")
                i += 2
                continue
            name = source_fragment[i + 1 : j]
            if name in _DROP_ARGS:
                j, _ = _skip_args(source_fragment, _skip_spaces(source_fragment, j, end), end, None)
            i = j
            out.append(" ")
            continue
        if ch in "{}$^_":
            i += 1
            continue
        out.append(" " if ch in "~\n\t" else ch)
        i += 1
    return " ".join("".join(out).split())
