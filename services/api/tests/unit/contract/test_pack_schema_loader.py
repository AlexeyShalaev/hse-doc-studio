"""Схема и лоадер согласованы: что схема пака допускает, лоадер разбирает целиком (template-studio.md, D12).

Выборка: hypothesis строит манифесты по самим схемам `contracts/pack/*.schema.json`, каждый образец сначала
проходит схему, затем лоадер Студии, и ни один элемент не должен выпасть (лоадер терпим и молча отбрасывает битое,
поэтому сверяются количества). Правила, которые JSON Schema не выражает (рамка внутри листа A4: `x_mm + width_mm`,
подсказка срока без конкретных дат), стратегии соблюдают сами: они описаны в `description` схемы.
"""

from __future__ import annotations

import math
import string
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml
from hse_doc_studio.core.catalog import ANCHOR_DATE_HEIGHT_MM, AnchorDate, AnchorPlace, TemplateVersion
from hse_doc_studio.infra.template.releases import load_releases
from hse_doc_studio.infra.template.yaml_template_repository import _parse_pack, _parse_template_info, _parse_version
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from tests.unit.contract.pack_schemas import registry, schemas, validator

_SETTINGS = settings(
    max_examples=40,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
_MAX_ITEMS = 2
_TEXT = st.text(alphabet=string.ascii_letters + string.digits + " _-ёжЖ", min_size=1, max_size=12)
_FORMATS = ("day", "month_word", "month_number", "year", "year_short", "date_numeric", "date_long")
_NAME = st.from_regex(r"[a-z][a-z0-9_]{0,10}", fullmatch=True)


def _opt(draw: st.DrawFn, out: dict[str, Any], key: str, strategy: st.SearchStrategy[Any]) -> None:
    if draw(st.booleans()):
        out[key] = draw(strategy)


def _mm(low: float, high: float, *, exclude_low: bool = False) -> st.SearchStrategy[float]:
    floats = st.floats(low, high, allow_nan=False, exclude_min=exclude_low)
    whole = range(math.floor(low) + 1, math.ceil(high))
    return (st.one_of(st.sampled_from(whole), floats) if whole else floats).map(float)


def _num(definition: str, key: str, high: float | None = None) -> st.SearchStrategy[float]:
    """Число поля из пределов самой схемы (`common.schema.json`): ослабленный предел схемы попадёт в выборку."""
    prop = schemas()["common"]["$defs"][definition]["properties"][key]
    low = prop.get("minimum", prop.get("exclusiveMinimum", 0))
    top = prop.get("maximum", 200)
    return _mm(low, top if high is None else min(top, high), exclude_low="exclusiveMinimum" in prop)


@st.composite
def _place(draw: st.DrawFn, *, anchor: bool = False, fallback: bool | None = None) -> dict[str, Any]:
    """Место в мм или на якоре: рамка внутри листа по ширине (`x_mm + width_mm <= 210`)."""
    definition = "anchorPlacement" if anchor else "mmPlacement"
    out: dict[str, Any] = {}
    if anchor:
        out["anchor"] = draw(_NAME)
        _opt(draw, out, "align", st.sampled_from(["left", "center", "right"]))
        _opt(draw, out, "dx_mm", _num(definition, "dx_mm"))
        _opt(draw, out, "dy_mm", _num(definition, "dy_mm"))
        _opt(draw, out, "width_mm", _num(definition, "width_mm"))
    if not anchor or (fallback if fallback is not None else draw(st.booleans())):
        width = out.setdefault("width_mm", draw(_num(definition, "width_mm")))
        out["x_mm"] = draw(_num(definition, "x_mm", 210.0 - width))
        out["y_mm"] = draw(_num(definition, "y_mm"))
        _opt(draw, out, "page", st.integers(1, 9))
    return out


@st.composite
def _date_mark(draw: st.DrawFn, *, anchor: bool) -> dict[str, Any]:
    """Метка даты: рамка внутри листа A4; на якоре без `format` часть якоря это формат."""
    definition = "anchorDateMark" if anchor else "mmDateMark"
    out: dict[str, Any] = {}
    if anchor:
        named_part = draw(st.booleans())
        part = draw(st.sampled_from(_FORMATS)) if named_part else draw(_NAME)
        out["anchor"] = f"{draw(_NAME)}.{part}"
        if not named_part or draw(st.booleans()):
            out["format"] = draw(st.sampled_from(_FORMATS))
        _opt(draw, out, "height_mm", _num(definition, "height_mm"))
        _opt(draw, out, "dx_mm", _num(definition, "dx_mm"))
        _opt(draw, out, "dy_mm", _num(definition, "dy_mm"))
        _opt(draw, out, "width_mm", _num(definition, "width_mm"))
    else:
        out["format"] = draw(st.sampled_from(_FORMATS))
        out["height_mm"] = draw(_num(definition, "height_mm", 20))
    _opt(draw, out, "align", st.sampled_from(["left", "center", "right"]))
    if not anchor or draw(st.booleans()):
        height = out.get("height_mm", ANCHOR_DATE_HEIGHT_MM)
        width = out.setdefault("width_mm", draw(_num(definition, "width_mm")))
        out["x_mm"] = draw(_num(definition, "x_mm", 210.0 - width))
        out["y_mm"] = draw(_num(definition, "y_mm", 297.0 - height))
        _opt(draw, out, "page", st.integers(1, 9))
    return out


_HINT = st.text(alphabet=string.ascii_letters + " ,;абвгд", min_size=1, max_size=200).filter(str.strip)

# Определения схем с правилами, которых JSON Schema не выражает: их строят стратегии выше.
_OVERRIDES: dict[str, st.SearchStrategy[Any]] = {
    "mmPlacement": _place(),
    "anchorPlacement": _place(anchor=True),
    "defaultPlacement": st.one_of(_place(), _place(anchor=True, fallback=True)),
    "mmDateMark": _date_mark(anchor=False),
    "anchorDateMark": _date_mark(anchor=True),
    "hintText": _HINT,
}


def _from_schema(schema: Any, resolver: Any) -> st.SearchStrategy[Any]:  # noqa: C901, PLR0911, PLR0912
    """Стратегия образцов по схеме (то подмножество JSON Schema, которым написаны схемы пака)."""
    if schema is True or not {"$ref", "const", "enum", "oneOf", "anyOf", "allOf", "type"} & set(schema):
        return st.one_of(st.none(), st.booleans(), _TEXT)  # любое значение (`required_for`)
    if "$ref" in schema:
        ref = schema["$ref"]
        name = ref.rsplit("/", 1)[-1]
        if name in _OVERRIDES:
            return _OVERRIDES[name]
        resolved = resolver.lookup(ref)
        return st.deferred(lambda: _from_schema(resolved.contents, resolved.resolver))
    if "const" in schema:
        return st.just(schema["const"])
    if "enum" in schema:
        return st.sampled_from(schema["enum"])
    for key in ("oneOf", "anyOf"):
        if key in schema:
            return st.one_of(*(_from_schema(sub, resolver) for sub in schema[key]))
    if "allOf" in schema:
        # Слияние частей: ссылка на определение и уточнение (`required`). Ссылки внутри части разрешаются от её файла.
        merged: dict[str, Any] = {}
        for sub in schema["allOf"]:
            part = sub
            if "$ref" in sub:
                resolved = resolver.lookup(sub["$ref"])
                part, resolver = resolved.contents, resolved.resolver
            merged = {**merged, **part, "required": sorted({*merged.get("required", []), *part.get("required", [])})}
        return _from_schema(merged, resolver)
    kind = schema.get("type")
    if isinstance(kind, list):
        return st.one_of(*(_from_schema({**schema, "type": t}, resolver) for t in kind))
    builders: dict[str, Callable[[], st.SearchStrategy[Any]]] = {
        "string": lambda: _string(schema),
        "integer": lambda: st.integers(schema.get("minimum", 0), schema.get("maximum", 400)),
        "number": lambda: _mm(schema.get("minimum", 0), schema.get("maximum", 400)),
        "boolean": st.booleans,
        "null": st.none,
        "array": lambda: _array(schema, resolver),
        "object": lambda: _object(schema, resolver),
    }
    return builders[kind]()


def _string(schema: dict[str, Any]) -> st.SearchStrategy[str]:
    if schema.get("format") == "date":
        return st.dates().map(lambda d: d.isoformat())
    if "pattern" in schema:
        limit = schema.get("maxLength", 40)
        return st.from_regex(schema["pattern"], fullmatch=True).filter(lambda s: len(s) <= limit)
    return _TEXT


def _array(schema: dict[str, Any], resolver: Any) -> st.SearchStrategy[list[Any]]:
    items = _from_schema(schema.get("items", True), resolver)
    high = min(schema.get("maxItems", _MAX_ITEMS), _MAX_ITEMS)
    low = schema.get("minItems", 0)
    if schema.get("uniqueItems"):
        return st.lists(items, min_size=low, max_size=high, unique_by=repr)
    return st.lists(items, min_size=low, max_size=high)


def _object(schema: dict[str, Any], resolver: Any) -> st.SearchStrategy[dict[str, Any]]:
    props = {key: _from_schema(sub, resolver) for key, sub in schema.get("properties", {}).items()}
    required = set(schema.get("required", []))
    extra = schema.get("additionalProperties", True)
    names = schema.get("propertyNames")

    @st.composite
    def build(draw: st.DrawFn) -> dict[str, Any]:
        out = draw(
            st.fixed_dictionaries(
                {k: v for k, v in props.items() if k in required},
                optional={k: v for k, v in props.items() if k not in required},
            )
        )
        for key, deps in schema.get("dependentRequired", {}).items():
            if key in out:
                out.update({dep: draw(props[dep]) for dep in deps if dep not in out})
        if isinstance(extra, dict):
            keys = _from_schema(names, resolver) if names else _TEXT
            more = draw(st.dictionaries(keys, _from_schema(extra, resolver), max_size=_MAX_ITEMS))
            out.update({k: v for k, v in more.items() if k not in out})
        return out

    return build()


def _strategy(name: str) -> st.SearchStrategy[Any]:
    schema = schemas()[name]
    return _from_schema(schema, registry().resolver(schema["$id"]))


def _valid(name: str, sample: Any) -> Any:
    errors = [error.message for error in validator(name).iter_errors(sample)]
    assert not errors, errors
    return sample


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _count(raw: Any) -> int:
    return len(raw) if isinstance(raw, list | dict) else 0


def _definition(name: str, definition: str) -> st.SearchStrategy[Any]:
    schema = schemas()[name]
    resolved = registry().resolver(schema["$id"]).lookup(f"#/$defs/{definition}")
    return _from_schema(resolved.contents, resolved.resolver)


def _load(manifest: dict[str, Any], data: st.DataObject) -> TemplateVersion:
    """Версия из манифеста (документы ростера получают свой `doc.yaml` по схеме) через лоадер Студии."""
    _valid("version", manifest)
    with tempfile.TemporaryDirectory() as tmp:
        version_dir = Path(tmp) / "v"
        (version_dir / "files").mkdir(parents=True)
        for entry in manifest.get("documents", []):
            if isinstance(entry, str):
                doc = _valid("doc", data.draw(_strategy("doc"), label=f"doc {entry}"))
                if "id" in doc:
                    doc["id"] = entry
                _write(version_dir / "files" / entry / "doc.yaml", doc)
        _write(version_dir / "version.yaml", manifest)
        version = _parse_version(version_dir, pack_id="p", template_id="t")
    assert version is not None, "лоадер не принял манифест, который проходит схему"
    return version


def _check_slots(version: TemplateVersion, signatures: dict[str, Any]) -> None:
    config = version.signatures_config
    assert len(config.route) == _count(signatures.get("route"))
    assert len(config.anchor_macros) == _count(signatures.get("anchor_macros"))
    raw_slots = signatures.get("slots", [])
    assert [s.id for s in config.slots] == [s["id"] for s in raw_slots]
    for slot, raw in zip(config.slots, raw_slots, strict=True):
        assert len(slot.placements) == _count(raw.get("placements"))
        assert all(isinstance(p, AnchorPlace) == ("anchor" in raw["placements"][d]) for d, p in slot.placements)
        raw_dates = raw.get("default_dates", {})
        assert [doc for doc, _ in slot.default_dates] == list(raw_dates)
        for doc, marks in slot.default_dates:
            assert [isinstance(m, AnchorDate) for m in marks] == ["anchor" in m for m in raw_dates[doc]]
        assert (slot.default_anchor is not None) == ("anchor" in raw.get("default_placement", {}))


def _check_profiles(version: TemplateVersion, raw_profiles: list[dict[str, Any]]) -> None:
    profiles = version.pack_submission.profiles
    assert [p.id for p in profiles] == [p["id"] for p in raw_profiles]
    for profile, raw in zip(profiles, raw_profiles, strict=True):
        assert len(profile.items) == _count(raw.get("items"))
        assert len(profile.extra_items) == _count(raw.get("extra_items"))
        assert len(profile.signing_route) == _count(raw.get("signing_route"))
        assert len(profile.signing_slots) == _count(raw.get("signing_slots"))
        hint = raw.get("deadline_hint")
        assert profile.deadline_hint == ({k: v.strip() for k, v in hint.items()} if hint else None)


@_SETTINGS
@given(data=st.data())
def test_every_schema_valid_version_loads_whole(data: st.DataObject) -> None:
    manifest = data.draw(_strategy("version"), label="version.yaml")
    version = _load(manifest, data)
    assert version.version == manifest["id"]
    assert len(version.documents) == _count(manifest.get("documents"))
    assert set(version.meta_fields) == set(manifest.get("meta_fields", {}))
    assert len(version.meta_groups) == _count(manifest.get("meta_groups"))
    assert version.langs == tuple(manifest.get("langs", []))
    raw_forms = manifest.get("forms", [])
    assert [len(f.sections) for f in version.forms] == [_count(f.get("sections")) for f in raw_forms]
    assert [len(s.fields) for f in version.forms for s in f.sections] == [
        _count(s.get("fields")) for f in raw_forms for s in f.get("sections", [])
    ]
    _check_slots(version, manifest.get("signatures", {}))
    _check_profiles(version, manifest.get("pack_submission", {}).get("profiles", []))


# Подписи и профили сдачи вложены глубоко: в целой версии они редки, поэтому у них своя выборка, где они есть всегда.
@_SETTINGS
@given(data=st.data(), slots=st.lists(_definition("version", "slot"), min_size=1, max_size=3))
def test_every_schema_valid_slot_loads_whole(data: st.DataObject, slots: list[Any]) -> None:
    signatures = {"slots": slots, "anchor_macros": ["hseSignField"], "route": [[s["id"]] for s in slots]}
    version = _load({"id": "2026.1", "signatures": signatures}, data)
    _check_slots(version, signatures)


@_SETTINGS
@given(data=st.data(), profiles=st.lists(_definition("version", "profile"), min_size=1, max_size=3))
def test_every_schema_valid_profile_loads_whole(data: st.DataObject, profiles: list[Any]) -> None:
    version = _load({"id": "2026.1", "pack_submission": {"profiles": profiles}}, data)
    _check_profiles(version, profiles)


@_SETTINGS
@given(template=_strategy("template"), releases=_strategy("releases"), pack=_strategy("pack"))
def test_every_schema_valid_template_releases_and_pack_load(template: Any, releases: Any, pack: Any) -> None:
    _valid("template", template)
    _valid("releases", releases)
    _valid("pack", pack)
    with tempfile.TemporaryDirectory() as tmp:
        pack_dir = Path(tmp) / "pack"
        template_dir = pack_dir / "templates" / "t"
        _write(pack_dir / "pack.yaml", pack)
        _write(template_dir / "template.yaml", template)
        _write(template_dir / "releases.yaml", releases)
        info = _parse_template_info(template_dir, pack_id="p")
        loaded = load_releases(template_dir)
        parsed_pack = _parse_pack(pack_dir)

    assert info is not None
    assert info.id == template["id"]
    assert info.default_version == template.get("default_version", "")
    assert set(loaded) == set(releases["releases"])
    assert {v: e.kind and e.kind.value for v, e in loaded.items()} == {
        v: r.get("kind") for v, r in releases["releases"].items()
    }
    assert parsed_pack is not None
    assert parsed_pack.id == pack["id"]
    assert [t.id for t in parsed_pack.templates] == [template["id"]]
