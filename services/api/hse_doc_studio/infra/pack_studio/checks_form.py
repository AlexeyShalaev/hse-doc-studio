"""Файлы правил `checks/*.yaml` и `checks_version` формой (docs/design/template-studio.md, 5.7, срез T14).

Порт `IPackChecksForm`. Правила читаются как у лоадера (`_parse_check_rule`, шапка как у `_parse_check_source`), с
индексами в списке YAML. Запись идёт точечными правками (`yaml_edits`, D11): правило пишется в порядке ключей
паков (`id`, `title`, `description`, `category`, `applies_to`, `default_severity`, `engine`, `params`), правка
правила меняет только известные форме ключи (незнакомые остаются), параметры правятся по ключам: неизменённые
остаются байт в байт.

Каждая правка проверяет себя: после неё в файле не должно появиться новых проблем строгого разбора (правило,
которое лоадер выбросит, повтор id, шапка без `label` или `ref` в обоих языках, линтер это требует). Проблемы,
которые были до правки, её не запрещают.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

import yaml

from hse_doc_studio.core.enums import CheckEngine
from hse_doc_studio.core.pack_studio.checks_form import (
    OVERRIDE_SEVERITIES,
    RULE_SEVERITIES,
    ChecksConfig,
    ChecksEditError,
    ChecksFileView,
    ChecksHeader,
    ChecksOp,
    ChecksOpKind,
    RuleEntry,
)
from hse_doc_studio.core.pack_studio.submission import Indexed
from hse_doc_studio.infra.pack_studio.yaml_edits import YamlEditError, delete, insert_item, move_item, set_value
from hse_doc_studio.infra.template.yaml_template_repository import _parse_check_rule

_LOADER: Any = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
_RULES = ("rules",)
_CONFIG = "checks_version"
_PARSE_ERRORS = (TypeError, ValueError, KeyError, AttributeError)
_MISSING = object()
_LANGS = ("ru", "en")
_ENGINES = tuple(engine.value for engine in CheckEngine)
# Ключи правила, которые знает форма; прочие ключи правила она не трогает.
_RULE_KEYS = ("id", "title", "description", "category", "applies_to", "default_severity", "engine", "params")

Path = tuple[str | int, ...]


# ── чтение ──────────────────────────────────────────────────────────────────


def _load(text: str) -> dict[str, Any]:
    try:
        data = yaml.load(text, Loader=_LOADER)  # noqa: S506 — безопасный загрузчик (CSafeLoader или SafeLoader)
    except yaml.YAMLError as exc:
        raise ValueError(f"the file is not valid YAML: {exc}") from None
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise TypeError("the file is not a mapping")
    return data


def _localized(raw: Any) -> dict[str, str]:
    if isinstance(raw, dict):
        return {str(k): str(v) for k, v in raw.items() if v is not None}
    if isinstance(raw, str):
        return {"ru": raw}
    return {}


def _error(exc: BaseException) -> str:
    if isinstance(exc, KeyError):
        return f"missing key {str(exc).strip(chr(39))!r}"[:300]
    return str(exc)[:300]


def _header(data: dict[str, Any]) -> ChecksHeader:
    source = data.get("source")
    source = source if isinstance(source, dict) else {}
    url = source.get("url")
    return ChecksHeader(
        label=_localized(data.get("label")),
        ref=_localized(data.get("ref")),
        source={str(k): str(v) for k, v in source.items() if k != "url" and v is not None},
        url=str(url) if url else None,
    )


def _checked_kind(raw: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """Важность, движок и параметры правила: значение, которого лоадер не знает, это ошибка."""
    severity = raw.get("default_severity") or raw.get("severity") or "warn"
    if severity not in RULE_SEVERITIES:
        raise ValueError(f"default_severity {severity!r} is not one of {list(RULE_SEVERITIES)}")
    engine = raw.get("engine", "structural")
    if engine not in _ENGINES:
        raise ValueError(f"engine {engine!r} is not one of {list(_ENGINES)}")
    params = raw.get("params") or {}
    if not isinstance(params, dict):
        raise TypeError("params must be a mapping")
    return str(severity), str(engine), params


def _applies(raw: Any) -> tuple[str, ...] | None:
    if raw == "*":
        return None
    if not isinstance(raw, list | str):
        raise TypeError("applies_to must be '*' or a list of document ids")
    return tuple(str(a) for a in (raw if isinstance(raw, list) else [raw]))


def _rule(raw: Any) -> RuleEntry:
    """Правило строго: то, что лоадер молча выбросит или прочитает не так, это ошибка."""
    if not isinstance(raw, dict):
        raise TypeError("a rule must be a mapping with id")
    rule_id = raw["id"]
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise ValueError("id must be a non-empty string")
    severity, engine, params = _checked_kind(raw)
    applies = _applies(raw.get("applies_to", "*"))
    if _parse_check_rule(raw) is None:
        raise ValueError("the loader drops this rule")
    category = raw.get("category")
    return RuleEntry(
        id=rule_id,
        title=_localized(raw.get("title")),
        description=_localized(raw.get("description")),
        category=str(category) if category is not None else None,
        applies_to=applies,
        default_severity=severity,
        engine=engine,
        params=params,
    )


def _raw_rules(data: dict[str, Any]) -> list[Any]:
    rules = data.get("rules")
    return rules if isinstance(rules, list) else []


def _header_problems(data: dict[str, Any]) -> Iterator[str]:
    if data.get("rules") is not None and not isinstance(data.get("rules"), list):
        yield "rules must be a list"
    if not _raw_rules(data):
        return
    for key in ("label", "ref"):
        block = data.get(key)
        if not isinstance(block, dict) or any(not str(block.get(lang) or "").strip() for lang in _LANGS):
            yield f"{key}.ru and {key}.en are required: the interface shows the group by them"


def _problems(data: dict[str, Any]) -> Counter[str]:
    """Проблемы файла правил без индексов: перестановка правил их не меняет."""
    found: Counter[str] = Counter(_header_problems(data))
    ids: Counter[str] = Counter()
    for raw in _raw_rules(data):
        try:
            ids[_rule(raw).id] += 1
        except _PARSE_ERRORS as exc:
            owner = raw.get("id", "?") if isinstance(raw, dict) else "?"
            found[f"rule {owner}: {_error(exc)}"] += 1
    found.update({f"rule id {rule_id!r} is repeated": count - 1 for rule_id, count in ids.items() if count > 1})
    return found


def _checked(before: str, after: str) -> str:
    added = _problems(_load(after)) - _problems(_load(before))
    if added:
        raise ChecksEditError(next(iter(added)))
    return after


# ── запись ──────────────────────────────────────────────────────────────────


def _node(text: str, path: Path) -> Any:
    node: Any = _load(text)
    for key in path:
        if isinstance(node, dict):
            node = node.get(key, _MISSING)
        elif isinstance(node, list) and isinstance(key, int) and 0 <= key < len(node):
            node = node[key]
        else:
            return _MISSING
        if node is _MISSING:
            return _MISSING
    return node


def _need[T](value: T | None, name: str) -> T:
    if value is None:
        raise ChecksEditError(f"the operation needs {name}")
    return value


def _clean(value: Mapping[str, str]) -> dict[str, str]:
    return {lang: text.strip() for lang, text in value.items() if text.strip()}


def _rule_value(rule: RuleEntry) -> dict[str, Any]:
    if not rule.id.strip():
        raise ChecksEditError("the rule id is empty")
    if rule.default_severity not in RULE_SEVERITIES:
        raise ChecksEditError(f"default_severity must be one of {list(RULE_SEVERITIES)}")
    if rule.engine not in _ENGINES:
        raise ChecksEditError(f"engine must be one of {list(_ENGINES)}")
    value: dict[str, Any] = {"id": rule.id.strip(), "title": _clean(rule.title)}
    description = _clean(rule.description)
    if description:
        value["description"] = description
    if rule.category and rule.category.strip():
        value["category"] = rule.category.strip()
    value["applies_to"] = list(dict.fromkeys(rule.applies_to)) if rule.applies_to is not None else "*"
    value["default_severity"] = rule.default_severity
    value["engine"] = rule.engine
    if rule.params:
        value["params"] = dict(rule.params)
    return value


def _as_form(raw: Any) -> dict[str, Any]:
    """Правило так, как его видит и пишет форма; битое правило пусто."""
    try:
        return _rule_value(_rule(raw))
    except (*_PARSE_ERRORS, ChecksEditError):
        return {}


def _set_keys(text: str, path: Path, value: Mapping[str, Any]) -> str:
    """Известные ключи правила по `value` (нет в `value`: ключ уходит), незнакомые остаются как были.

    Ключ, который для формы не изменился, остаётся байт в байт, даже если форма видит его иначе, чем он записан:
    выпущенные паки бывают с текстом через запятую без кавычек (`{ ru: Поля (ЕСПД, рамка), en: ... }`).
    """
    current = _node(text, path)
    if not isinstance(current, dict):
        return set_value(text, path, dict(value))
    seen = _as_form(current)
    kept = {k for k in value if k in current and seen.get(k) == value[k]}
    merged = {
        k: (v if k in kept or k not in _RULE_KEYS else value[k])
        for k, v in current.items()
        if k in value or k not in _RULE_KEYS
    }
    merged.update({k: v for k, v in value.items() if k not in merged})
    # `severity` старых паков заменяется ключом, который читает лоадер.
    if "default_severity" in value and "default_severity" not in kept:
        merged.pop("severity", None)
    return set_value(text, path, merged)


def _rules(text: str) -> list[Any]:
    rules = _node(text, _RULES)
    if rules is not _MISSING and rules is not None and not isinstance(rules, list):
        raise ChecksEditError("rules is not a list: fix it in the source")
    return rules if isinstance(rules, list) else []


def _index(rules: list[Any], op: ChecksOp) -> int:
    index = _need(op.index, "a rule index")
    if not 0 <= index < len(rules):
        raise ChecksEditError(f"there is no rule {index}")
    return index


def _set_localized(text: str, key: str, value: dict[str, str]) -> str:
    """`label` или `ref`: без изменений для формы запись остаётся как есть, пустое значение убирает ключ."""
    current = _node(text, (key,))
    if not value:
        return delete(text, (key,)) if current is not _MISSING else text
    if current is not _MISSING and _clean(_localized(current)) == value:
        return text
    return set_value(text, (key,), value)


def _set_header(text: str, op: ChecksOp) -> str:
    header = _need(op.header, "a header")
    text = _set_localized(text, "label", _clean(header.label))
    text = _set_localized(text, "ref", _clean(header.ref))
    source: dict[str, Any] = _clean(header.source)
    if header.url and header.url.strip():
        source["url"] = header.url.strip()
    current = _node(text, ("source",))
    if not source:
        return delete(text, ("source",)) if current is not _MISSING else text
    if not isinstance(current, dict):
        return set_value(text, ("source",), source, after="ref")
    if {k: str(v).strip() for k, v in current.items() if v is not None} == source:
        return text
    merged = {k: source[k] for k in current if k in source}
    merged.update({k: v for k, v in source.items() if k not in merged})
    return set_value(text, ("source",), merged)


def _add_rule(text: str, op: ChecksOp) -> str:
    value = _rule_value(_need(op.rule, "a rule"))
    rules = _rules(text)
    seed = {"id": value["id"]}
    if rules:
        text = insert_item(text, _RULES, len(rules), seed, block=True)
        return set_value(text, (*_RULES, len(rules)), value)
    text = set_value(text, _RULES, [seed], block=True)
    return set_value(text, (*_RULES, 0), value)


def _set_rule(text: str, op: ChecksOp) -> str:
    index = _index(_rules(text), op)
    return _set_keys(text, (*_RULES, index), _rule_value(_need(op.rule, "a rule")))


def _remove_rule(text: str, op: ChecksOp) -> str:
    return delete(text, (*_RULES, _index(_rules(text), op)))


def _move_rule(text: str, op: ChecksOp) -> str:
    rules = _rules(text)
    index = _index(rules, op)
    to = _need(op.to, "a target index")
    if not 0 <= to < len(rules):
        raise ChecksEditError(f"cannot move rule {index} to {to}")
    return move_item(text, _RULES, index, to)


_HANDLERS: dict[ChecksOpKind, Callable[[str, ChecksOp], str]] = {
    ChecksOpKind.set_header: _set_header,
    ChecksOpKind.add_rule: _add_rule,
    ChecksOpKind.set_rule: _set_rule,
    ChecksOpKind.remove_rule: _remove_rule,
    ChecksOpKind.move_rule: _move_rule,
}


def _indexed_rules(data: dict[str, Any]) -> Iterator[Indexed[RuleEntry]]:
    for i, raw in enumerate(_raw_rules(data)):
        try:
            yield Indexed(i, _rule(raw))
        except _PARSE_ERRORS as exc:
            yield Indexed(i, None, _error(exc))


def _strings(raw: Any) -> tuple[str, ...]:
    return tuple(str(v) for v in raw) if isinstance(raw, list) else ()


def _config_value(config: ChecksConfig) -> dict[str, Any]:
    overrides = dict(config.severity_override or {})
    bad = [severity for severity in overrides.values() if severity not in OVERRIDE_SEVERITIES]
    if bad:
        raise ChecksEditError(f"severity_override values must be one of {list(OVERRIDE_SEVERITIES)}")
    return {
        "disabled_categories": list(dict.fromkeys(config.disabled_categories)),
        "disabled": list(dict.fromkeys(config.disabled)),
        "severity_override": overrides,
    }


class PackChecksFormEditor:
    """Реализация порта `IPackChecksForm` (core/pack_studio/protocols.py)."""

    def describe_file(self, text: str, prefix: str) -> ChecksFileView:
        data = _load(text)
        problems = list(_problems(data))
        return ChecksFileView(
            header=_header(data),
            prefix=prefix,
            rules=tuple(_indexed_rules(data)),
            error=problems[0] if problems else None,
        )

    def apply_file(self, text: str, ops: Sequence[ChecksOp]) -> str:
        before = text
        for op in ops:
            try:
                text = _HANDLERS[op.op](text, op)
            except YamlEditError as exc:
                raise ChecksEditError(str(exc)) from None
        return _checked(before, text) if text != before else text

    def describe_config(self, text: str) -> ChecksConfig:
        raw = _load(text).get(_CONFIG)
        raw = raw if isinstance(raw, dict) else {}
        overrides = raw.get("severity_override")
        return ChecksConfig(
            disabled_categories=_strings(raw.get("disabled_categories")),
            disabled=_strings(raw.get("disabled")),
            severity_override={str(k): str(v) for k, v in overrides.items()} if isinstance(overrides, dict) else {},
        )

    def apply_config(self, text: str, config: ChecksConfig) -> str:
        value = _config_value(config)
        current = _node(text, (_CONFIG,))
        try:
            if not isinstance(current, dict) or not current:
                # Новый блок строками, значения по одному: короткие списки и словари одной строкой.
                text = set_value(text, (_CONFIG,), {"disabled_categories": value["disabled_categories"]}, block=True)
            for key, item in value.items():
                text = set_value(text, (_CONFIG, key), item)
        except YamlEditError as exc:
            raise ChecksEditError(str(exc)) from None
        return text
