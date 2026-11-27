r"""Проверка мест подписей и меток даты на якорях шаблона (docs/design/signing-route.md, 15.17.13).

Линтер проверяет текст, а не вёрстку: условный `\if` вокруг якоря он не видит, что якоря и `when` совпадают во всех
комбинациях, проверяет сборка. Здесь:

- у каждой записи на якоре (`placements`, `default_placement`, `default_dates` слота) в файлах документа (каталог
  его `source_file`) или в `common/` версии есть вызов `\hseSignAnchor[...]{<имя>}`,
  `\hseDateAnchor[...]{<имя>}{<часть>}` или обёртки из `signatures.anchor_macros` с `[<имя>]` первым аргументом;
  что даёт обёртка (якорь подписи и части даты), видно по её определению в тех же файлах;
- если пак использует якоря, в версии есть `common/anchors.tex`, и документ с якорями подключает его
  (`\input{../common/anchors}` в исходнике или преамбуле);
- `default_placement` на якоре только вместе с полным запасным местом в мм;
- предупреждения: имя якоря в исходнике не id слота каталога (опечатка), одно имя дважды в одном файле.

Якорь автора в команде (15.17.20) пишется именем слота, двойным подчёркиванием и слагом из Jinja:
`\hseSignAnchor[7cm]{author__{{ a.slug }}}`, `\hseDateAnchor{author__{{ a.slug }}}{day}`. Такой вызов закрывает
запись пака на якоре `author` (`author.day`), а `author_anchor_names` говорит линтеру пака, что место `per_author`
слота на общем документе встанет на строку каждого автора.

Имя такого якоря может приходить через макросы: цикл по авторам объявлен в одном общем файле и передаёт
`author__{{ a.slug }}` в макрос строки, а `\hseSignAnchor{#2}` стоит в самом макросе строки. Поэтому вызовы
документа и подключённых им (`\input`) общих файлов дополнительно раскрываются по макросам
`\newcommand`/`\renewcommand`/`\providecommand`. Макрос, который документ не вызывает, якорей не даёт.
"""

from __future__ import annotations

import posixpath
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from hse_doc_studio.core.catalog import AnchorDate, AnchorPlace
from hse_doc_studio.core.signatures.anchors import AUTHOR_SEPARATOR, NAME_RE, author_anchor_id, split_author_name
from hse_doc_studio.infra.project_init.template_renderer import PACK_DOC_MANIFEST
from hse_doc_studio.infra.template.yaml_template_repository import (
    parse_anchor_macros,
    parse_default_anchor,
    parse_default_dates,
    parse_slot_placement,
    slot_placement_entries,
)

_NAME = NAME_RE.pattern
# Имя якоря в вызове: обычное или якорь автора в команде, слаг из Jinja (`author__{{ a.slug }}`, 15.17.20).
_JINJA_AUTHOR = rf"[a-z][a-z0-9_]*?{AUTHOR_SEPARATOR}\{{\{{[^{{}}]*\}}\}}"
_ARG = rf"(?:{_JINJA_AUTHOR}|{_NAME})"
# Любой слаг: якорь автора в команде записывается в найденных как `author__*`.
_ANY_AUTHOR = "*"
_OPT = r"(?:\[[^\]]*\])?"
_SIGN_RE = re.compile(rf"\\hseSignAnchor\s*{_OPT}\s*\{{\s*({_ARG})\s*\}}")
_DATE_RE = re.compile(rf"\\hseDateAnchor\s*{_OPT}\s*\{{\s*({_ARG})\s*\}}\s*\{{\s*({_NAME})\s*\}}")
# Вызов якоря внутри определения обёртки: имя это параметр (`#1`).
_SIGN_PARAM_RE = re.compile(rf"\\hseSignAnchor\s*{_OPT}\s*\{{\s*#\d\s*\}}")
_DATE_PARAM_RE = re.compile(rf"\\hseDateAnchor\s*{_OPT}\s*\{{\s*#\d\s*\}}\s*\{{\s*({_NAME})\s*\}}")
_ANCHORS_INPUT_RE = re.compile(r"\\input\s*\{[^}]*common/anchors(?:\.tex)?\s*\}")
_DEFINITION_START_RE = re.compile(r"\\(?:newcommand|renewcommand|providecommand|NewDocumentCommand|def)\b")
_COMMENT_RE = re.compile(r"(?<!\\)%.*")
# Объявление макроса: имя, число параметров и значение необязательного первого; дальше группа с телом.
_MACRO_RE = re.compile(
    r"\\(?:newcommand|renewcommand|providecommand)\*?\s*(?:\{\s*\\([A-Za-z@]+)\s*\}|\\([A-Za-z@]+))"
    r"\s*(?:\[\s*(\d)\s*\])?\s*(?:\[([^\[\]]*)\])?\s*(?=\{)"
)
_CALL_RE = re.compile(r"\\([A-Za-z@]+)")
_INPUT_RE = re.compile(r"\\(?:input|include)\s*\{([^}]+)\}")
_LANG_SUFFIX_RE = re.compile(r"\.[a-z]{2}(?:-[a-z]{2})?$")
# Имя якоря на каждого автора в тексте вызова: без него раскрывать макросы незачем.
_AUTHOR_MARK = f"{AUTHOR_SEPARATOR}{{{{"
# Пределы раскрытия: глубина вложенных макросов и число разных вызовов на документ (рекурсия не зациклит).
_MAX_DEPTH = 8
_MAX_EXPANSIONS = 2000
_TEX_SUFFIXES = (".tex", ".j2", ".sty", ".cls")
ANCHORS_FILE = "common/anchors.tex"


@dataclass
class _Sources:
    """Вызовы якорей в файлах: id якоря → файлы, где он встречается; и подключение файла макросов."""

    found: dict[str, set[str]] = field(default_factory=dict)
    includes_macros: bool = False

    def add(self, anchor_id: str, rel: str) -> None:
        self.found.setdefault(anchor_id, set()).add(rel)


def _text(path: Path) -> str:
    return _COMMENT_RE.sub("", path.read_text(encoding="utf-8", errors="replace"))


def _tex_files(files_dir: Path, top: str) -> list[Path]:
    root = files_dir / top
    if not root.is_dir():
        return []
    return sorted(
        f
        for f in root.rglob("*")
        if f.is_file() and f.name != PACK_DOC_MANIFEST and any(f.name.endswith(s) for s in _TEX_SUFFIXES)
    )


@dataclass(frozen=True)
class _Wrapper:
    sign: bool
    parts: tuple[str, ...]


def _wrappers(texts: dict[str, str], macros: tuple[str, ...]) -> dict[str, _Wrapper]:
    """Что даёт каждая обёртка: якорь подписи и части даты по её определению (`\\newcommand\\имя...` до следующего
    определения). Определения нет: обёртка считается якорем подписи."""
    result: dict[str, _Wrapper] = {}
    for macro in macros:
        head = re.compile(rf"\\(?:newcommand|renewcommand|providecommand|NewDocumentCommand|def)\s*\{{?\\{macro}\b")
        body = next((_definition(text, m.end()) for text in texts.values() if (m := head.search(text))), None)
        if body is None:
            result[macro] = _Wrapper(sign=True, parts=())
            continue
        parts = tuple(dict.fromkeys(m.group(1) for m in _DATE_PARAM_RE.finditer(body)))
        result[macro] = _Wrapper(sign=_SIGN_PARAM_RE.search(body) is not None, parts=parts)
    return result


def _definition(text: str, start: int) -> str:
    following = _DEFINITION_START_RE.search(text, start)
    return text[start : following.start() if following else len(text)]


def _name(arg: str) -> str:
    """Имя якоря вызова; якорь автора в команде (`author__{{ a.slug }}` или `author__ivanov`) это `author__*`."""
    jinja = arg.find("{{")
    base, key = (arg[: jinja - len(AUTHOR_SEPARATOR)], _ANY_AUTHOR) if jinja >= 0 else split_author_name(arg)
    return author_anchor_id(base, _ANY_AUTHOR) if key is not None else base


def _calls(rel: str, text: str, wrappers: dict[str, _Wrapper]) -> list[str]:
    """id якорей, которые ставит файл: прямые вызовы и обёртки с `[имя]`."""
    ids = [_name(m.group(1)) for m in _SIGN_RE.finditer(text)]
    ids += [f"{_name(m.group(1))}.{m.group(2)}" for m in _DATE_RE.finditer(text)]
    for macro, wrapper in wrappers.items():
        for m in re.finditer(rf"\\{macro}\s*\[\s*({_ARG})\s*\]", text):
            name = _name(m.group(1))
            if wrapper.sign:
                ids.append(name)
            ids += [f"{name}.{part}" for part in wrapper.parts]
    return ids


def _present(anchor_id: str, found: dict[str, set[str]]) -> bool:
    """Якорь записи стоит в исходниках: сам или на каждого автора (`author__{{ a.slug }}`)."""
    return anchor_id in found or author_anchor_id(anchor_id, _ANY_AUTHOR) in found


@dataclass(frozen=True)
class _Macro:
    params: int
    default: str | None
    body: str


def _group(text: str, start: int, pair: str = "{}") -> tuple[str, int] | None:
    """Содержимое группы, которая начинается в `text[start]`, и позиция за ней; None: группы там нет."""
    opening, closing = pair[0], pair[1]
    if start >= len(text) or text[start] != opening:
        return None
    depth, index = 0, start
    while index < len(text):
        char = text[index]
        if char == "\\":
            index += 2
            continue
        if char == opening:
            depth += 1
        elif char == closing:
            depth -= 1
            if depth == 0:
                return text[start + 1 : index], index + 1
        index += 1
    return None


def _skip_spaces(text: str, index: int) -> int:
    while index < len(text) and text[index].isspace():
        index += 1
    return index


def _split_macros(texts: dict[str, str]) -> tuple[dict[str, list[_Macro]], dict[str, str]]:
    """Объявления макросов всех файлов и тексты без них (вызовы вне объявлений). Языковые редакции объявляют макрос
    дважды, поэтому под именем список."""
    macros: dict[str, list[_Macro]] = {}
    rest: dict[str, str] = {}
    for rel, text in texts.items():
        kept: list[str] = []
        position = 0
        for head in _MACRO_RE.finditer(text):
            body = _group(text, head.end()) if head.start() >= position else None
            if body is None:
                continue
            macro = _Macro(int(head.group(3) or 0), head.group(4), body[0])
            macros.setdefault(head.group(1) or head.group(2), []).append(macro)
            kept.append(text[position : head.start()])
            position = body[1]
        kept.append(text[position:])
        rest[rel] = " ".join(kept)
    return macros, rest


def _arguments(text: str, index: int, macro: _Macro) -> tuple[str, ...] | None:
    """Аргументы вызова макроса с позиции `index`; None: вызов неполный."""
    args: list[str] = []
    if macro.default is not None and macro.params:
        index = _skip_spaces(text, index)
        optional = _group(text, index, "[]")
        args.append(optional[0] if optional else macro.default)
        index = optional[1] if optional else index
    while len(args) < macro.params:
        index = _skip_spaces(text, index)
        group = _group(text, index)
        if group is None:
            token = _CALL_RE.match(text, index)
            if token is None:
                return None
            group = token.group(0), token.end()
        args.append(group[0])
        index = group[1]
    return tuple(args)


def _expanded_calls(text: str, macros: dict[str, list[_Macro]], wrappers: dict[str, _Wrapper]) -> set[str]:
    """id якорей на каждого автора, до которых доходят вызовы макросов из `text` (подстановка `#1`...`#9`)."""
    found: set[str] = set()
    seen: set[tuple[str, int, tuple[str, ...]]] = set()
    queue: list[tuple[str, int]] = [(text, 0)]
    while queue and len(seen) < _MAX_EXPANSIONS:
        current, depth = queue.pop()
        found.update(i for i in _calls("", current, wrappers) if i.partition(".")[0].endswith(_author_marker()))
        if depth >= _MAX_DEPTH:
            continue
        for call in _CALL_RE.finditer(current):
            name = call.group(1)
            for number, macro in enumerate(macros.get(name, ())):
                args = _arguments(current, call.end(), macro)
                if args is None or (name, number, args) in seen:
                    continue
                seen.add((name, number, args))
                body = macro.body
                for position, value in enumerate(args, start=1):
                    body = body.replace(f"#{position}", value)
                queue.append((body, depth + 1))
    return found


def _author_marker() -> str:
    return author_anchor_id("", _ANY_AUTHOR)


def _input_key(rel: str) -> str:
    """Путь без `.j2`, `.tex` и кода языка: так `\\input` называет любую редакцию файла."""
    return _LANG_SUFFIX_RE.sub("", rel.removesuffix(".j2").removesuffix(".tex"))


def _reached(top: str, own: dict[str, str], common: dict[str, str]) -> dict[str, str]:
    """Файлы документа и общие файлы, которые они подключают (`\\input`, в том числе через другие общие)."""
    by_key: dict[str, list[str]] = {}
    for rel in common:
        by_key.setdefault(_input_key(rel), []).append(rel)
    reached = dict(own)
    queue = list(own.values())
    while queue:
        for ref in _INPUT_RE.findall(queue.pop()):
            key = _input_key(posixpath.normpath(posixpath.join(top, ref.strip())))
            for rel in by_key.get(key, ()):
                if rel not in reached:
                    reached[rel] = common[rel]
                    queue.append(common[rel])
    return reached


def _scan(files_dir: Path, top: str, common: dict[str, str], wrappers: dict[str, _Wrapper]) -> _Sources:
    sources = _Sources()
    own = {f.relative_to(files_dir).as_posix(): _text(f) for f in _tex_files(files_dir, top)}
    for rel, text in {**own, **common}.items():
        for anchor_id in _calls(rel, text, wrappers):
            sources.add(anchor_id, rel)
    sources.includes_macros = any(_ANCHORS_INPUT_RE.search(text) for text in own.values())
    _scan_macros(sources, top, own, common, wrappers)
    return sources


def _scan_macros(
    sources: _Sources, top: str, own: dict[str, str], common: dict[str, str], wrappers: dict[str, _Wrapper]
) -> None:
    """Якоря на каждого автора, которые документ ставит через макросы (имя и вызов якоря в разных местах)."""
    if not any(_AUTHOR_MARK in text for text in (*own.values(), *common.values())):
        return
    macros, rest = _split_macros({**common, **own})
    for rel, text in _reached(top, own, common).items():
        for anchor_id in _expanded_calls(rest.get(rel, text), macros, wrappers):
            sources.add(anchor_id, rel)


@dataclass(frozen=True)
class _Entry:
    where: str
    doc_id: str
    anchor: str


def _entries(slot_id: str, slot: dict[str, Any], errors: list[str]) -> list[_Entry]:
    """Записи слота на якоре; битые записи уже назвали проверки мест и меток даты."""
    where = f"signatures.slots[{slot_id}]"
    return [
        *_placement_entries(where, slot),
        *_default_entries(where, slot, errors),
        *_date_entries(where, slot),
    ]


def _placement_entries(where: str, slot: dict[str, Any]) -> list[_Entry]:
    try:
        entries = slot_placement_entries(slot.get("placements"))
    except TypeError:
        return []
    found: list[_Entry] = []
    for doc_id, item in entries:
        try:
            place = parse_slot_placement(item, f"placements.{doc_id}")
        except (TypeError, ValueError, KeyError):
            continue
        if isinstance(place, AnchorPlace):
            found.append(_Entry(f"{where}: placements.{doc_id}", doc_id, place.anchor))
    return found


def _default_entries(where: str, slot: dict[str, Any], errors: list[str]) -> list[_Entry]:
    """`default_placement` на якоре: по записи на каждый документ слота; без запасного места в мм это ошибка."""
    default = slot.get("default_placement")
    if not isinstance(default, dict) or "anchor" not in default:
        return []
    try:
        anchor = parse_default_anchor(default).anchor
    except (TypeError, ValueError, KeyError) as exc:
        errors.append(f"{where}: {exc}")
        return []
    applies = slot.get("applies_to", [])
    docs = applies if isinstance(applies, list) else [applies]
    return [_Entry(f"{where}: default_placement", str(doc_id), anchor) for doc_id in docs]


def _date_entries(where: str, slot: dict[str, Any]) -> list[_Entry]:
    try:
        dates = parse_default_dates(slot.get("default_dates"))
    except (TypeError, ValueError, KeyError):
        return []
    return [
        _Entry(f"{where}: default_dates.{doc_id}", doc_id, mark.anchor)
        for doc_id, marks in dates
        for mark in marks
        if isinstance(mark, AnchorDate)
    ]


def _doc_tops(version_dir: Path, manifest: dict[str, Any]) -> dict[str, set[str]]:
    """id документа → каталоги его исходников (первый сегмент `source_file` документа и его вариантов)."""
    tops: dict[str, set[str]] = {}
    for entry in manifest.get("documents", []) or []:
        if isinstance(entry, str):
            doc_path = version_dir / "files" / entry / PACK_DOC_MANIFEST
            data = yaml.safe_load(doc_path.read_text(encoding="utf-8")) if doc_path.exists() else {}
            doc_id = entry
        elif isinstance(entry, dict):
            data, doc_id = entry, str(entry.get("id", "?"))
        else:
            continue
        data = data or {}
        sources = [data.get("source_file")]
        sources += [v.get("source_file") for v in data.get("variants", []) or [] if isinstance(v, dict)]
        tops[doc_id] = {str(src).split("/", 1)[0] for src in sources if src}
    return tops


def lint_anchors(version_dir: Path, manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Ошибки и предупреждения мест на якорях версии (см. модуль)."""
    errors: list[str] = []
    warnings: list[str] = []
    signatures = manifest.get("signatures")
    signatures = signatures if isinstance(signatures, dict) else {}
    slots = {str(s["id"]): s for s in signatures.get("slots", []) or [] if isinstance(s, dict) and s.get("id")}
    try:
        macros = parse_anchor_macros(signatures.get("anchor_macros"))
    except (TypeError, ValueError) as exc:
        errors.append(f"signatures.anchor_macros: {exc}")
        macros = ()
    entries = [entry for slot_id, slot in slots.items() for entry in _entries(slot_id, slot, errors)]
    files_dir = version_dir / "files"
    if entries and not (files_dir / ANCHORS_FILE).is_file():
        errors.append(f"signatures: места на якорях, но в версии нет {ANCHORS_FILE} (копия эталона Студии)")
    sources = _sources(version_dir, manifest, macros)
    scans, wrappers = sources.scans, sources.wrappers
    for doc_id in sorted({entry.doc_id for entry in entries}):
        doc_scans = scans.get(doc_id, [])
        if doc_scans and not any(scan.includes_macros for scan in doc_scans):
            errors.append(f"документ {doc_id}: места на якорях, но исходник не подключает {ANCHORS_FILE} (\\input)")
    errors.extend(
        f"{entry.where}: якоря {entry.anchor!r} нет в исходниках документа {entry.doc_id} и в common/ "
        f"(\\hseSignAnchor, \\hseDateAnchor или обёртка из anchor_macros)"
        for entry in entries
        if not any(_present(entry.anchor, scan.found) for scan in scans.get(entry.doc_id, []))
    )
    warnings.extend(_source_warnings(files_dir, sources.rels, wrappers, set(slots)))
    return errors, warnings


@dataclass(frozen=True)
class _VersionSources:
    """Вызовы якорей по документам версии, обёртки и все просмотренные файлы."""

    scans: dict[str, list[_Sources]]
    wrappers: dict[str, _Wrapper]
    rels: set[str]


def _sources(version_dir: Path, manifest: dict[str, Any], macros: tuple[str, ...]) -> _VersionSources:
    files_dir = version_dir / "files"
    common = {f.relative_to(files_dir).as_posix(): _text(f) for f in _tex_files(files_dir, "common")}
    tops = _doc_tops(version_dir, manifest)
    own = {top: _text_map(files_dir, top) for doc_tops in tops.values() for top in doc_tops}
    wrappers = _wrappers({**common, **{k: v for texts in own.values() for k, v in texts.items()}}, macros)
    scans = {
        doc_id: [_scan(files_dir, top, common, wrappers) for top in sorted(doc_tops)]
        for doc_id, doc_tops in tops.items()
    }
    rels = {*common, *(rel for texts in own.values() for rel in texts)}
    return _VersionSources(scans, wrappers, rels)


def author_anchor_names(version_dir: Path, manifest: dict[str, Any]) -> dict[str, set[str]]:
    """id документа → имена якорей подписи, которые его исходники (или `common/`) ставят на каждого автора
    (`\\hseSignAnchor{author__{{ a.slug }}}` или обёртка из `anchor_macros` с таким именем, 15.17.20)."""
    signatures = manifest.get("signatures")
    signatures = signatures if isinstance(signatures, dict) else {}
    try:
        macros = parse_anchor_macros(signatures.get("anchor_macros"))
    except (TypeError, ValueError):
        macros = ()
    marker = author_anchor_id("", _ANY_AUTHOR)
    return {
        doc_id: {found[: -len(marker)] for scan in doc_scans for found in scan.found if found.endswith(marker)}
        for doc_id, doc_scans in _sources(version_dir, manifest, macros).scans.items()
    }


def _text_map(files_dir: Path, top: str) -> dict[str, str]:
    return {f.relative_to(files_dir).as_posix(): _text(f) for f in _tex_files(files_dir, top)}


def _source_warnings(files_dir: Path, rels: set[str], wrappers: dict[str, _Wrapper], slot_ids: set[str]) -> list[str]:
    """Имя якоря не id слота каталога (опечатка) и одно имя дважды в одном файле."""
    warnings: list[str] = []
    for rel in sorted(rels):
        ids = _calls(rel, _text(files_dir / rel), wrappers)
        names = sorted({split_author_name(anchor_id.partition(".")[0])[0] for anchor_id in ids} - slot_ids)
        warnings.extend(f"{rel}: якорь {name!r} не id слота каталога подписей (опечатка?)" for name in names)
        warnings.extend(
            f"{rel}: якорь {anchor_id!r} стоит в файле {count} раза, место встанет по первому"
            for anchor_id, count in sorted(Counter(ids).items())
            if count > 1
        )
    return warnings
