from __future__ import annotations

import re
from datetime import datetime, timezone

from hse_doc_studio.core.enums import VcsCommitKind
from hse_doc_studio.core.vcs.entities import VcsHistoryQuery

# Вид, под который попадают снимки без трейлера Hse-Kind и с видом, неизвестным этой Студии.
_FALLBACK_KIND = VcsCommitKind.manual.value
_KNOWN_KINDS = frozenset(kind.value for kind in VcsCommitKind)

_ERE_SPECIAL = re.compile(r"([\\.^$|?*+()\[\]{}])")
_KIND_TRAILER_VALUE = re.compile(r"^Hse-Kind:\s*(\S+)\s*$", re.MULTILINE)


def ere_escape(text: str) -> str:
    """Текст как буквальный фрагмент расширенного регулярного выражения (git log -E)."""
    return _ERE_SPECIAL.sub(r"\\\1", text)


def raw_kind(body: str) -> str | None:
    """Значение трейлера Hse-Kind как написано в сообщении; None, если трейлера нет."""
    match = _KIND_TRAILER_VALUE.search(body)
    return match.group(1) if match else None


def kind_matches(body: str, kinds: tuple[str, ...]) -> bool:
    """Проверка вида в Python для случая, когда в отбор входит manual и одним --grep его не выразить."""
    raw = raw_kind(body)
    if raw in kinds:
        return True
    return _FALLBACK_KIND in kinds and (raw is None or raw not in _KNOWN_KINDS)


def kinds_need_python(query: VcsHistoryQuery) -> bool:
    """manual включает коммиты без трейлера, а искать отсутствие строки через --grep нельзя."""
    return _FALLBACK_KIND in query.kinds


def needs_python(query: VcsHistoryQuery) -> bool:
    """Текст ищет Python: git сворачивает регистр кириллицы лишь в UTF-8 локали, а служебное окружение её не задаёт."""
    return kinds_need_python(query) or bool(_clean(query.text))


def matches(body: str, query: VcsHistoryQuery) -> bool:
    """Отбор, который git не выразит: вид manual и подстрока в сообщении без регистра."""
    if kinds_need_python(query) and not kind_matches(body, query.kinds):
        return False
    text = _clean(query.text)
    return not text or text.casefold() in _searchable(body).casefold()


def git_args(query: VcsHistoryQuery) -> list[str]:
    """Аргументы `git log` для отбора по виду (если он не уходит в Python), автору и датам."""
    args: list[str] = []
    if query.kinds and not kinds_need_python(query):
        kinds = "|".join(ere_escape(kind) for kind in query.kinds)
        args += ["--extended-regexp", f"--grep=^Hse-Kind: ({kinds})$"]
    email = _clean(query.author_email)
    if email:
        args += ["--extended-regexp", "--regexp-ignore-case", f"--author=<{ere_escape(email)}>"]
    if query.since is not None:
        args.append(f"--since={_git_date(query.since)}")
    if query.until is not None:
        args.append(f"--until={_git_date(query.until)}")
    return args


def _searchable(body: str) -> str:
    """Сообщение без служебных трейлеров Hse-*: по ним искать нечего, а «edit» совпал бы с каждым снимком."""
    return _clean("\n".join(line for line in body.splitlines() if not line.startswith("Hse-")))


def _clean(value: str | None) -> str:
    if not value:
        return ""
    return " ".join(value.replace("\0", " ").split())


def _git_date(value: datetime) -> str:
    """Дата в виде, который git разбирает однозначно: UTC с явным смещением."""
    moment = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S +0000")
