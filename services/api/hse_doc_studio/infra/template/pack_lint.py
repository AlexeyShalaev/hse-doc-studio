r"""Линтер пака (bundle-раскладка v2): превращает конвенции раскладки в
проверяемые ошибки ДО того, как пользователь увидит их в созданном проекте.

Проверки:
  * Jinja-parse каждого текстового файла с маркерами шаблонизатора —
    TemplateSyntaxError становится ошибкой авторинга, а не молчаливым
    verbatim-копированием с выпадением веток (главная тихая гоча рендера);
  * грамматика языковых суффиксов: смешение bare + суффиксных файлов в одной
    группе (ошибка), суффиксная группа без редакции дефолтного языка
    («сиротский перевод», предупреждение), похожий на код 2-буквенный сегмент
    вне объявленных `langs:` (предупреждение об опечатке);
  * резолв всех \input/\include по РАЗРЕШЁННОМУ дереву каждого языка (ловит
    протухшие кросс-документные пути — класс бага `../tz_shared/…`);
  * существование source_file каждого документа/варианта в разрешённом дереве;
  * согласованность состава пакета: анкета, которую профиль сдачи кладёт в
    архив через `extra_items`, обязана быть объявлена `required_for_pack`, иначе
    приложение промолчит о незаполненной (класс бага «Ссылка на код»);
  * шапка каждого checks/*.yaml: `label` и `ref` на ru+en — подпись группы правил
    в UI берётся из пака, приложение названий стандартов и ОП не знает;
  * порядок маршрута подписания (`signatures.route`, `signing_route` профиля):
    разбирается и называет только объявленные слоты, каждый один раз;
  * метки даты по умолчанию слота (`default_dates`): разбираются, рамка внутри
    листа A4, документ из `applies_to` слота;
  * подсказка срока точки (`deadline_hint` профиля): обе локали, не длиннее 200
    знаков и без конкретных дат (сроки меняются каждый год);
  * пресет маршрута (signing-route.md, 15.8): места слота по документам
    (`placements`) внутри листа и только на документах слота и версии;
    `signing_slots` профиля называют документ точки и применимый к нему слот
    каталога, без повторов, `when` только у слота сверх точки, `optional: true`
    не у слота с `required: true`; предупреждения: слот сверх точки не стоит в
    порядке маршрута, место `per_author` слота на общем документе командного
    шаблона, узкое место под плашку открепленной ЭП;
  * места и метки даты на якорях шаблона (signing-route.md, 15.17.13, модуль
    `anchor_lint`): вызов якоря или обёртки из `anchor_macros` в исходнике
    документа или в `common/`, файл макросов `common/anchors.tex` подключён,
    `default_placement` на якоре с запасным местом в мм; предупреждения: имя
    якоря в исходнике не id слота каталога, одно имя дважды в файле.

Запуск: `python -m hse_doc_studio.infra.template.pack_lint <version_dir>…`
(exit code 1 при ошибках). Roster ↔ doc.yaml проверяется fail-fast самим
лоадером (`_parse_documents`) — здесь не дублируется.
"""

from __future__ import annotations

import posixpath
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, TemplateSyntaxError

from hse_doc_studio.core.catalog import AnchorPlace
from hse_doc_studio.core.checkpoint_deadlines import parse_deadline_hint
from hse_doc_studio.core.signatures.route_order import BUILTIN_ROUTE
from hse_doc_studio.core.signatures.stamps import PLATE_MIN_WIDTH_MM
from hse_doc_studio.infra.project_init.template_renderer import (
    PACK_DOC_MANIFEST,
    _split_lang_qualifier,
    collect_sources_suffixed,
)
from hse_doc_studio.infra.template.anchor_lint import lint_anchors
from hse_doc_studio.infra.template.yaml_template_repository import (
    parse_default_dates,
    parse_signing_route,
    parse_signing_slot,
    parse_slot_placement,
    signing_slot_entries,
    slot_placement_entries,
)

_TEXT_SUFFIXES = {".tex", ".md", ".html", ".txt", ".cls", ".sty", ".bib", ".j2"}
_INPUT_RE = re.compile(r"\\(?:input|include)\{([^}]+)\}")
# Контекстные корни рендера: незарендеренный `{{ project.… }}` в PDF — ошибка.
_PLACEHOLDER_RE = re.compile(r"\{\{\s*(?:project|author|team|pack|template)\.")
_QUALIFIER_LIKE_RE = re.compile(r"^[a-z]{2}(?:-[a-z]{2})?$")
# LaTeX-комментарий: `%` до конца строки (кроме экранированного `\%`).
_TEX_COMMENT_RE = re.compile(r"(?<!\\)%.*")
# Языки, на которых обязаны быть заметки версии (`changes:`). Не `langs:` пака —
# то языки ДОКУМЕНТОВ, а это язык интерфейса, на котором заметки читает человек.
_CHANGES_LANGS = ("ru", "en")


@dataclass
class LintReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _jinja_env() -> Environment:
    # Те же LaTeX-safe делимитеры, что у рендера (см. template_renderer).
    return Environment(  # noqa: S701
        block_start_string="((*",
        block_end_string="*))",
        comment_start_string="((#",
        comment_end_string="#))",
    )


def _load_manifest(version_dir: Path) -> dict[str, Any]:
    return yaml.safe_load((version_dir / "version.yaml").read_text(encoding="utf-8")) or {}


def _doc_sources(version_dir: Path, manifest: dict[str, Any]) -> list[tuple[str, str]]:
    """(doc_id, source_file) всех документов и вариантов (v2: roster+doc.yaml)."""
    out: list[tuple[str, str]] = []
    for entry in manifest.get("documents", []):
        if isinstance(entry, str):
            doc_path = version_dir / "files" / entry / "doc.yaml"
            data = yaml.safe_load(doc_path.read_text(encoding="utf-8")) if doc_path.exists() else {}
            doc_id = entry
        else:
            data, doc_id = entry, str(entry.get("id", "?"))
        if data.get("source_file"):
            out.append((doc_id, str(data["source_file"])))
        out.extend((doc_id, str(v["source_file"])) for v in data.get("variants", []) or [] if v.get("source_file"))
    return out


def _extra_form_id(extra: object) -> str | None:
    """id анкеты, на которую ссылается extra-пункт; None — пункт не про форму."""
    if not isinstance(extra, dict):
        return None
    source = str(extra.get("source", ""))
    # Скан NDA и прочие файлы приезжают тем же механизмом, но формами не являются.
    if "/forms/" not in source or not source.endswith(".json"):
        return None
    return source.rsplit("/", 1)[-1].removesuffix(".json")


def _lint_form_extras(manifest: dict[str, Any]) -> list[str]:
    """
    Анкета, которую профиль сдачи кладёт в архив, обязана быть required_for_pack.

    Про состав пакета в паке говорят два независимых места: `extra_items` профиля
    (что реально уедет — по нему собирает create_submission) и флаг
    `required_for_pack` самой формы (по нему приложение решает, предупреждать ли
    о незаполненной). Разъехались — студент отправляет незаполненную анкету, и
    ни кольцо готовности, ни один экран об этом не скажут: расчёт засчитывает
    только пересечение. Ровно так и случилось со «Ссылкой на код».
    """
    errors: list[str] = []
    flag_by_form = {
        str(f["id"]): bool(f.get("required_for_pack", False))
        for f in manifest.get("forms", []) or []
        if isinstance(f, dict) and f.get("id")
    }
    profiles = (manifest.get("pack_submission", {}) or {}).get("profiles", []) or []
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        for extra in profile.get("extra_items", []) or []:
            form_id = _extra_form_id(extra)
            if form_id is None:
                continue
            if form_id not in flag_by_form:
                errors.append(
                    f"профиль {profile.get('id', '?')}: extra_items ссылается на {form_id!r}, "
                    f"но такой формы нет в forms:"
                )
            elif not flag_by_form[form_id]:
                errors.append(
                    f"профиль {profile.get('id', '?')}: анкета {form_id!r} уходит в пакет, "
                    f"но объявлена required_for_pack: false — приложение не предупредит, "
                    f"что она не заполнена"
                )
    return errors


def _lint_check_sources(version_dir: Path) -> list[str]:
    """Каждый checks/*.yaml обязан сам назвать документ, чьи требования кодирует.

    Приложение не знает названий стандартов и образовательных программ — и не должно:
    другой пак может описывать другую ОП или другой вуз. Поэтому подпись группы правил
    в UI берётся из `label` файла (с откатом на `ref`). Без них в интерфейсе появится
    сырой id вида `hse-pi-lang`, и никто, кроме автора пака, не поймёт, что это.
    """
    errors: list[str] = []
    checks_dir = version_dir / "checks"
    if not checks_dir.is_dir():
        return errors
    for yaml_file in sorted(checks_dir.glob("*.yaml")):
        try:
            data = yaml.safe_load(yaml_file.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            errors.append(f"checks/{yaml_file.name}: не парсится ({exc})")
            continue
        if not data.get("rules"):
            continue
        for key in ("label", "ref"):
            block = data.get(key)
            if not isinstance(block, dict) or not block.get("ru") or not block.get("en"):
                errors.append(
                    f"checks/{yaml_file.name}: нет {key}.ru/{key}.en — "
                    f"UI покажет сырой id группы вместо названия документа"
                )
    return errors


def _lint_signing_routes(manifest: dict[str, Any]) -> list[str]:
    """Порядок маршрута подписания (`signatures.route`, `signing_route` профиля) называет слоты каталога.

    Лоадер терпим: битый ключ отбрасывается, неизвестный или повторный слот пропускается, и маршрут молча
    пойдёт встроенным порядком или без шага, который автор пака имел в виду. Линтер делает это ошибкой.
    """
    signatures = manifest.get("signatures")
    signatures = signatures if isinstance(signatures, dict) else {}
    slots = {str(s["id"]) for s in signatures.get("slots", []) or [] if isinstance(s, dict) and s.get("id")}
    routes: list[tuple[str, Any]] = [("signatures.route", signatures.get("route"))]
    submission = manifest.get("pack_submission")
    profiles = (submission.get("profiles", []) or []) if isinstance(submission, dict) else []
    routes.extend(
        (f"профиль {profile.get('id', '?')}: signing_route", profile.get("signing_route"))
        for profile in profiles
        if isinstance(profile, dict)
    )
    return [error for where, raw in routes if raw is not None for error in _route_errors(where, raw, slots)]


def _lint_default_dates(manifest: dict[str, Any]) -> list[str]:
    """Метки даты по умолчанию слотов (`default_dates`, signing-route.md, 14.10): разбор, рамка в листе A4, документ
    из `applies_to` слота. Лоадер битый ключ отбрасывает молча (с записью в журнал), линтер делает это ошибкой."""
    signatures = manifest.get("signatures")
    signatures = signatures if isinstance(signatures, dict) else {}
    errors: list[str] = []
    for slot in signatures.get("slots", []) or []:
        if not isinstance(slot, dict) or slot.get("default_dates") is None:
            continue
        where = f"signatures.slots[{slot.get('id', '?')}]"
        try:
            by_doc = parse_default_dates(slot["default_dates"])
        except (TypeError, ValueError, KeyError) as exc:
            errors.append(f"{where}: {exc}")
            continue
        applies = slot.get("applies_to", [])
        applies = set(applies) if isinstance(applies, list) else {applies}
        errors.extend(
            f"{where}: default_dates.{doc_id}: документ не входит в applies_to слота"
            for doc_id, _ in by_doc
            if doc_id not in applies
        )
    return errors


def _lint_deadline_hints(manifest: dict[str, Any]) -> list[str]:
    """Подсказка срока точки (`deadline_hint`, signing-route.md, 16.4): обе локали, не длиннее 200 знаков, без дат.

    Лоадер битую подсказку отбрасывает молча (с записью в журнал), и точка останется без серого текста; дата в
    подсказке устареет к следующему году, а выпущенную версию пака уже не поправить. Линтер делает это ошибкой.
    """
    submission = manifest.get("pack_submission")
    profiles = (submission.get("profiles", []) or []) if isinstance(submission, dict) else []
    errors: list[str] = []
    for profile in profiles:
        if not isinstance(profile, dict) or profile.get("deadline_hint") is None:
            continue
        try:
            parse_deadline_hint(profile["deadline_hint"])
        except (TypeError, ValueError) as exc:
            errors.append(f"профиль {profile.get('id', '?')}: {exc}")
    return errors


def _doc_scopes(version_dir: Path, manifest: dict[str, Any]) -> dict[str, str]:
    """id документа версии → `scope` (`shared` по умолчанию), v2: roster + doc.yaml, v1: записи в манифесте."""
    scopes: dict[str, str] = {}
    for entry in manifest.get("documents", []) or []:
        if isinstance(entry, str):
            doc_path = version_dir / "files" / entry / "doc.yaml"
            data = yaml.safe_load(doc_path.read_text(encoding="utf-8")) if doc_path.exists() else {}
            scopes[entry] = str((data or {}).get("scope", "shared"))
        elif isinstance(entry, dict) and entry.get("id"):
            scopes[str(entry["id"])] = str(entry.get("scope", "shared"))
    return scopes


def _catalog(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Слоты каталога подписей по id (сырые записи манифеста)."""
    signatures = manifest.get("signatures")
    slots = signatures.get("slots", []) if isinstance(signatures, dict) else []
    return {str(s["id"]): s for s in slots or [] if isinstance(s, dict) and s.get("id")}


def _applies(slot: dict[str, Any]) -> set[str]:
    applies = slot.get("applies_to", [])
    return {str(a) for a in applies} if isinstance(applies, list) else {str(applies)}


def _profiles(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    submission = manifest.get("pack_submission")
    profiles = (submission.get("profiles", []) or []) if isinstance(submission, dict) else []
    return [p for p in profiles if isinstance(p, dict)]


def _lint_slot_placements(version_dir: Path, manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Места слотов по документам (`placements`, signing-route.md, 15.8): рамка в листе, документ слота и версии.

    Лоадер битую запись документа отбрасывает молча (с записью в журнал), линтер делает это ошибкой. Место
    `per_author` слота на общем документе командного шаблона это предупреждение: в команде пресет такие места не
    ставит, все авторы встали бы в одну рамку (15.5).
    """
    errors: list[str] = []
    warnings: list[str] = []
    scopes = _doc_scopes(version_dir, manifest)
    team = "team" in (manifest.get("supported_staffing") or ())
    for slot_id, slot in _catalog(manifest).items():
        where = f"signatures.slots[{slot_id}]"
        try:
            entries = slot_placement_entries(slot.get("placements"))
        except TypeError as exc:
            errors.append(f"{where}: {exc}")
            continue
        shared_warning = team and bool(slot.get("per_author"))
        for doc_id, item in entries:
            problem = _placement_problem(doc_id, item, _applies(slot), scopes)
            if problem is not None:
                errors.append(f"{where}: {problem}")
            elif shared_warning and scopes.get(doc_id) == "shared":
                warnings.append(
                    f"{where}: placements.{doc_id}: слот per_author на общем документе, в команде место из пака "
                    f"не ставится (все авторы встали бы в одну рамку)"
                )
    return errors, warnings


def _placement_problem(doc_id: str, item: Any, applies: set[str], scopes: dict[str, str]) -> str | None:
    """Что не так с записью `placements` документа; None, если запись годится."""
    try:
        parse_slot_placement(item, f"placements.{doc_id}")
    except (TypeError, ValueError, KeyError) as exc:
        return str(exc)
    if doc_id not in applies:
        return f"placements.{doc_id}: документ не входит в applies_to слота"
    if scopes and doc_id not in scopes:
        return f"placements.{doc_id}: такого документа нет в documents версии"
    return None


def _lint_signing_slots(manifest: dict[str, Any]) -> tuple[list[str], list[str]]:  # noqa: C901, PLR0912
    """Пресеты точек (`signing_slots`, signing-route.md, 15.8): ошибки формы и связей, предупреждение о порядке.

    Лоадер терпим: битая запись или запись с незнакомым условием отбрасывается, а запись с неизвестным документом
    или слотом просто ничего не включит. Линтер делает это ошибкой. Слот сверх точки, которого нет в порядке
    маршрута, встал бы молча последним шагом: это предупреждение.
    """
    errors: list[str] = []
    warnings: list[str] = []
    catalog = _catalog(manifest)
    signatures = manifest.get("signatures")
    version_route = signatures.get("route") if isinstance(signatures, dict) else None
    for profile in _profiles(manifest):
        owner = f"профиль {profile.get('id', '?')}"
        where = f"{owner}: signing_slots"
        try:
            entries = signing_slot_entries(profile.get("signing_slots"))
        except TypeError as exc:
            errors.append(f"{owner}: {exc}")
            continue
        point: dict[str, set[str]] = {}
        for item in profile.get("items", []) or []:
            if isinstance(item, dict) and item.get("doc_id"):
                point.setdefault(str(item["doc_id"]), set()).update(str(s) for s in item.get("signatures", []) or [])
        seen: set[tuple[str, str]] = set()
        extra: list[str] = []
        for i, raw in enumerate(entries):
            try:
                entry = parse_signing_slot(raw, f"signing_slots[{i}]")
            except (TypeError, ValueError) as exc:
                errors.append(f"{owner}: {exc}")
                continue
            pair = f"{entry.doc_id}/{entry.slot_id}"
            slot = catalog.get(entry.slot_id)
            if entry.doc_id not in point:
                errors.append(f"{where}: {pair}: документа нет в items профиля")
            elif slot is None:
                errors.append(f"{where}: {pair}: слот не объявлен в signatures.slots")
            elif entry.doc_id not in _applies(slot):
                errors.append(f"{where}: {pair}: слот не применим к документу (applies_to)")
            if (entry.doc_id, entry.slot_id) in seen:
                errors.append(f"{where}: {pair}: пара указана дважды")
            seen.add((entry.doc_id, entry.slot_id))
            of_point = entry.slot_id in point.get(entry.doc_id, set())
            if entry.when is not None and of_point:
                errors.append(f"{where}: {pair}: when только у слота сверх точки, а эту подпись точка требует")
            if entry.optional and slot is not None and bool(slot.get("required")):
                errors.append(f"{where}: {pair}: optional: true у слота с required: true")
            if not of_point:
                extra.append(entry.slot_id)
        declared_raw = profile.get("signing_route") or version_route
        try:
            declared = parse_signing_route(declared_raw) if declared_raw else BUILTIN_ROUTE
        except (TypeError, ValueError):
            continue  # битый порядок уже назвал `_lint_signing_routes`
        ordered = {slot_id for step in declared for slot_id in step}
        warnings.extend(
            f"{where}: слот сверх точки {slot_id!r} не стоит в порядке маршрута, он пойдёт последним шагом"
            for slot_id in dict.fromkeys(extra)
            if slot_id not in ordered
        )
    return errors, warnings


def _detached_pairs(manifest: dict[str, Any]) -> list[tuple[str, str]]:
    """Пары «документ, слот» пунктов точек, где открепленная ЭП разрешена (`methods` слота без записи: любой способ)."""
    pairs: list[tuple[str, str]] = []
    for profile in _profiles(manifest):
        for item in profile.get("items", []) or []:
            if not isinstance(item, dict):
                continue
            raw_methods = item.get("methods")
            methods: dict[str, Any] = raw_methods if isinstance(raw_methods, dict) else {}
            for slot_id in (str(s) for s in item.get("signatures", []) or []):
                allowed = methods.get(slot_id)
                listed = allowed if isinstance(allowed, list) else [allowed] if allowed else []
                pair = (str(item.get("doc_id", "")), slot_id)
                if (not listed or "detached" in listed) and pair not in pairs:
                    pairs.append(pair)
    return pairs


def _lint_plate_room(manifest: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Место из `placements` у пары точки, где разрешена открепленная ЭП, и плашка (signing-route.md, 6.3, 15.8).

    `widen_for_plate` расширяет узкое место до ширины плашки влево, сохраняя правый край: предупреждение, что рамка
    станет шире, и ошибка, если слева не хватит листа.
    """
    errors: list[str] = []
    warnings: list[str] = []
    catalog = _catalog(manifest)
    for doc_id, slot_id in _detached_pairs(manifest):
        raw = catalog.get(slot_id, {}).get("placements")
        place = raw.get(doc_id) if isinstance(raw, dict) else None
        try:
            parsed = parse_slot_placement(place, f"placements.{doc_id}") if isinstance(place, dict) else None
        except (TypeError, ValueError, KeyError):
            parsed = None  # битое место уже назвал `_lint_slot_placements`
        if isinstance(parsed, AnchorPlace):
            parsed = parsed.fallback  # место на якоре по сборке линтер не считает; запасное место в мм проверяет
        if parsed is None or parsed.width_mm >= PLATE_MIN_WIDTH_MM:
            continue
        where = f"signatures.slots[{slot_id}]: placements.{doc_id}"
        if parsed.x_mm + parsed.width_mm - PLATE_MIN_WIDTH_MM < 0:
            errors.append(
                f"{where}: под плашку открепленной ЭП рамка расширится до {PLATE_MIN_WIDTH_MM:g} мм влево "
                f"и выйдет за левый край листа"
            )
        else:
            warnings.append(
                f"{where}: место уже плашки открепленной ЭП, при подписи ЭП рамка расширится до "
                f"{PLATE_MIN_WIDTH_MM:g} мм влево"
            )
    return errors, warnings


def _route_errors(where: str, raw: Any, slots: set[str]) -> list[str]:
    try:
        steps = parse_signing_route(raw)
    except (TypeError, ValueError) as exc:
        return [f"{where}: {exc}"]
    errors: list[str] = []
    seen: set[str] = set()
    for slot_id in (slot_id for step in steps for slot_id in step):
        if slot_id not in slots:
            errors.append(f"{where}: слот {slot_id!r} не объявлен в signatures.slots")
        elif slot_id in seen:
            errors.append(f"{where}: слот {slot_id!r} указан дважды, действует первый шаг")
        seen.add(slot_id)
    return errors


def _lint_changes(manifest: dict[str, Any]) -> list[str]:
    """`changes:` — двуязычные заметки версии; списки ru и en обязаны быть параллельны.

    Заменяют прежний CHANGELOG.md шаблона. Пропущенный перевод виден только в другой
    локали интерфейса, где его уже некому заметить, а разъехавшиеся по длине списки
    означают, что языки описывают РАЗНЫЕ наборы фактов — поэтому сверяем длины, а не
    только наличие.
    """
    errors: list[str] = []
    changes = manifest.get("changes")
    if changes is None:
        return errors  # блок необязателен; проверяем только заполненный
    if not isinstance(changes, dict):
        return [f"version.yaml: `changes` должен быть словарём {{{', '.join(_CHANGES_LANGS)}}}"]

    lengths: dict[str, int] = {}
    for lang in _CHANGES_LANGS:
        items = changes.get(lang)
        if not isinstance(items, list) or not items:
            errors.append(f"version.yaml: `changes.{lang}` — непустой список заметок о версии")
            continue
        if any(not str(item).strip() for item in items):
            errors.append(f"version.yaml: `changes.{lang}` содержит пустой пункт")
        lengths[lang] = len(items)

    if len(lengths) == len(_CHANGES_LANGS) and len(set(lengths.values())) > 1:
        errors.append(
            f"version.yaml: `changes` разной длины по языкам ({lengths}) — "
            f"пункты должны соответствовать друг другу один к одному"
        )
    return errors


def lint_version_dir(version_dir: Path) -> LintReport:  # noqa: C901, PLR0912, PLR0915
    report = LintReport()
    files_dir = version_dir / "files"
    if not files_dir.is_dir():
        report.errors.append(f"{version_dir}: нет каталога files/")
        return report
    manifest = _load_manifest(version_dir)
    langs = tuple(str(c).lower() for c in manifest.get("langs", []) if isinstance(c, str))

    # ── 1. Jinja-parse (гоча verbatim-fallback) ──
    env = _jinja_env()
    for f in sorted(files_dir.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in _TEXT_SUFFIXES or f.name == PACK_DOC_MANIFEST:
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        if "((*" not in text and "{{" not in text:
            continue
        try:
            env.parse(text)
        except TemplateSyntaxError as exc:
            rel = f.relative_to(files_dir).as_posix()
            msg = f"{rel}:{exc.lineno}: Jinja TemplateSyntaxError ({exc.message}) — файл уйдёт verbatim"
            # Ветки ((* *)) или плейсхолдеры контекста молча пропадут — ошибка;
            # без них verbatim-копия совпадает с намерением — предупреждение.
            if "((*" in text or _PLACEHOLDER_RE.search(text):
                report.errors.append(msg + " (ветки/плейсхолдеры будут потеряны)")
            else:
                report.warnings.append(msg)

    # ── 1a. Анкеты, уезжающие в пакет, обязаны быть required_for_pack ──
    report.errors.extend(_lint_form_extras(manifest))
    report.errors.extend(_lint_check_sources(version_dir))
    report.errors.extend(_lint_changes(manifest))
    report.errors.extend(_lint_signing_routes(manifest))
    report.errors.extend(_lint_default_dates(manifest))
    report.errors.extend(_lint_deadline_hints(manifest))
    for errors, warnings in (
        _lint_slot_placements(version_dir, manifest),
        _lint_signing_slots(manifest),
        _lint_plate_room(manifest),
        lint_anchors(version_dir, manifest),
    ):
        report.errors.extend(errors)
        report.warnings.extend(warnings)

    if not langs:
        report.warnings.append("v1-раскладка (нет `langs:`): проверены только Jinja-шаблоны")
        return report

    # ── 2. Грамматика суффиксов ──
    groups: dict[str, dict[str, str]] = {}
    for f in sorted(files_dir.rglob("*")):
        if not f.is_file() or f.name == PACK_DOC_MANIFEST:
            continue
        rel = f.relative_to(files_dir).as_posix()
        bare, code = _split_lang_qualifier(rel, langs)
        groups.setdefault(bare, {})[code] = rel
        if not code:
            parts = f.name.split(".")
            if len(parts) >= 3 and parts[-2] not in langs and _QUALIFIER_LIKE_RE.match(parts[-2]):
                report.warnings.append(
                    f"{rel}: сегмент «{parts[-2]}» похож на языковой код, но не объявлен в langs "
                    f"{list(langs)} — опечатка или забытый код?"
                )
    for bare, by_code in sorted(groups.items()):
        codes = set(by_code)
        if "" in codes and codes != {""}:
            report.errors.append(
                f"{bare}: смешение bare-файла и языковых редакций в одной группе "
                f"({sorted(by_code.values())}) — bare затеняется, оставьте либо один bare, либо только суффиксы"
            )
        elif codes and "" not in codes and langs[0] not in codes:
            report.warnings.append(
                f"{bare}: нет редакции дефолтного языка «{langs[0]}» (есть {sorted(codes)}) — сиротский перевод"
            )

    # ── 3. Резолв дерева по языкам: \input/\include + source_file ──
    generated = {str(inc.get("output")) for inc in manifest.get("dynamic_includes", []) if isinstance(inc, dict)}
    doc_sources = _doc_sources(version_dir, manifest)
    for lang in langs:
        sources = collect_sources_suffixed(files_dir, langs, lang)
        tree = set(sources) | generated
        for doc_id, src in doc_sources:
            if src not in tree:
                report.errors.append(f"[{lang}] документ {doc_id}: source_file {src!r} не существует в дереве")
        for bare, src_path in sorted(sources.items()):
            if not bare.endswith(".tex"):
                continue
            text = src_path.read_text(encoding="utf-8", errors="replace")
            text = _TEX_COMMENT_RE.sub("", text)  # \input в комментариях не считается
            for m in _INPUT_RE.finditer(text):
                target = m.group(1).strip()
                if "\\" in target or "{{" in target or "((*" in target:
                    continue  # макрос/шаблонизатор — статически не резолвится
                resolved = posixpath.normpath(posixpath.join(posixpath.dirname(bare), target))
                if resolved in tree or f"{resolved}.tex" in tree:
                    continue
                report.errors.append(rf"[{lang}] {bare}: \input{{{target}}} → {resolved} не существует")
    return report


def main(argv: list[str]) -> int:
    # CLI-инструмент авторинга: stdout — его интерфейс, print намеренно.
    if not argv:
        print("usage: python -m hse_doc_studio.infra.template.pack_lint <version_dir>...")  # noqa: T201
        return 2
    exit_code = 0
    for arg in argv:
        vdir = Path(arg)
        report = lint_version_dir(vdir)
        print(f"== {vdir}")  # noqa: T201
        for e in report.errors:
            print(f"  ERROR   {e}")  # noqa: T201
        for w in report.warnings:
            print(f"  warning {w}")  # noqa: T201
        if report.ok and not report.warnings:
            print("  ok")  # noqa: T201
        if not report.ok:
            exit_code = 1
    return exit_code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
