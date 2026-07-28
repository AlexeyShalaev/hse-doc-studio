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
    в UI берётся из пака, приложение названий стандартов и ОП не знает.

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

from hse_doc_studio.infra.project_init.template_renderer import (
    PACK_DOC_MANIFEST,
    _split_lang_qualifier,
    collect_sources_suffixed,
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
