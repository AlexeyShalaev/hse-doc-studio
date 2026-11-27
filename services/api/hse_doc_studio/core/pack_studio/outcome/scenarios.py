"""Сценарии Студии шаблонов: файл `<пак>/templates/<шаблон>/scenarios/<id>.yaml` (дизайн результата, раздел 5).

Сценарий это именованная точка в пространстве вводных и необязательное ожидание: `snapshot` (сжатый результат,
`Digest`) и (или) `assertions` закрытого набора. Файл лежит рядом с `examples/`, вне каталога версии, поэтому дайджест
выпущенной версии не меняется; лоадер паков его не читает.

Здесь только формат: разбор текста и словаря в модель с проверкой структуры (`ScenarioError` с путём и причиной),
канонический YAML (`scenario_text`: один и тот же сценарий всегда пишется одним и тем же текстом, круг
«разбор, запись» байт в байт) и шаблоны номеров версий. Допустимость вводных относительно версии проверяет прогон
(`use_cases/pack_studio/outcome/scenario_runner.py`): вводная, которой в версии нет, это статус `error` сценария, а не
отказ записи, потому что сценарий переживает версии.

Строгая модель контракта (`api/schemas/pack_studio_outcome.py`, `PackScenario`) и эта модель описывают один формат;
соответствие держит контрактный тест на эталонах.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from dataclasses import field as _field
from typing import Any, Literal

import yaml

from hse_doc_studio.core.pack_studio.outcome.model import (
    SECTIONS,
    Digest,
    DigestPoint,
    DocumentStateName,
    SectionPrint,
)

FORMAT = 1
SCENARIOS_DIR = "scenarios"
SCENARIO_SUFFIX = ".yaml"

MAX_ID = 64
MAX_NAME_LANGS = 4
MAX_TEXT = 2000
MAX_INPUTS = 64
MAX_INPUT_VALUE = 128
MAX_VERSIONS = 16
MAX_VERSION_PATTERN = 64
MAX_ASSERTIONS = 64
MAX_STEPS = 16
MAX_COUNT = 1000
MAX_SCENARIOS = 200

_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_VERSION_PATTERN_RE = re.compile(r"^[0-9A-Za-z._*-]+$")
_LANG_RE = re.compile(r"^[a-z]{2,3}$")
_DOCUMENT_STATES: tuple[str, ...] = ("active", "inactive", "absent")
_BOOL_TRUE, _BOOL_FALSE = "yes", "no"

# Допустимые комбинации ключей `Mapping` в разборе: лишний ключ это ошибка формата, а не молчаливая потеря.
type Data = Mapping[str, Any]


class ScenarioError(ValueError):
    """Файл или тело запроса не соответствуют формату сценария. `reason` это путь и причина (`assertions[2].kind: ...`);
    на границе это `scenario_invalid`."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


# ── Утверждения ──────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class DocumentStateAssertion:
    kind: Literal["document_state"] = _field(default="document_state", init=False)
    doc: str = ""
    state: DocumentStateName = "active"


@dataclass(frozen=True, slots=True)
class DocumentCountAssertion:
    kind: Literal["document_count"] = _field(default="document_count", init=False)
    state: DocumentStateName = "active"
    count: int = 0


@dataclass(frozen=True, slots=True)
class MetaVisibleAssertion:
    kind: Literal["meta_visible"] = _field(default="meta_visible", init=False)
    field: str = ""
    visible: bool = True


@dataclass(frozen=True, slots=True)
class ParticipantAssertion:
    kind: Literal["participant_present"] = _field(default="participant_present", init=False)
    persona: str = ""
    present: bool = True


@dataclass(frozen=True, slots=True)
class ItemActiveAssertion:
    kind: Literal["item_active"] = _field(default="item_active", init=False)
    point: str = ""
    doc: str = ""
    active: bool = True


@dataclass(frozen=True, slots=True)
class RouteStepsAssertion:
    kind: Literal["route_steps"] = _field(default="route_steps", init=False)
    point: str = ""
    steps: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True, slots=True)
class RoutePairAssertion:
    kind: Literal["route_pair"] = _field(default="route_pair", init=False)
    point: str = ""
    doc: str = ""
    slot: str = ""
    persona: str = ""
    present: bool = True
    # Подпись маршрута необязательна (True) или обязательна (False); None: не проверяется, ключ в файле не пишется.
    optional: bool | None = None


type Assertion = (
    DocumentStateAssertion
    | DocumentCountAssertion
    | MetaVisibleAssertion
    | ParticipantAssertion
    | ItemActiveAssertion
    | RouteStepsAssertion
    | RoutePairAssertion
)

# Ключи каждого вида утверждения по порядку записи: имя поля и способ разобрать значение. Способ с «?» в конце это
# необязательный ключ: без него (или с null) поле остаётся None и в файл не пишется.
_ASSERTION_FIELDS: dict[str, tuple[type[Assertion], tuple[tuple[str, str], ...]]] = {
    "document_state": (DocumentStateAssertion, (("doc", "id"), ("state", "state"))),
    "document_count": (DocumentCountAssertion, (("state", "state"), ("count", "count"))),
    "meta_visible": (MetaVisibleAssertion, (("field", "id"), ("visible", "bool"))),
    "participant_present": (ParticipantAssertion, (("persona", "id"), ("present", "bool"))),
    "item_active": (ItemActiveAssertion, (("point", "id"), ("doc", "id"), ("active", "bool"))),
    "route_steps": (RouteStepsAssertion, (("point", "id"), ("steps", "steps"))),
    "route_pair": (
        RoutePairAssertion,
        (("point", "id"), ("doc", "id"), ("slot", "id"), ("persona", "id"), ("present", "bool"), ("optional", "bool?")),
    ),
}
ASSERTION_KINDS: tuple[str, ...] = tuple(_ASSERTION_FIELDS)


@dataclass(frozen=True, slots=True)
class Scenario:
    """Сценарий целиком. `inputs` частичные (остальное по умолчанию), `versions` шаблоны номеров (пусто: любая)."""

    name: dict[str, str]
    description: dict[str, str] = _field(default_factory=dict)
    example: str | None = None
    inputs: dict[str, str] = _field(default_factory=dict)
    versions: tuple[str, ...] = ()
    snapshot: Digest | None = None
    assertions: tuple[Assertion, ...] = ()
    format: int = _field(default=FORMAT, init=False)

    @property
    def has_expectation(self) -> bool:
        return self.snapshot is not None or bool(self.assertions)


# ── Идентификатор и версии ───────────────────────────────────────────────────


def is_scenario_id(value: str) -> bool:
    """Строчная латиница, цифры и дефис между ними, до 64 знаков."""
    return len(value) <= MAX_ID and _ID_RE.match(value) is not None


def check_scenario_id(value: str) -> str:
    if not is_scenario_id(value):
        raise ScenarioError("id: lowercase Latin letters, digits and hyphens between them, up to 64 characters")
    return value


def scenario_file_name(scenario_id: str) -> str:
    return f"{check_scenario_id(scenario_id)}{SCENARIO_SUFFIX}"


def scenario_id_of(file_name: str) -> str | None:
    """Идентификатор по имени файла (`company-supervisor.yaml`); None, если файл не сценарий (чужое имя или суффикс)."""
    if not file_name.endswith(SCENARIO_SUFFIX):
        return None
    stem = file_name.removesuffix(SCENARIO_SUFFIX)
    return stem if is_scenario_id(stem) else None


def version_matches(patterns: Iterable[str], version: str) -> bool:
    """Подходит ли версия под список шаблонов; пустой список подходит любой. `*` это любая последовательность знаков
    (`2026.1.*` подходит `2026.1.6`, но не `2026.1`), остальное буквально."""
    given = tuple(patterns)
    if not given:
        return True
    return any(
        re.fullmatch(".*".join(re.escape(part) for part in pattern.split("*")), version) is not None
        for pattern in given
    )


# ── Разбор ───────────────────────────────────────────────────────────────────


def parse_scenario(text: str) -> Scenario:
    """Сценарий из текста YAML. Незнакомые ключи, чужие типы и выход за пределы это `ScenarioError`."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" (line {mark.line + 1})" if mark is not None else ""
        raise ScenarioError(f"yaml: not a valid YAML document{where}") from None
    if not isinstance(data, dict):
        raise ScenarioError("the file must be a mapping with format, name, inputs")
    return scenario_from_data(data)


def parse_scenario_files(files: Mapping[str, bytes]) -> dict[str, Scenario | str]:
    """Файлы папки сценариев (имя файла -> содержимое) в разобранные сценарии по id; значение `str` это ошибка файла.
    Файлы не `*.yaml` сценарием не считаются, не больше `MAX_SCENARIOS` по порядку имён."""
    parsed: dict[str, Scenario | str] = {}
    for name in sorted(n for n in files if n.endswith(SCENARIO_SUFFIX))[:MAX_SCENARIOS]:
        stem = name.removesuffix(SCENARIO_SUFFIX)
        try:
            check_scenario_id(stem)
            parsed[stem] = parse_scenario(files[name].decode("utf-8"))
        except ScenarioError as exc:
            parsed[stem] = exc.reason
        except UnicodeDecodeError:
            parsed[stem] = "the file is not UTF-8"
    return parsed


def scenario_from_data(data: Data) -> Scenario:
    """Сценарий из словаря: из разобранного YAML или тела запроса (там пустые ключи могут быть `None`)."""
    _only(data, ("format", "name", "description", "example", "inputs", "versions", "snapshot", "assertions"), "")
    if data.get("format") != FORMAT or isinstance(data.get("format"), bool):
        raise ScenarioError(f"format: only {FORMAT} is supported")
    name = _localized(data.get("name"), "name", required=True)
    description = _localized(data.get("description"), "description", required=False)
    example = _optional_text(data.get("example"), "example", 255)
    inputs = _inputs(data.get("inputs"))
    versions = _versions(data.get("versions"))
    snapshot = _snapshot(data["snapshot"]) if data.get("snapshot") is not None else None
    assertions = _assertions(data.get("assertions"))
    return Scenario(
        name=name,
        description=description,
        example=example,
        inputs=inputs,
        versions=versions,
        snapshot=snapshot,
        assertions=assertions,
    )


def _only(data: Data, allowed: tuple[str, ...], where: str) -> None:
    for key in data:
        if key not in allowed:
            raise ScenarioError(f"{where + '.' if where else ''}{key}: unknown key")


def _text(value: Any, where: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ScenarioError(f"{where}: a non-empty string is expected")
    if len(value) > limit:
        raise ScenarioError(f"{where}: longer than {limit} characters")
    if any(ord(ch) < 0x20 and ch not in "\n\t" for ch in value):
        raise ScenarioError(f"{where}: control characters are not allowed")
    return value


def _optional_text(value: Any, where: str, limit: int) -> str | None:
    return None if value is None else _text(value, where, limit)


def _localized(value: Any, where: str, *, required: bool) -> dict[str, str]:
    if value is None:
        if required:
            raise ScenarioError(f"{where}: a mapping of language to text is required")
        return {}
    if not isinstance(value, Mapping) or (required and not value):
        raise ScenarioError(f"{where}: a mapping of language to text is required")
    if len(value) > MAX_NAME_LANGS:
        raise ScenarioError(f"{where}: more than {MAX_NAME_LANGS} languages")
    out: dict[str, str] = {}
    for lang, text in value.items():
        if not isinstance(lang, str) or _LANG_RE.match(lang) is None:
            raise ScenarioError(f"{where}: language key must be a short lowercase code, got {lang!r}")
        out[lang] = _text(text, f"{where}.{lang}", MAX_TEXT)
    return out


def _input_value(value: Any, where: str) -> str:
    """Значения вводных строки; логическое значение YAML (`yes`, `no` без кавычек) это `yes` и `no`."""
    if isinstance(value, bool):
        return _BOOL_TRUE if value else _BOOL_FALSE
    if not isinstance(value, str) or not value:
        raise ScenarioError(f"{where}: a non-empty string is expected")
    if len(value) > MAX_INPUT_VALUE:
        raise ScenarioError(f"{where}: longer than {MAX_INPUT_VALUE} characters")
    return value


def _inputs(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ScenarioError("inputs: a mapping of input to value is expected")
    if len(value) > MAX_INPUTS:
        raise ScenarioError(f"inputs: more than {MAX_INPUTS} inputs")
    out: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not key or len(key) > MAX_INPUT_VALUE:
            raise ScenarioError(f"inputs: bad input name {key!r}")
        out[key] = _input_value(item, f"inputs.{key}")
    return out


def _versions(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > MAX_VERSIONS:
        raise ScenarioError(f"versions: a list of up to {MAX_VERSIONS} version patterns is expected")
    out: list[str] = []
    for index, item in enumerate(value):
        # Номера в YAML без кавычек (`2026.1`) разбираются числом: шаблон номера всегда строка.
        if not isinstance(item, str) or not _VERSION_PATTERN_RE.match(item) or len(item) > MAX_VERSION_PATTERN:
            raise ScenarioError(f'versions[{index}]: a quoted pattern like "2026.1.*" is expected')
        out.append(item)
    return tuple(out)


def _id(value: Any, where: str) -> str:
    return _text(value, where, 128)


def _bool(value: Any, where: str) -> bool:
    if not isinstance(value, bool):
        raise ScenarioError(f"{where}: true or false is expected")
    return value


def _state(value: Any, where: str) -> DocumentStateName:
    if value not in _DOCUMENT_STATES:
        raise ScenarioError(f"{where}: one of {', '.join(_DOCUMENT_STATES)} is expected")
    return value


def _count(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= MAX_COUNT:
        raise ScenarioError(f"{where}: an integer from 0 to {MAX_COUNT} is expected")
    return value


def _id_list(value: Any, where: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ScenarioError(f"{where}: a list is expected")
    return tuple(_id(item, f"{where}[{i}]") for i, item in enumerate(value))


def _steps(value: Any, where: str) -> tuple[tuple[str, ...], ...]:
    if not isinstance(value, list) or len(value) > MAX_STEPS:
        raise ScenarioError(f"{where}: a list of up to {MAX_STEPS} steps is expected")
    return tuple(_id_list(step, f"{where}[{i}]") for i, step in enumerate(value))


_PARSERS: dict[str, Callable[[Any, str], Any]] = {
    "id": _id,
    "bool": _bool,
    "bool?": _bool,
    "state": _state,
    "count": _count,
    "steps": _steps,
}


def _assertions(value: Any) -> tuple[Assertion, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > MAX_ASSERTIONS:
        raise ScenarioError(f"assertions: a list of up to {MAX_ASSERTIONS} assertions is expected")
    return tuple(_assertion(item, f"assertions[{index}]") for index, item in enumerate(value))


def _assertion(value: Any, where: str) -> Assertion:
    if not isinstance(value, Mapping):
        raise ScenarioError(f"{where}: a mapping with kind is expected")
    kind = value.get("kind")
    known = _ASSERTION_FIELDS.get(kind) if isinstance(kind, str) else None
    if known is None:
        raise ScenarioError(f"{where}.kind: unknown kind {kind!r}, expected one of {', '.join(ASSERTION_KINDS)}")
    cls, spec = known
    _only(value, ("kind", *(name for name, _ in spec)), where)
    args: dict[str, Any] = {}
    for name, how in spec:
        if how.endswith("?") and value.get(name) is None:
            continue
        if name not in value:
            raise ScenarioError(f"{where}.{name}: required for {kind}")
        args[name] = _PARSERS[how](value[name], f"{where}.{name}")
    assertion = cls(**args)
    if isinstance(assertion, RoutePairAssertion) and assertion.optional is not None and not assertion.present:
        raise ScenarioError(f"{where}.optional: only with present: true")
    return assertion


def _snapshot(value: Any) -> Digest:
    if not isinstance(value, Mapping):
        raise ScenarioError("snapshot: a mapping is expected")
    _only(value, ("documents", "participants", "meta_visible", "points", "sections"), "snapshot")
    documents_raw = value.get("documents", {})
    if not isinstance(documents_raw, Mapping):
        raise ScenarioError("snapshot.documents: a mapping of document to state is expected")
    documents = {
        _id(doc, "snapshot.documents"): _state(state, f"snapshot.documents.{doc}")
        for doc, state in documents_raw.items()
    }
    points_raw = value.get("points", [])
    sections_raw = value.get("sections", [])
    if not isinstance(points_raw, list) or not isinstance(sections_raw, list):
        raise ScenarioError("snapshot: points and sections are lists")
    return Digest(
        documents=documents,
        participants=_id_list(value.get("participants", []), "snapshot.participants"),
        meta_visible=_id_list(value.get("meta_visible", []), "snapshot.meta_visible"),
        points=tuple(_digest_point(p, f"snapshot.points[{i}]") for i, p in enumerate(points_raw)),
        sections=tuple(_section_print(s, f"snapshot.sections[{i}]") for i, s in enumerate(sections_raw)),
    )


def _digest_point(value: Any, where: str) -> DigestPoint:
    if not isinstance(value, Mapping):
        raise ScenarioError(f"{where}: a mapping is expected")
    _only(value, ("id", "items", "steps", "pairs"), where)
    for key in ("id", "items", "steps", "pairs"):
        if key not in value:
            raise ScenarioError(f"{where}.{key}: required")
    return DigestPoint(
        id=_id(value["id"], f"{where}.id"),
        items=_id_list(value["items"], f"{where}.items"),
        steps=_steps(value["steps"], f"{where}.steps"),
        pairs=_count(value["pairs"], f"{where}.pairs"),
    )


def _section_print(value: Any, where: str) -> SectionPrint:
    if not isinstance(value, Mapping):
        raise ScenarioError(f"{where}: a mapping is expected")
    _only(value, ("section", "fingerprint", "count"), where)
    section = value.get("section")
    if section not in SECTIONS:
        raise ScenarioError(f"{where}.section: one of {', '.join(SECTIONS)} is expected")
    fingerprint = value.get("fingerprint")
    if isinstance(fingerprint, int) and not isinstance(fingerprint, bool):
        # Хэш из одних цифр YAML без кавычек читает числом: возвращаем исходную запись нельзя, поэтому отказ.
        raise ScenarioError(f"{where}.fingerprint: quote the fingerprint, YAML read it as a number")
    return SectionPrint(
        section=section,
        fingerprint=_text(fingerprint, f"{where}.fingerprint", 64),
        count=_count(value.get("count"), f"{where}.count"),
    )


# ── Канонический YAML ────────────────────────────────────────────────────────

_PLAIN_RE = re.compile(r"^[\w][\w .,:()/+-]*$")
_PLAIN_FLOW_RE = re.compile(r"^[\w][\w./-]*$")


def _scalar(value: str, *, flow: bool = False) -> str:
    """Строка в YAML: без кавычек, если запись читается обратно тем же текстом, иначе JSON в двойных кавычках.
    Внутри `[...]` и `{...}` (`flow`) без кавычек только слова, точки, дефисы и косые черты."""
    plain = _PLAIN_FLOW_RE if flow else _PLAIN_RE
    if plain.match(value) and not value.endswith(" ") and _reads_back(value, value):
        return value
    return json.dumps(value, ensure_ascii=False)


def _reads_back(text: str, expected: object) -> bool:
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError:
        return False
    return type(loaded) is type(expected) and bool(loaded == expected)


def _flow_list(items: Iterable[str]) -> str:
    return "[" + ", ".join(_scalar(item, flow=True) for item in items) + "]"


def _flow_steps(steps: Iterable[Iterable[str]]) -> str:
    return "[" + ", ".join(_flow_list(step) for step in steps) + "]"


def _key(value: str) -> str:
    return _scalar(value)


def _assertion_line(assertion: Assertion) -> str:
    spec = _ASSERTION_FIELDS[assertion.kind][1]
    parts = [f"kind: {assertion.kind}"]
    for name, how in spec:
        item = getattr(assertion, name)
        if item is None:
            continue
        if how in {"bool", "bool?"}:
            rendered = "true" if item else "false"
        elif how == "count":
            rendered = str(item)
        elif how == "steps":
            rendered = _flow_steps(item)
        else:
            rendered = _scalar(item, flow=True)
        parts.append(f"{name}: {rendered}")
    return "  - { " + ", ".join(parts) + " }"


def _localized_lines(key: str, value: Mapping[str, str]) -> list[str]:
    return [f"{key}:", *(f"  {lang}: {_scalar(text)}" for lang, text in value.items())]


def _snapshot_lines(snapshot: Digest) -> list[str]:
    lines = ["snapshot:"]
    if snapshot.documents:
        lines.append("  documents:")
        lines.extend(f"    {_key(doc)}: {state}" for doc, state in snapshot.documents.items())
    else:
        lines.append("  documents: {}")
    lines.append(f"  participants: {_flow_list(snapshot.participants)}")
    if snapshot.meta_visible:
        lines.append("  meta_visible:")
        lines.extend(f"    - {_scalar(field_id)}" for field_id in snapshot.meta_visible)
    else:
        lines.append("  meta_visible: []")
    if snapshot.points:
        lines.append("  points:")
        for point in snapshot.points:
            lines.append(f"    - id: {_scalar(point.id)}")
            lines.append(f"      items: {_flow_list(point.items)}")
            lines.append(f"      steps: {_flow_steps(point.steps)}")
            lines.append(f"      pairs: {point.pairs}")
    else:
        lines.append("  points: []")
    if snapshot.sections:
        lines.append("  sections:")
        lines.extend(
            f"    - {{ section: {p.section}, fingerprint: {_scalar(p.fingerprint, flow=True)}, count: {p.count} }}"
            for p in snapshot.sections
        )
    else:
        lines.append("  sections: []")
    return lines


def scenario_text(scenario: Scenario) -> str:
    """Канонический YAML сценария: порядок ключей и вид записи фиксированы, пустые необязательные ключи опущены.

    Круг `parse_scenario(scenario_text(s)) == s` и `scenario_text(parse_scenario(t)) == t` для канонического `t`."""
    lines = [f"format: {FORMAT}", *_localized_lines("name", scenario.name)]
    if scenario.description:
        lines.extend(_localized_lines("description", scenario.description))
    if scenario.example is not None:
        lines.append(f"example: {_scalar(scenario.example)}")
    if scenario.versions:
        lines.append("versions: [" + ", ".join(json.dumps(v) for v in scenario.versions) + "]")
    if scenario.inputs:
        lines.append("inputs:")
        # `yes` и `no` без кавычек YAML читает логическим значением: `_scalar` их заключает в кавычки.
        lines.extend(f"  {_key(key)}: {_scalar(value)}" for key, value in scenario.inputs.items())
    else:
        lines.append("inputs: {}")
    if scenario.assertions:
        lines.append("assertions:")
        lines.extend(_assertion_line(a) for a in scenario.assertions)
    if scenario.snapshot is not None:
        lines.extend(_snapshot_lines(scenario.snapshot))
    return "\n".join(lines) + "\n"


__all__ = [
    "ASSERTION_KINDS",
    "FORMAT",
    "MAX_SCENARIOS",
    "SCENARIOS_DIR",
    "SCENARIO_SUFFIX",
    "Assertion",
    "DocumentCountAssertion",
    "DocumentStateAssertion",
    "ItemActiveAssertion",
    "MetaVisibleAssertion",
    "ParticipantAssertion",
    "RoutePairAssertion",
    "RouteStepsAssertion",
    "Scenario",
    "ScenarioError",
    "check_scenario_id",
    "is_scenario_id",
    "parse_scenario",
    "parse_scenario_files",
    "scenario_file_name",
    "scenario_from_data",
    "scenario_id_of",
    "scenario_text",
    "version_matches",
]
