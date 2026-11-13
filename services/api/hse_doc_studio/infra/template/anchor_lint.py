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
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from hse_doc_studio.core.catalog import AnchorDate, AnchorPlace
from hse_doc_studio.core.signatures.anchors import NAME_RE
from hse_doc_studio.infra.project_init.template_renderer import PACK_DOC_MANIFEST
from hse_doc_studio.infra.template.yaml_template_repository import (
    parse_anchor_macros,
    parse_default_anchor,
    parse_default_dates,
    parse_slot_placement,
    slot_placement_entries,
)

_NAME = NAME_RE.pattern
_OPT = r"(?:\[[^\]]*\])?"
_SIGN_RE = re.compile(rf"\\hseSignAnchor\s*{_OPT}\s*\{{\s*({_NAME})\s*\}}")
_DATE_RE = re.compile(rf"\\hseDateAnchor\s*{_OPT}\s*\{{\s*({_NAME})\s*\}}\s*\{{\s*({_NAME})\s*\}}")
# Вызов якоря внутри определения обёртки: имя это параметр (`#1`).
_SIGN_PARAM_RE = re.compile(rf"\\hseSignAnchor\s*{_OPT}\s*\{{\s*#\d\s*\}}")
_DATE_PARAM_RE = re.compile(rf"\\hseDateAnchor\s*{_OPT}\s*\{{\s*#\d\s*\}}\s*\{{\s*({_NAME})\s*\}}")
_ANCHORS_INPUT_RE = re.compile(r"\\input\s*\{[^}]*common/anchors(?:\.tex)?\s*\}")
_DEFINITION_START_RE = re.compile(r"\\(?:newcommand|renewcommand|providecommand|NewDocumentCommand|def)\b")
_COMMENT_RE = re.compile(r"(?<!\\)%.*")
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


def _calls(rel: str, text: str, wrappers: dict[str, _Wrapper]) -> list[str]:
    """id якорей, которые ставит файл: прямые вызовы и обёртки с `[имя]`."""
    ids = [m.group(1) for m in _SIGN_RE.finditer(text)]
    ids += [f"{m.group(1)}.{m.group(2)}" for m in _DATE_RE.finditer(text)]
    for macro, wrapper in wrappers.items():
        for m in re.finditer(rf"\\{macro}\s*\[\s*({_NAME})\s*\]", text):
            name = m.group(1)
            if wrapper.sign:
                ids.append(name)
            ids += [f"{name}.{part}" for part in wrapper.parts]
    return ids


def _scan(files_dir: Path, top: str, common: dict[str, str], wrappers: dict[str, _Wrapper]) -> _Sources:
    sources = _Sources()
    own = {f.relative_to(files_dir).as_posix(): _text(f) for f in _tex_files(files_dir, top)}
    for rel, text in {**own, **common}.items():
        for anchor_id in _calls(rel, text, wrappers):
            sources.add(anchor_id, rel)
    sources.includes_macros = any(_ANCHORS_INPUT_RE.search(text) for text in own.values())
    return sources


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
    common = {f.relative_to(files_dir).as_posix(): _text(f) for f in _tex_files(files_dir, "common")}
    tops = _doc_tops(version_dir, manifest)
    own = {top: _text_map(files_dir, top) for doc_tops in tops.values() for top in doc_tops}
    wrappers = _wrappers({**common, **{k: v for texts in own.values() for k, v in texts.items()}}, macros)
    if entries and not (files_dir / ANCHORS_FILE).is_file():
        errors.append(f"signatures: места на якорях, но в версии нет {ANCHORS_FILE} (копия эталона Студии)")
    scans = {
        doc_id: [_scan(files_dir, top, common, wrappers) for top in sorted(doc_tops)]
        for doc_id, doc_tops in tops.items()
    }
    for doc_id in sorted({entry.doc_id for entry in entries}):
        doc_scans = scans.get(doc_id, [])
        if doc_scans and not any(scan.includes_macros for scan in doc_scans):
            errors.append(f"документ {doc_id}: места на якорях, но исходник не подключает {ANCHORS_FILE} (\\input)")
    errors.extend(
        f"{entry.where}: якоря {entry.anchor!r} нет в исходниках документа {entry.doc_id} и в common/ "
        f"(\\hseSignAnchor, \\hseDateAnchor или обёртка из anchor_macros)"
        for entry in entries
        if not any(entry.anchor in scan.found for scan in scans.get(entry.doc_id, []))
    )
    rels = {*common, *(rel for texts in own.values() for rel in texts)}
    warnings.extend(_source_warnings(files_dir, rels, wrappers, set(slots)))
    return errors, warnings


def _text_map(files_dir: Path, top: str) -> dict[str, str]:
    return {f.relative_to(files_dir).as_posix(): _text(f) for f in _tex_files(files_dir, top)}


def _source_warnings(files_dir: Path, rels: set[str], wrappers: dict[str, _Wrapper], slot_ids: set[str]) -> list[str]:
    """Имя якоря не id слота каталога (опечатка) и одно имя дважды в одном файле."""
    warnings: list[str] = []
    for rel in sorted(rels):
        ids = _calls(rel, _text(files_dir / rel), wrappers)
        names = sorted({anchor_id.partition(".")[0] for anchor_id in ids} - slot_ids)
        warnings.extend(f"{rel}: якорь {name!r} не id слота каталога подписей (опечатка?)" for name in names)
        warnings.extend(
            f"{rel}: якорь {anchor_id!r} стоит в файле {count} раза, место встанет по первому"
            for anchor_id, count in sorted(Counter(ids).items())
            if count > 1
        )
    return warnings
