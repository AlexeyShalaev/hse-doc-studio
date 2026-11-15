r"""Диагностики и подсказки редактора Студии шаблонов (docs/design/template-studio.md, 4.4 и 5.4; срез T8).

Проверки те же, что у `hse-doc-studio pack check` (`check.py`): `pack_lint` версии и схемы манифестов. Здесь они
раскладываются по файлам и строкам, чтобы редактор показал их в строке, а панель «Проблемы» вела к месту:

* находки схемы получают строку узла по пути в данных (`yaml.compose`, позиции узлов);
* сообщения линтера разбираются по своим префиксам (`files/...:строка:`, `checks/x.yaml:`, `version.yaml:`,
  `[ru] doc.tex: \input{...}`, путь файла версии); прочие относятся к версии целиком (`path` None).

Подсказки автодополнения: поля анкеты версии (`meta_fields`) и макросы `\hse...`, которые объявляют её динамические
инклуды (разбор `core/meta_usage.py`, без исполнения Jinja).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml
from yaml.nodes import MappingNode, Node, SequenceNode

from hse_doc_studio.core.meta_usage import parse_include, strip_tex_comments
from hse_doc_studio.core.pack_studio.entities import (
    DiagnosticCheck,
    DiagnosticSeverity,
    MacroHint,
    MetaFieldHint,
    PackDiagnostic,
    PackEditorHints,
)
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.infra.pack_studio import pack_schemas
from hse_doc_studio.infra.template.pack_lint import lint_version_dir

VERSION_MANIFEST = "version.yaml"
FILES_DIR = "files"
CHECKS_DIR = "checks"
# Больше находок редактору не нужно: длинный список читают в CLI.
MAX_FINDINGS = 500
# Шаблон инклуда больше этого не разбирается для подсказок.
MAX_INCLUDE_BYTES = 512 * 1024
# Пакам вне версии нужна только схема: `pack.yaml`, `template.yaml`, `releases.yaml`.
_MANIFEST_SCHEMAS = {"pack.yaml": "pack", "template.yaml": "template", "releases.yaml": "releases"}
_LOADER: Any = getattr(yaml, "CSafeLoader", yaml.SafeLoader)

_FILE_LINE = re.compile(r"^(?P<rel>[^\s:\[\]]+\.[A-Za-z0-9]+):(?P<line>\d+): ")
_CHECKS_FILE = re.compile(r"^checks/(?P<name>[^\s:/]+\.ya?ml):")
_VERSION_FILE = re.compile(r"^version\.yaml:")
_INPUT_MISSING = re.compile(r"^\[(?P<lang>[\w-]+)\] (?P<bare>[^\s:]+): \\input\{(?P<target>[^}]*)\}")
_LEADING_PATH = re.compile(r"^(?P<rel>[^\s:\[\]]+\.[A-Za-z0-9]+):")
_DOC_SOURCE = re.compile(r"^\[[\w-]+\] документ (?P<doc>[\w-]+): source_file")


class PackInspector:
    """Порт `IPackInspector`: проверки и подсказки по файлам под папкой паков."""

    def lint_version(self, root: Path, version_dir: str, *, released: bool) -> tuple[PackDiagnostic, ...]:
        vdir = _inside(root, version_dir)
        if not (vdir / VERSION_MANIFEST).is_file():
            raise PackStudioError(PackStudioErrorCode.file_not_found, path=f"{version_dir}/{VERSION_MANIFEST}")
        findings = list(_lint(vdir, version_dir))
        schema_severity = DiagnosticSeverity.warning if released else DiagnosticSeverity.error
        findings.extend(
            _schema(vdir / VERSION_MANIFEST, f"{version_dir}/{VERSION_MANIFEST}", "version", schema_severity)
        )
        files = vdir / FILES_DIR
        for doc in sorted(files.rglob("doc.yaml")) if files.is_dir() else ():
            rel = f"{version_dir}/{doc.relative_to(vdir).as_posix()}"
            findings.extend(_schema(doc, rel, "doc", schema_severity))
        return tuple(findings[:MAX_FINDINGS])

    def check_manifest(self, root: Path, path: str) -> tuple[PackDiagnostic, ...] | None:
        name = _MANIFEST_SCHEMAS.get(path.rsplit("/", 1)[-1].lower())
        if name is None or not _is_manifest_place(path, name):
            return None
        target = _inside(root, path)
        if not target.is_file():
            raise PackStudioError(PackStudioErrorCode.file_not_found, path=path)
        return tuple(_schema(target, path, name, DiagnosticSeverity.error)[:MAX_FINDINGS])

    def hints(self, root: Path, version_dir: str) -> PackEditorHints:
        vdir = _inside(root, version_dir)
        try:
            text = (vdir / VERSION_MANIFEST).read_text(encoding="utf-8")
            manifest = yaml.load(text, Loader=_LOADER) or {}  # noqa: S506 — безопасный загрузчик
        except (OSError, UnicodeDecodeError, yaml.YAMLError):
            return PackEditorHints(version=version_dir)
        if not isinstance(manifest, Mapping):
            return PackEditorHints(version=version_dir)
        return PackEditorHints(
            version=version_dir,
            meta_fields=tuple(_meta_fields(manifest.get("meta_fields"))),
            macros=tuple(_macros(vdir, version_dir, manifest.get("dynamic_includes"))),
        )


# ── пути ────────────────────────────────────────────────────────────────────


def _inside(root: Path, rel: str) -> Path:
    """Путь под папкой паков без выхода наружу через символьные ссылки."""
    base = root.resolve()
    target = (root / rel).resolve()
    if target != base and base not in target.parents:
        raise PackStudioError(PackStudioErrorCode.path_not_allowed)
    return target


def _is_manifest_place(path: str, name: str) -> bool:
    depth = len(path.split("/"))
    return {"pack": 2, "template": 4, "releases": 4}[name] == depth


# ── линтер ──────────────────────────────────────────────────────────────────


def _lint(vdir: Path, version_dir: str) -> Iterable[PackDiagnostic]:
    try:
        report = lint_version_dir(vdir)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        yield PackDiagnostic(
            DiagnosticSeverity.error,
            DiagnosticCheck.lint,
            f"{VERSION_MANIFEST} не разобран: {_one_line(exc)}",
            path=f"{version_dir}/{VERSION_MANIFEST}",
            line=mark.line + 1 if mark is not None else None,
        )
        return
    except (OSError, UnicodeDecodeError, TypeError, ValueError, AttributeError) as exc:
        yield PackDiagnostic(
            DiagnosticSeverity.error, DiagnosticCheck.lint, f"{VERSION_MANIFEST} не разобран: {_one_line(exc)}"
        )
        return
    locator = _LintLocator(vdir, version_dir)
    for severity, messages in (
        (DiagnosticSeverity.error, report.errors),
        (DiagnosticSeverity.warning, report.warnings),
    ):
        for message in messages:
            path, line = locator.locate(message)
            yield PackDiagnostic(severity, DiagnosticCheck.lint, message, path=path, line=line)


Site = tuple[str | None, int | None]


class _LintLocator:
    """Файл и строка находки линтера по префиксу сообщения; не нашлось: версия целиком."""

    def __init__(self, vdir: Path, version_dir: str) -> None:
        self._vdir = vdir
        self._version_dir = version_dir
        self._files = vdir / FILES_DIR
        # Разобранный `version.yaml` (узлы с позициями); False: не разобран.
        self._manifest: Node | bool | None = None

    def locate(self, message: str) -> Site:
        for probe in (self._file_line, self._known_file, self._input, self._leading_path):
            site = probe(message)
            if site is not None:
                return site
        line = self._manifest_line(message)
        return (self._manifest_path, line) if line is not None else (None, None)

    @property
    def _manifest_path(self) -> str:
        return f"{self._version_dir}/{VERSION_MANIFEST}"

    def _file_line(self, message: str) -> Site | None:
        """`report/main.tex:3: Jinja ...`: файл в `files/` и строка."""
        found = _FILE_LINE.match(message)
        if found and (self._files / found["rel"]).is_file():
            return self._rel(FILES_DIR, found["rel"]), int(found["line"])
        return None

    def _known_file(self, message: str) -> Site | None:
        """`checks/x.yaml: ...`, `version.yaml: ...`, `[ru] документ X: source_file ...`."""
        found = _CHECKS_FILE.match(message)
        if found:
            return self._rel(CHECKS_DIR, found["name"]), None
        if _VERSION_FILE.match(message) or _DOC_SOURCE.match(message):
            return self._manifest_path, None
        return None

    def _input(self, message: str) -> Site | None:
        found = _INPUT_MISSING.match(message)
        return self._input_site(found["bare"], found["lang"], found["target"]) if found else None

    def _leading_path(self, message: str) -> Site | None:
        """Сообщение начинается с пути файла версии (`files/` или от каталога версии)."""
        found = _LEADING_PATH.match(message)
        if not found:
            return None
        rel = found["rel"]
        if (self._files / rel).is_file():
            return self._rel(FILES_DIR, rel), None
        if (self._vdir / rel).is_file():
            return f"{self._version_dir}/{rel}", None
        return None

    def _manifest_line(self, message: str) -> int | None:
        """Строка `version.yaml` по пути в начале сообщения: `signatures.slots[author]: placements.report: ...`."""
        steps = _message_steps(message)
        if not steps:
            return None
        if self._manifest is None:
            try:
                text = (self._vdir / VERSION_MANIFEST).read_text(encoding="utf-8")
                self._manifest = yaml.compose(text, Loader=_LOADER) or False
            except (OSError, UnicodeDecodeError, yaml.YAMLError):
                self._manifest = False
        if not isinstance(self._manifest, MappingNode):
            return None
        return _walk_steps(self._manifest, steps)

    def _rel(self, folder: str, rel: str) -> str:
        return f"{self._version_dir}/{folder}/{rel}"

    def _input_site(self, bare: str, lang: str, target: str) -> Site:
        """Файл с `\\input` (языковая редакция или bare) и строка, где он подключает отсутствующий файл."""
        stem, dot, ext = bare.rpartition(".")
        for candidate in (f"{stem}.{lang}.{ext}" if dot else bare, bare):
            path = self._files / candidate
            if not path.is_file():
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                return self._rel(FILES_DIR, candidate), None
            for number, text in enumerate(lines, start=1):
                if f"{{{target}}}" in text and not text.lstrip().startswith("%"):
                    return self._rel(FILES_DIR, candidate), number
            return self._rel(FILES_DIR, candidate), None
        return None, None


# ── схемы ───────────────────────────────────────────────────────────────────


def _schema(file: Path, rel: str, name: str, severity: DiagnosticSeverity) -> list[PackDiagnostic]:
    try:
        text = file.read_text(encoding="utf-8")
        data = yaml.load(text, Loader=_LOADER)  # noqa: S506 — безопасный загрузчик (SafeLoader или CSafeLoader)
        tree = yaml.compose(text, Loader=_LOADER)
    except (OSError, UnicodeDecodeError) as exc:
        return [PackDiagnostic(DiagnosticSeverity.error, DiagnosticCheck.schema, _one_line(exc), path=rel)]
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        return [
            PackDiagnostic(
                DiagnosticSeverity.error,
                DiagnosticCheck.schema,
                f"YAML не разобран: {_one_line(exc)}",
                path=rel,
                line=mark.line + 1 if mark is not None else None,
            )
        ]
    return [
        PackDiagnostic(
            severity,
            DiagnosticCheck.schema,
            f"{pack_schemas.pointer_of(where)}: {message}",
            path=rel,
            line=line_of(tree, where),
            pointer=pack_schemas.pointer_of(where),
        )
        for where, message in pack_schemas.validation_errors(name, data)
    ]


def line_of(tree: Node | None, where: Iterable[str | int]) -> int | None:
    """Строка (с единицы) узла по пути в данных; пути нет целиком: строка ближайшего найденного предка."""
    if tree is None:
        return None
    node: Node = tree
    line = node.start_mark.line + 1
    for part in where:
        if isinstance(node, MappingNode):
            entry = next(((k, v) for k, v in node.value if str(k.value) == str(part)), None)
            if entry is None:
                break
            key, node = entry
            line = key.start_mark.line + 1
        elif isinstance(node, SequenceNode) and isinstance(part, int) and 0 <= part < len(node.value):
            node = node.value[part]
            line = node.start_mark.line + 1
        else:
            break
    return line


_STEP = re.compile(r"(?P<key>[A-Za-z_][\w-]*)(?:\[(?P<sel>[^\]]+)\])?")
_STEPS = re.compile(r"[A-Za-z_][\w-]*(?:\[[^\]]+\])?(?:\.[A-Za-z_][\w-]*(?:\[[^\]]+\])?)*")


def _message_steps(message: str) -> list[tuple[str, str | None]]:
    """Шаги пути из ведущих сегментов сообщения до первого, который путём не выглядит."""
    steps: list[tuple[str, str | None]] = []
    for segment in message.split(": ")[:-1]:
        if not _STEPS.fullmatch(segment):
            break
        steps.extend((m["key"], m["sel"]) for m in _STEP.finditer(segment))
    return steps


def _walk_steps(root: MappingNode, steps: list[tuple[str, str | None]]) -> int | None:
    """Строка самого глубокого найденного узла; первый шаг обязан быть ключом верхнего уровня."""
    node: Node = root
    line: int | None = None
    for key, selector in steps:
        child = _mapping_child(node, key)
        if child is None:
            break
        line, node = child
        if selector is None:
            continue
        picked = _select(node, selector)
        if picked is None:
            break
        line, node = picked
    return line


def _mapping_child(node: Node, key: str) -> tuple[int, Node] | None:
    if not isinstance(node, MappingNode):
        return None
    for k, v in node.value:
        if str(k.value) == key:
            return k.start_mark.line + 1, v
    return None


def _select(node: Node, selector: str) -> tuple[int, Node] | None:
    """`[author]`: элемент списка с `id: author` (или ключ словаря); `[2]`: элемент по индексу."""
    if isinstance(node, MappingNode):
        return _mapping_child(node, selector.strip("'\""))
    if not isinstance(node, SequenceNode):
        return None
    if selector.isdigit() and int(selector) < len(node.value):
        item = node.value[int(selector)]
        return item.start_mark.line + 1, item
    wanted = selector.strip("'\"")
    for item in node.value:
        found = _mapping_child(item, "id")
        if found is not None and str(getattr(found[1], "value", "")) == wanted:
            return item.start_mark.line + 1, item
    return None


def _one_line(exc: BaseException) -> str:
    return " ".join(str(exc).split())[:300]


# ── подсказки ───────────────────────────────────────────────────────────────


def _localized(value: Any) -> dict[str, str] | None:
    if isinstance(value, Mapping):
        out = {str(k): str(v) for k, v in value.items() if isinstance(v, str | int | float)}
        return out or None
    if isinstance(value, str):
        return {"ru": value}
    return None


def _meta_fields(raw: Any) -> Iterable[MetaFieldHint]:
    if not isinstance(raw, Mapping):
        return
    for key, spec in raw.items():
        if not isinstance(key, str):
            continue
        spec_map = spec if isinstance(spec, Mapping) else {}
        kind = spec_map.get("type")
        group = spec_map.get("group")
        yield MetaFieldHint(
            key=key,
            type=kind if isinstance(kind, str) else None,
            label=_localized(spec_map.get("label")),
            group=group if isinstance(group, str) else None,
        )


def _macros(vdir: Path, version_dir: str, raw: Any) -> Iterable[MacroHint]:
    if not isinstance(raw, list):
        return
    seen: set[str] = set()
    for include in raw:
        template = include.get("template") if isinstance(include, Mapping) else None
        text = _include_text(vdir / FILES_DIR, template)
        if text is None:
            continue
        keys_of = _keys_by_macro(text)
        source = f"{version_dir}/{FILES_DIR}/{template}"
        for name in _defined_macros(text):
            if name not in seen and not name.startswith("if"):
                seen.add(name)
                yield MacroHint(name=name, keys=tuple(sorted(keys_of.get(name, ()))), source=source)


def _keys_by_macro(text: str) -> dict[str, set[str]]:
    """Макрос инклуда в ключи полей, которые он печатает (обратное к разбору `meta_usage`)."""
    keys_of: dict[str, set[str]] = {}
    for key, names in parse_include(text).macros.items():
        for name in names:
            keys_of.setdefault(name, set()).add(key)
    return keys_of


def _include_text(files: Path, template: Any) -> str | None:
    """Текст шаблона инклуда из `files/` версии; путь наружу, нет файла или слишком большой: None."""
    if not isinstance(template, str) or template.startswith("/") or ".." in template.split("/"):
        return None
    path = files / template
    try:
        if not path.is_file() or path.stat().st_size > MAX_INCLUDE_BYTES:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


_DEFINITION = re.compile(r"\\(?:newcommand|renewcommand|providecommand|def)\*?\s*\{?\\(?P<cmd>[A-Za-z@]+)")


def _defined_macros(text: str) -> list[str]:
    """Имена макросов, которые инклуд объявляет, в порядке объявления (без `@`-служебных)."""
    names: list[str] = []
    for found in _DEFINITION.finditer(strip_tex_comments(text)):
        name = found["cmd"]
        if "@" not in name and name not in names:
            names.append(name)
    return names
