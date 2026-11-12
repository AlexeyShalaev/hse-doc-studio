"""Корпус для поиска выделения из PDF в исходнике: глава ВКР на LaTeX и выделения так, как их отдаёт pdf.js.

Текст выделений повторяет то, что даёт `Selection.toString()` над текстовым слоем pdf.js у PDF из XeLaTeX/pdfLaTeX:
переносы со знаком `-` и переводом строки, лигатуры, пропавшие или лишние пробелы, номера ссылок `[3]` и
`2.1` вместо `\\cite` и `\\ref`, знак сноски, типографские кавычки и тире, неразрывные пробелы.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SOURCE = r"""\chapter{Анализ предметной области}
\label{ch:analysis}

% TODO: переписать вступление после ревью
В этой главе рассматриваются существующие подходы к автоматизации
нормоконтроля выпускных квалификационных работ. Особое внимание уделено
\textbf{проверке оформления} по ГОСТ~7.32--2017 и требованиям
факультета~\cite{gost2017,fkn2024}.

\section{Обзор существующих решений}
\label{sec:review}

Наиболее распространённым инструментом остаётся ручная проверка:
нормоконтролёр открывает PDF и сверяет поля, шрифты и нумерацию
с методическими указаниями. По данным опроса\footnote{Опрос проведён
в октябре 2025 года среди 42 сотрудников учебных офисов.}, на одну
работу уходит от 30 до 90 минут.

Автоматические средства делятся на три группы (см. раздел~\ref{sec:groups}):
\begin{itemize}
  \item плагины текстовых редакторов, которые проверяют стиль <<на лету>>;
  \item сервисы, принимающие готовый файл и возвращающие отчёт;
  \item системы вёрстки, где правила оформления заложены в шаблон.
\end{itemize}

Третья группа наиболее перспективна: если документ собирается из
исходников по шаблону, то большинство ошибок оформления просто
невозможно допустить. Остаётся проверить содержательные требования,
например наличие обязательных разделов и корректность ссылок на
литературу~\cite[с.~15]{knuth1984}.

\section{Требования к системе}
\label{sec:groups}

Система должна поддерживать совместную работу студента и научного
руководителя: руководитель оставляет замечания прямо в документе,
а студент видит их рядом с исходным текстом. Для этого используется
синхронизация позиций SyncTeX, связывающая каждую строку PDF с
файлом и строкой исходника.

Формула оценки качества имеет вид $Q = \alpha \cdot P + (1-\alpha) \cdot R$,
где $P$~--- точность, $R$~--- полнота, а коэффициент $\alpha \in [0, 1]$
подбирается эмпирически.

\begin{table}[h]
  \centering
  \caption{Сравнение инструментов}
  \label{tab:tools}
  \begin{tabular}{|l|c|c|}
    \hline
    Инструмент & Скорость & Точность \\
    \hline
    Ручная проверка & низкая & высокая \\
    Плагин редактора & высокая & средняя \\
    \hline
  \end{tabular}
\end{table}

Эффективность и efficiency of the workflow определяются тем, насколько
быстро обнаруживаются ошибки: \emph{чем раньше найдена ошибка, тем дешевле
её исправление}. Это подтверждается в~работах~\cite{boehm1981} и
\cite{mcconnell2004}.

В заключение отметим, что предложенный подход требует дальнейшей
апробации на реальных работах студентов 2026 года выпуска.
"""


@dataclass(frozen=True)
class Case:
    """Выделение в PDF и то, с чего должна начинаться и чем заканчиваться найденная цитата (None: не найти)."""

    name: str
    pdf: str
    starts: str | None
    ends: str | None = None


CASES: list[Case] = [
    Case("слово", "нормоконтроля", "нормоконтроля", "нормоконтроля"),
    Case("фраза в строке", "существующие подходы к автоматизации", "существующие", "автоматизации"),
    Case(
        "перенос строки и слова",
        "автоматизации нор-\nмоконтроля выпускных",
        "автоматизации",
        "выпускных",
    ),
    Case("перенос без дефиса", "автоматизации нормо\nконтроля", "автоматизации", "нормоконтроля"),
    Case("жирный", "проверке оформления", "проверке", "оформления"),
    Case("через разметку", "уделено проверке оформления по ГОСТ 7.32–2017", "уделено", "2017"),
    Case("ссылка на литературу", "требованиям факультета [1, 2].", "требованиям", "}."),
    Case("заголовок раздела", "1.1 Обзор существующих решений", "Обзор", "решений"),
    Case("знак сноски", "По данным опроса1, на одну работу", "По данным", "работу"),
    Case("текст сноски", "Опрос проведён в октябре 2025 года среди 42 сотрудников", "Опрос", "сотрудников"),
    Case(
        "ссылка на раздел",
        "Автоматические средства делятся на три группы (см. раздел 1.2):",
        "Автоматические",
        "):",
    ),
    Case("пункт списка", "• плагины текстовых редакторов, которые проверяют стиль «на лету»;", "плагины", ";"),
    Case(
        "два пункта",
        "сервисы, принимающие готовый файл и возвращающие отчёт;\n• системы вёрстки",
        "сервисы",
        "вёрстки",
    ),
    Case("ё и е", "системы верстки, где правила", "системы", "правила"),
    Case(
        "абзац целиком",
        "Третья группа наиболее перспективна: если документ собирается из исход-\n"
        "ников по шаблону, то большинство ошибок оформления просто невозможно\n"
        "допустить. Остаётся проверить содержательные требования, например нали-\n"
        "чие обязательных разделов и корректность ссылок на литературу [3, с. 15].",
        "Третья",
        ".",
    ),
    Case("лигатуры", "Эффективность и efficiency of the workﬂow", "Эффективность", "workflow"),
    Case("курсив", "чем раньше найдена ошибка, тем дешевле её исправление", "чем", "исправление"),
    Case("неразрывный пробел", "Это подтверждается в работах [4] и [5].", "Это", "}."),
    Case("формула", "Q = αP + (1 − α)R", None),
    Case("подпись к формуле", "где P — точность, R — полнота, а коэффициент", "где", "коэффициент"),
    Case("ячейка таблицы", "Плагин редактора высокая средняя", "Плагин", "средняя"),
    Case("подпись таблицы", "Таблица 1.1 – Сравнение инструментов", "Сравнение", "инструментов"),
    Case("лишние пробелы", "студент  видит  их  рядом с  исходным  текстом", "студент", "текстом"),
    Case("пропавшие пробелы", "синхронизацияпозиций SyncTeX,связывающая", "синхронизация", "связывающая"),
    Case(
        "опечатка в PDF-тексте",
        "Система должна поддерживать совместную работу студента и научного руководтеля",
        "Система",
        "руководителя",
    ),
    Case("цифры", "студентов 2026 года выпуска", "студентов", "выпуска"),
    Case("короткое", "SQL", None),
    Case("колонтитул шаблона", "Национальный исследовательский университет", None),
    Case("номер страницы", "12", None),
    Case("пробелы и точка", "В заключение отметим, что предложенный подход", "В заключение", "подход"),
]


# ── Вторая проверка: выделения, нарезанные из «отрисованного» текста главы ─────────────────────────────────────
#
# Грубый рендер LaTeX в текст страницы: номера разделов и ссылок, `[n]` вместо `\cite`, знак сноски в теле и текст
# сноски внизу, маркеры списка, типографские кавычки и тире, лигатуры, перенос строк по ширине с переносами слов,
# потерянные и лишние пробелы. Каждый знак помнит смещение в исходнике (-1 у того, чего в исходнике нет), поэтому
# у каждого случайного выделения известна правильная цитата.

_GLYPHS = {"alpha": "α", "cdot": "·", "in": "∈"}
_HEADINGS = {"chapter": "1 ", "section": "1.{n} "}


@dataclass
class Rendered:
    text: str
    offsets: list[int]


def _find_group_end(source: str, at: int) -> int:
    depth = 0
    for i in range(at, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    return len(source) - 1


def render(source: str) -> Rendered:  # noqa: C901, PLR0912, PLR0915 — грубый, но прямолинейный рендер
    out: list[tuple[str, int]] = []
    notes: list[tuple[str, int]] = []
    sections = 0
    cites = 0
    tables = 0

    def emit(text: str, offset: int = -1, target: list[tuple[str, int]] | None = None) -> None:
        for ch in text:
            (out if target is None else target).append((ch, offset))

    def body(lo: int, hi: int, target: list[tuple[str, int]] | None = None) -> None:  # noqa: C901, PLR0912
        nonlocal sections, cites, tables
        i = lo
        while i < hi:
            ch = source[i]
            if ch == "%":
                nl = source.find("\n", i)
                i = hi if nl == -1 else nl + 1
                continue
            if ch == "\\":
                j = i + 1
                while j < hi and source[j].isalpha():
                    j += 1
                name = source[i + 1 : j]
                if not name:
                    nxt = source[i + 1]
                    emit("\n" if nxt == "\\" else nxt if nxt in "%&$#_" else "", -1, target)
                    i += 2
                    continue
                k = j
                opt = ""
                if k < hi and source[k] == "[":
                    close = source.index("]", k)
                    opt = source[k + 1 : close]
                    k = close + 1
                has_arg = k < hi and source[k] == "{"
                arg_end = _find_group_end(source, k) if has_arg else k - 1
                if name in ("chapter", "section", "caption") and has_arg:
                    if name == "section":
                        sections += 1
                        emit(f"\n1.{sections} ", -1, target)
                    elif name == "chapter":
                        emit("1 ", -1, target)
                    else:
                        tables += 1
                        emit(f"Таблица 1.{tables} – ", -1, target)
                    body(k + 1, arg_end, target)
                    emit("\n", -1, target)
                    i = arg_end + 1
                elif name in ("textbf", "emph") and has_arg:
                    body(k + 1, arg_end, target)
                    i = arg_end + 1
                elif name == "cite" and has_arg:
                    keys = source[k + 1 : arg_end].split(",")
                    nums = []
                    for _ in keys:
                        cites += 1
                        nums.append(str(cites))
                    emit("[" + ", ".join(nums) + (f", {opt.replace('~', ' ')}" if opt else "") + "]", -1, target)
                    i = arg_end + 1
                elif name == "ref" and has_arg:
                    emit("1.2", -1, target)
                    i = arg_end + 1
                elif name == "footnote" and has_arg:
                    emit("1", -1, target)
                    body(k + 1, arg_end, notes)
                    i = arg_end + 1
                elif name == "item":
                    emit("\n• ", -1, target)
                    i = j
                elif name in _GLYPHS:
                    emit(_GLYPHS[name], -1, target)
                    i = j
                elif name == "begin" and has_arg:
                    env = source[k + 1 : arg_end]
                    i = arg_end + 1
                    if env == "tabular":
                        i = _find_group_end(source, i) + 1
                    elif env == "table" and source[i] == "[":
                        i = source.index("]", i) + 1
                else:
                    i = arg_end + 1 if has_arg else j
                continue
            if ch == "$":
                i += 1
                continue
            if ch == "~":
                emit(" ", i, target)
                i += 1
                continue
            if source.startswith("---", i):
                emit("—", i, target)
                i += 3
                continue
            if source.startswith("--", i):
                emit("–", i, target)
                i += 2
                continue
            if source.startswith("<<", i) or source.startswith(">>", i):
                emit("«" if ch == "<" else "»", i, target)
                i += 2
                continue
            if ch == "&":
                emit(" ", -1, target)
                i += 1
                continue
            if ch in "{}^_":
                i += 1
                continue
            if ch == "\n":
                blank = source.startswith("\n", i + 1)
                emit("\n" if blank else " ", i, target)
                i += 2 if blank else 1
                continue
            emit(ch, i, target)
            i += 1

    body(0, len(source))
    out.append(("\n", -1))
    out.extend(notes)
    text = "".join(c for c, _ in out)
    return Rendered(text=text, offsets=[o for _, o in out])


def page_text(rendered: Rendered, rng: object, width: int = 62) -> Rendered:  # noqa: C901
    """Строки по ширине с переносами слов, лигатуры, потерянные и лишние пробелы (`rng` это random.Random)."""
    import random  # noqa: PLC0415

    assert isinstance(rng, random.Random)  # noqa: S101
    chars: list[tuple[str, int]] = []
    column = 0
    words = re.split(r"(\s+)", rendered.text)
    pos = 0
    for word in words:
        span = list(zip(word, rendered.offsets[pos : pos + len(word)], strict=True))
        pos += len(word)
        if not word:
            continue
        if word.isspace():
            if "\n" in word:
                chars.append(("\n", -1))
                column = 0
                continue
            roll = rng.random()
            if roll < 0.05:
                continue
            chars.extend(span * (2 if roll > 0.95 else 1))
            column += 1
            continue
        if column + len(word) > width and column > 0:
            if len(word) > 6 and word.isalpha():
                cut = rng.randint(3, len(word) - 3)
                chars.extend(span[:cut])
                chars.extend([("-", -1), ("\n", -1)])
                span = span[cut:]
            else:
                chars.append(("\n", -1))
            column = 0
        chars.extend(span)
        column += len(span)
    text = "".join(c for c, _ in chars).replace("fi", "ﬁ").replace("fl", "ﬂ")
    offsets = [o for _, o in chars]
    # Лигатура занимает один знак вместо двух: смещение берётся у первой буквы.
    fixed: list[int] = []
    i = 0
    for ch in text:
        fixed.append(offsets[i])
        i += 2 if ch in "ﬁﬂ" else 1
    return Rendered(text=text, offsets=fixed)
