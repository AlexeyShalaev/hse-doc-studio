"""Правила слияния файлов состояния Студии и стратегия, которой пользуется планировщик.

Правила написаны по тому, что пишут репозитории (`infra/persistence`): какие поля машинные, какие
списки ключевые, что нельзя смешивать. Любое изменение формата `.hse-studio/*.json` обязано
отразиться здесь; тесты строят документы настоящими сериализаторами.

    project.json     схема — максимум, `lock` — старшая версия шаблона, авторы по slug, документы по id,
                     `updated_at` — максимум, `created_at` — минимум; `pinned`, `archived`, `meta.vcs` и
                     `documents[].last_compile_id` остаются моими
    signatures.json  слоты и размещения по ключам, `signing_identity_id` и `sign_mode` мои, картинка
                     слота следует за новейшей, подписанный PDF с подписями — неделимая группа документа
    forms/*.json     `completed` — «и» обеих сторон и сбрасывается, если ответы изменились после отметки
    template.json    история обновлений — объединение по id, `ignored` — множество
    остальные        словари по ключам, списки и скаляры целиком

Итог проверяется: он должен разбираться как документ того же вида (проверку для `project.json`
подключает слой выше, где живут сериализаторы). Непроверяемый итог становится принудительным
конфликтом `invalid_result`: слияние на плохих данных не падает.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Hashable, Mapping
from datetime import UTC, datetime
from typing import Any

from hse_doc_studio.core.git_sync.entities import SyncWarning, SyncWarningCode
from hse_doc_studio.core.git_sync.merge.binary import newest_side
from hse_doc_studio.core.git_sync.merge.choices import FieldChoice
from hse_doc_studio.core.git_sync.merge.entities import ConflictType, MergeSide
from hse_doc_studio.core.git_sync.merge.jsonmerge import (
    ABSENT,
    UNRESOLVED,
    Atomic,
    ConflictKind,
    Custom,
    DocGroups,
    Extremum,
    FieldGroup,
    InvalidFieldChoiceError,
    JsonMerge,
    JsonRules,
    Keyed,
    LocalOnly,
    MustEqual,
    PostResult,
    SetOf,
    canonical_dumps,
    merge_json,
    same,
)
from hse_doc_studio.core.git_sync.protocols import MergeDecision, MergeMeta
from hse_doc_studio.core.git_sync.untrusted_json import loads_untrusted
from hse_doc_studio.core.template_versions import parse_app_version, parse_version_key

_STUDIO = ".hse-studio/"
_PROJECT = ".hse-studio/project.json"
_SIGNATURES = ".hse-studio/signatures.json"
_TEMPLATE = ".hse-studio/template.json"
_FORMS = re.compile(r"^\.hse-studio/forms/[^/]+\.json$")

# Проверка итога: бросает исключение, если документ не разбирается.
Validator = Callable[[Any], object]


# --- ключи и сравнения -------------------------------------------------------------------------


def _author_key(author: Any) -> Hashable | None:
    return author.get("slug") or author.get("name") or None


def _id_key(item: Any) -> Hashable | None:
    return item.get("id")


def _number(value: Any) -> float | None:
    return None if isinstance(value, bool) or not isinstance(value, int | float) else value


def _studio_version(value: Any) -> tuple[int, int, int] | None:
    """Версия Студии; непонятная строка не спорит, а проигрывает любой понятной."""
    if not isinstance(value, str):
        return None
    return parse_app_version(value) or (-1, -1, -1)


def _moment(value: Any) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)).timestamp()


def _history_order(record: Any) -> tuple[str, str]:
    """`TemplateTrackingState.last_applied` читает историю с конца, поэтому она идёт по времени."""
    return str(record.get("at", "")), str(record.get("id", ""))


# --- правила отдельных полей -------------------------------------------------------------------


def _lock(_base: Any, ours: Any, theirs: Any) -> Any:
    """Обе стороны меняли шаблон: берётся запись со старшей версией; другой шаблон или движок — конфликт."""
    if not (isinstance(ours, dict) and isinstance(theirs, dict)):
        return UNRESOLVED
    if any(ours.get(name) != theirs.get(name) for name in ("pack_id", "template_id", "engine")):
        return UNRESOLVED
    mine, other = parse_version_key(ours.get("version", "")), parse_version_key(theirs.get("version", ""))
    if mine is None or other is None or mine == other:
        return UNRESOLVED
    return ours if mine > other else theirs


def _both(_base: Any, ours: Any, theirs: Any) -> Any:
    return ours and theirs if isinstance(ours, bool) and isinstance(theirs, bool) else UNRESOLVED


def _either(_base: Any, ours: Any, theirs: Any) -> Any:
    return ours or theirs if isinstance(ours, bool) and isinstance(theirs, bool) else UNRESOLVED


def _non_null(_base: Any, ours: Any, theirs: Any) -> Any:
    if ours is None and theirs is not None:
        return theirs
    return ours if theirs is None and ours is not None else UNRESOLVED


# --- проверки итога ----------------------------------------------------------------------------


def _stale_signatures(merged: Any, ours: Any, theirs: Any) -> PostResult:  # noqa: ARG001
    """Подпись, снятая с другого PDF, чем замороженный: предупреждение, данные не трогаем."""
    if not isinstance(merged, dict):
        return PostResult(merged)
    frozen, detached = merged.get("frozen"), merged.get("detached")
    if not (isinstance(frozen, dict) and isinstance(detached, dict)):
        return PostResult(merged)
    stale = sorted(doc for doc, signatures in detached.items() if _is_stale(frozen.get(doc), signatures))
    if not stale:
        return PostResult(merged)
    paths = tuple(str(frozen[doc].get("path") or doc) for doc in stale)
    return PostResult(merged, (SyncWarning(SyncWarningCode.signatures_stale, paths),))


def _is_stale(frozen: Any, signatures: Any) -> bool:
    if not (isinstance(frozen, dict) and isinstance(signatures, dict)):
        return False
    return any(
        isinstance(item, dict) and item.get("pdf_sha256") != frozen.get("sha256") for item in signatures.values()
    )


def _completed_invariant(merged: Any, ours: Any, theirs: Any) -> PostResult:
    """Форма отмечена готовой только вместе с теми ответами, с которыми её отметили.

    Если после слияния ответы не совпали ни с одной из сторон, отметивших готовность, отметка снимается:
    человек должен просмотреть форму ещё раз.
    """
    if not isinstance(merged, dict) or merged.get("completed") is not True:
        return PostResult(merged)
    signed_off = [side for side in (ours, theirs) if isinstance(side, dict) and side.get("completed") is True]
    if any(same(side.get("answers"), merged.get("answers")) for side in signed_off):
        return PostResult(merged)
    return PostResult({**merged, "completed": False})


# --- правила файлов ----------------------------------------------------------------------------

PROJECT_RULES = JsonRules(
    name="project",
    rules=(
        MustEqual(("id",)),
        Extremum(("schema", "version"), "max", _number),
        Extremum(("schema", "read_compat"), "max", _number),
        Extremum(("schema", "write_compat"), "max", _number),
        Extremum(("schema", "written_by"), "max", _studio_version),
        Custom(("lock",), _lock),
        Keyed(("authors",), _author_key),
        Keyed(("documents",), _id_key),
        MustEqual(("documents", "*", "def_id")),
        SetOf(("documents", "*", "checks_override", "disabled_categories")),
        SetOf(("documents", "*", "checks_override", "disabled")),
        SetOf(("documents", "*", "checks_override", "enabled")),
        SetOf(("checks_override", "disabled_categories")),
        SetOf(("checks_override", "disabled")),
        SetOf(("checks_override", "enabled")),
        Extremum(("updated_at",), "max", _moment),
        Extremum(("created_at",), "min", _moment),
        # Машинные поля, которые лежат в общем файле: чужие значения на этой машине ничего не значат.
        LocalOnly(("pinned",), False),
        LocalOnly(("archived",), False),
        LocalOnly(("meta", "vcs")),
        LocalOnly(("documents", "*", "last_compile_id"), None),
    ),
)

SIGNATURES_RULES = JsonRules(
    name="signatures",
    rules=(
        LocalOnly(("slots", "*", "signing_identity_id"), None),
        LocalOnly(("slots", "*", "sign_mode"), "image"),
        Atomic(("placements", "*", "*")),
    ),
    field_groups=(FieldGroup(("slots", "*"), ("png_path", "natural_width_px", "natural_height_px")),),
    doc_groups=(DocGroups((), ("frozen", "detached"), "signature_groups"),),
    post=(_stale_signatures,),
)

FORM_RULES = JsonRules(
    name="form",
    rules=(
        Extremum(("schema_version",), "max", _number),
        Custom(("completed",), _both),
    ),
    post=(_completed_invariant,),
)

TEMPLATE_RULES = JsonRules(
    name="template",
    rules=(
        SetOf(("ignored",), sort=True),
        Keyed(("history",), _id_key, order=_history_order),
        Custom(("history", "*", "reverted"), _either),
        Custom(("history", "*", "commit"), _non_null),
    ),
)

# Файлы состояния, которых эта Студия не знает (их пишет более новая): словари по ключам, остальное целиком.
GENERIC_RULES = JsonRules(name="state")


def rules_for(path: str) -> JsonRules | None:
    """Правила файла состояния по пути; None — это не файл состояния."""
    if not (path.startswith(_STUDIO) and path.endswith(".json")):
        return None
    if path == _PROJECT:
        return PROJECT_RULES
    if path == _SIGNATURES:
        return SIGNATURES_RULES
    if path == _TEMPLATE:
        return TEMPLATE_RULES
    return FORM_RULES if _FORMS.match(path) else GENERIC_RULES


# --- стратегия ---------------------------------------------------------------------------------


class _UnparsableError(Exception):
    """Сторона не разобралась как JSON: файл сливается как текст."""


def _parse(raw: bytes | None) -> Any:
    if raw is None:
        return ABSENT
    try:
        return loads_untrusted(raw)
    except ValueError as exc:
        raise _UnparsableError from exc


def _conflict_type(merge: JsonMerge) -> ConflictType:
    if all(conflict.kind is ConflictKind.signature_group for conflict in merge.conflicts):
        return ConflictType.signature_group
    return ConflictType.fields


class StateFileMerge:
    """Слияние `.hse-studio/*.json` по полям; подключается к планировщику как `IFileMergeStrategy`.

    `validators` — проверки итога по виду файла (`project`, `signatures`, `form`, `template`): функция
    бросает исключение, если документ не разбирается. Сериализаторы живут в infra, поэтому их подаёт
    слой, который собирает стратегию.
    """

    def __init__(self, validators: Mapping[str, Validator] | None = None) -> None:
        self._validators = dict(validators or {})

    def merge(
        self, path: str, base: bytes | None, ours: bytes | None, theirs: bytes | None, meta: MergeMeta
    ) -> MergeDecision:
        return self._run(path, base, ours, theirs, meta, {})

    def resolve(
        self,
        path: str,
        base: bytes | None,
        ours: bytes | None,
        theirs: bytes | None,
        meta: MergeMeta,
        choices: Mapping[str, FieldChoice],
    ) -> MergeDecision:
        """Слияние заново с решениями человека. Неподходящее решение — InvalidFieldChoiceError."""
        decision = self._run(path, base, ours, theirs, meta, choices)
        if decision.conflict_type == ConflictType.invalid_result.value:
            raise InvalidFieldChoiceError(sorted(choices))
        return decision

    def _run(
        self,
        path: str,
        base: bytes | None,
        ours: bytes | None,
        theirs: bytes | None,
        meta: MergeMeta,
        choices: Mapping[str, FieldChoice],
    ) -> MergeDecision:
        rules = rules_for(path)
        try:
            documents = [_parse(raw) for raw in (base, ours, theirs)]
        except _UnparsableError:
            return MergeDecision(None, as_text=True)
        if rules is None or ours is None or theirs is None:
            return MergeDecision(None, as_text=True)

        def theirs_newer(mine: Any, other: Any) -> bool:
            return newest_side(mine, other, meta) is MergeSide.theirs

        before, mine, other = documents
        merge = merge_json(before, mine, other, rules, choices=choices, newest_theirs=theirs_newer)
        return self._decision(rules, merge, (ours, theirs), (documents[1], documents[2]))

    def _decision(
        self, rules: JsonRules, merge: JsonMerge, raw: tuple[bytes, bytes], parsed: tuple[Any, Any]
    ) -> MergeDecision:
        if merge.conflicts:
            return MergeDecision(
                _dump(merge.value),
                conflict=True,
                conflict_type=_conflict_type(merge).value,
                fields=merge.conflicts,
                auto=merge.auto,
            )
        if not self._valid(rules, merge.value):
            return MergeDecision(raw[0], conflict=True, conflict_type=ConflictType.invalid_result.value)
        # Итог, совпавший с одной из сторон, отдаётся её же байтами: форматирование не меняется зря.
        content = next((side for side, value in zip(raw, parsed, strict=True) if same(merge.value, value)), None)
        return MergeDecision(
            content if content is not None else _dump(merge.value), auto=merge.auto, warnings=merge.warnings
        )

    def _valid(self, rules: JsonRules, value: Any) -> bool:
        validate = self._validators.get(rules.name)
        if validate is None:
            return True
        if not isinstance(value, dict):
            return False
        try:
            validate(value)
        except Exception:  # noqa: BLE001 — проверка чужих данных: любая ошибка значит «итог плохой»
            return False
        return True


def _dump(value: Any) -> bytes:
    return canonical_dumps(value).encode()
