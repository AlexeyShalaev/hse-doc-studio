"""`hse-doc-studio pack`: команды автора паков и CI репозитория паков (docs/design/template-studio.md, 11).

    pack lint <каталог>...                       линтер всех версий под каталогами
    pack check <каталог>... [--base REF]         lint, releases check, схемы, классы невыпущенных, сверка с базой
    pack classify <шаблон> [<база>] <новая>      класс новой версии с причинами
    pack new-version <шаблон> [--from V] [--to V | --class C]
                                                 копия версии в новый номер, status: beta
    pack freeze <шаблон> <версия> [--release] [--default] [--kind C] [--replace] [--base REF]
                                                 выпуск: запись в releases.yaml
    pack ci init [<репозиторий>] [--provider github|gitlab] [--packs-path P] [--image I] [--branch B]
                                                 файл CI репозитория паков: `pack check` в образе Студии

Каталог это версия, шаблон, пак или папка с паками. `--json` печатает в stdout один объект JSON (для CI и агентов),
текст для человека иначе. Коды выхода: 0 всё в порядке; 1 найдены ошибки (с `--strict` и предупреждения), номер
мягче класса или операция отказана; 2 неверные аргументы, каталог не найден, ссылка git не разобрана.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from hse_doc_studio.core.enums import TemplateUpdateClass
from hse_doc_studio.core.template_diff import classify_change
from hse_doc_studio.core.template_versions import is_softer
from hse_doc_studio.infra.pack_studio.base_ref import BaseRefError, BaseReleases
from hse_doc_studio.infra.pack_studio.check import CheckResult, check_tree, lint_tree
from hse_doc_studio.infra.pack_studio.ci_init import (
    PackCiError,
    PackCiProvider,
    default_image,
    detect_branch,
    render_pack_ci,
    write_pack_ci,
)
from hse_doc_studio.infra.pack_studio.layout import PackPathError, discover, require_template, resolve_version
from hse_doc_studio.infra.pack_studio.versions import (
    LintFailedError,
    PackVersionError,
    create_version,
    previous_version,
    release_version,
)

EXIT_OK = 0
EXIT_FAILED = 1
EXIT_USAGE = 2

_CLASSES = [c.value for c in TemplateUpdateClass]


def _out(line: str = "") -> None:
    sys.stdout.write(line + "\n")


def _err(line: str) -> None:
    sys.stderr.write(line + "\n")


def _json(payload: dict[str, Any]) -> None:
    _out(json.dumps(payload, ensure_ascii=False, indent=2))


def configure_parser(pack: argparse.ArgumentParser) -> None:
    """Подкоманды `pack`: общие для `hse-doc-studio pack` и прежнего `python -m ...pack_lint`."""
    sub = pack.add_subparsers(dest="pack_command", required=True)

    def common(cmd: argparse.ArgumentParser) -> None:
        cmd.add_argument("--json", action="store_true", help="один объект JSON в stdout")

    lint = sub.add_parser("lint", help="линтер пака для всех версий под каталогами")
    lint.add_argument("paths", nargs="+", type=Path, metavar="каталог", help="версия, шаблон, пак или папка паков")
    lint.add_argument("--strict", action="store_true", help="код 1 и при предупреждениях")
    common(lint)

    check = sub.add_parser("check", help="lint, releases check, схемы и классы невыпущенных версий (для CI)")
    check.add_argument("paths", nargs="+", type=Path, metavar="каталог", help="версия, шаблон, пак или папка паков")
    check.add_argument(
        "--base", metavar="REF", help="базовая ветка git: выпущенные версии и их записи в releases.yaml по ней"
    )
    check.add_argument("--strict", action="store_true", help="код 1 и при предупреждениях")
    check.add_argument("--lang", choices=("ru", "en"), default="ru", help="язык отчёта классификатора")
    common(check)

    classify = sub.add_parser("classify", help="класс новой версии по содержимому с причинами")
    classify.add_argument("template", type=Path, metavar="шаблон", help="каталог шаблона (с versions/)")
    classify.add_argument(
        "versions",
        nargs="+",
        metavar="версия",
        help="[база] новая: номер или путь; без базы берётся предыдущая выпущенная",
    )
    classify.add_argument("--lang", choices=("ru", "en"), default="ru", help="язык причин")
    common(classify)

    new = sub.add_parser("new-version", help="копия версии в новый номер (status: beta)")
    new.add_argument("template", type=Path, metavar="шаблон", help="каталог шаблона (с versions/)")
    new.add_argument("--from", dest="base", metavar="V", help="база копии (по умолчанию последняя версия)")
    number = new.add_mutually_exclusive_group()
    number.add_argument("--to", metavar="V", help="номер новой версии")
    number.add_argument(
        "--class",
        dest="update_class",
        choices=_CLASSES,
        help="номер по классу от последней версии (по умолчанию patch; major даёт <год+1>.1)",
    )
    common(new)

    freeze = sub.add_parser("freeze", help="выпуск версии: запись в releases.yaml (как releases freeze)")
    freeze.add_argument("template", type=Path, metavar="шаблон", help="каталог шаблона (с versions/)")
    freeze.add_argument("version", metavar="версия")
    freeze.add_argument("--kind", choices=_CLASSES, help="класс выпуска (по умолчанию release.kind, иначе по номеру)")
    freeze.add_argument(
        "--release", action="store_true", help="отметить выпущенной: status: stable, released_at сегодня, release.kind"
    )
    freeze.add_argument("--default", action="store_true", help="сделать default_version шаблона")
    freeze.add_argument(
        "--replace", action="store_true", help="пересчитать запись уже внесённой версии, пока выпуск не слит"
    )
    freeze.add_argument("--base", metavar="REF", help="базовая ветка git: с --replace запрет на выпущенные в ней")
    common(freeze)

    ci = sub.add_parser("ci", help="CI репозитория паков (GitHub Actions, GitLab CI)")
    ci_sub = ci.add_subparsers(dest="ci_command", required=True)
    init = ci_sub.add_parser("init", help="положить файл CI: `pack check` в опубликованном образе Студии")
    init.add_argument(
        "root", nargs="?", type=Path, default=Path(), metavar="репозиторий", help="корень репозитория (по умолчанию .)"
    )
    init.add_argument(
        "--provider",
        choices=[p.value for p in PackCiProvider],
        default=PackCiProvider.github.value,
        help="github: .github/workflows/hse-packs.yml; gitlab: .gitlab-ci.yml",
    )
    init.add_argument("--packs-path", default="packs", metavar="P", help="папка паков от корня (по умолчанию packs)")
    init.add_argument("--image", metavar="I", help="образ Студии (по умолчанию этой версии)")
    init.add_argument("--branch", metavar="B", help="основная ветка для push (GitHub; по умолчанию из origin/HEAD)")
    init.add_argument("--force", action="store_true", help="заменить существующий файл")
    init.add_argument("--stdout", action="store_true", help="напечатать файл, ничего не записывая")
    common(init)


# ── lint и check ──


def _print_findings(result: CheckResult, *, tagged: bool, every_version: bool) -> None:
    groups: dict[str, list[str]] = {}
    if every_version:
        for version_dir in result.tree.versions:
            groups[str(version_dir)] = []
    for finding in result.findings:
        word = "ERROR  " if finding.severity == "error" else "warning"
        tag = f"[{finding.check}] " if tagged else ""
        groups.setdefault(finding.path, []).append(f"  {word} {tag}{finding.message}")
    for path, lines in groups.items():
        _out(f"== {path}")
        for line in lines or ["  ok"]:
            _out(line)


def _summary(result: CheckResult) -> str:
    tree = result.tree
    return (
        f"паков {len(tree.packs)}, шаблонов {len(tree.templates)}, версий {len(tree.versions)}: "
        f"ошибок {result.errors}, предупреждений {result.warnings}"
    )


def _scenario_line(item: Any) -> str:
    """Строка сводки сценариев шаблона: прогон и покрытие правил."""
    return (
        f"сценарии {item.template}@{item.version}: {item.scenarios} (прошли {item.passed}, упали {item.failed}, "
        f"ошибок {item.errors}, без ожидания {item.unchecked}); покрытие правил {item.percent:g}% "
        f"(полностью {item.rules_covered}, наполовину {item.rules_half}, не покрыто {item.rules_uncovered}), "
        f"комбинаций затронуто {item.rows_touched} из {item.rows_total}"
    )


def _lint(args: argparse.Namespace) -> int:
    result = lint_tree(discover(args.paths))
    if args.json:
        _json({"command": "lint", **result.to_dict(strict=args.strict)})
    else:
        _print_findings(result, tagged=False, every_version=True)
        _out(_summary(result))
    return EXIT_OK if result.ok(strict=args.strict) else EXIT_FAILED


def _check(args: argparse.Namespace) -> int:
    tree = discover(args.paths)
    result = check_tree(tree, BaseReleases(args.base) if args.base else None, load=True)
    if args.json:
        _json({"command": "check", "base": args.base, **result.to_dict(strict=args.strict)})
    else:
        _print_findings(result, tagged=True, every_version=False)
        for scenario in result.scenarios:
            _out(_scenario_line(scenario))
        for item in result.classes:
            report = item.report
            number = report.by_number.value if report.by_number else "-"
            _out(f"класс {item.version_dir} (от {item.base}): {report.headline(args.lang)}; по номеру {number}")
        _out(_summary(result))
    return EXIT_OK if result.ok(strict=args.strict) else EXIT_FAILED


# ── classify ──


def _classify(args: argparse.Namespace) -> int:
    template_dir = require_template(args.template)
    if len(args.versions) > 2:  # noqa: PLR2004 — база и новая
        raise PackPathError("classify: нужны [база] и новая версия, не больше двух")
    new_dir = resolve_version(template_dir, args.versions[-1])
    if len(args.versions) == 2:  # noqa: PLR2004
        base_dir = resolve_version(template_dir, args.versions[0])
    else:
        base = previous_version(template_dir, new_dir.name)
        if base is None:
            raise PackPathError(f"{template_dir.name}@{new_dir.name}: нет версии ниже, укажите базу явно")
        base_dir = template_dir / "versions" / base
    report = classify_change(base_dir, new_dir)
    number = report.by_number
    number_ok = number is None or not is_softer(number, report.minimum)
    if args.json:
        _json(
            {
                "command": "classify",
                "template": template_dir.name,
                "base_path": str(base_dir),
                "new_path": str(new_dir),
                "number_ok": number_ok,
                **report.to_dict(),
            }
        )
    else:
        _out(report.render(args.lang))
        if not number_ok:
            _out(
                f"номер {new_dir.name} мягче минимума {report.minimum.value}"
                if args.lang == "ru"
                else f"version number {new_dir.name} is softer than the minimum {report.minimum.value}"
            )
    return EXIT_OK if number_ok else EXIT_FAILED


# ── new-version и freeze ──


def _new_version(args: argparse.Namespace) -> int:
    update_class = TemplateUpdateClass(args.update_class) if args.update_class else None
    created = create_version(args.template, base=args.base, to=args.to, update_class=update_class)
    if args.json:
        _json({"command": "new-version", "ok": True, **created.to_dict()})
        return EXIT_OK
    cls = created.update_class.value if created.update_class else "-"
    _out(f"{created.template_dir.name}@{created.version}: копия {created.base} ({cls}) в {created.path}")
    _out("  version.yaml: id, status: beta, released_at сегодня; release убран, changes и breaking_changes пусты")
    for note in created.notes:
        _out(f"  внимание: {note}")
    _out(
        "Дальше: правки, заметки changes ru/en, класс `pack classify` и при нужде release.kind и release.note; "
        "выпуск `pack freeze --release`."
    )
    return EXIT_OK


def _freeze(args: argparse.Namespace) -> int:
    template_dir = require_template(args.template)
    released = release_version(
        template_dir,
        args.version,
        kind=TemplateUpdateClass(args.kind) if args.kind else None,
        mark_released=args.release,
        set_default=args.default,
        replace=args.replace,
        base=BaseReleases(args.base) if args.base else None,
    )
    if args.json:
        _json({"command": "freeze", "ok": True, **released.to_dict()})
        return EXIT_OK
    entry = released.entry
    kind = entry.kind.value if entry.kind else "-"
    verb = "запись заменена" if released.replaced else "внесена"
    _out(f"{template_dir.name}@{entry.version}: {verb}, {entry.digest} ({kind})")
    for path in released.edited:
        _out(f"  изменён {path}")
    for warning in released.warnings:
        _out(f"  warning {warning}")
    return EXIT_OK


# ── ci init ──


def _ci(args: argparse.Namespace) -> int:
    root: Path = args.root
    if not root.is_dir():
        raise PackPathError(f"{root}: каталог не найден")
    ci_file = render_pack_ci(
        PackCiProvider(args.provider),
        image=args.image or default_image(),
        packs_path=args.packs_path,
        branch=args.branch or detect_branch(root),
    )
    warnings = [] if (root / ci_file.packs_path).is_dir() else [f"папки паков {ci_file.packs_path} нет в {root}"]
    if args.stdout:
        if args.json:
            _json({"command": "ci init", "ok": True, "path": ci_file.path, "content": ci_file.content})
        else:
            sys.stdout.write(ci_file.content)
        return EXIT_OK
    target = write_pack_ci(root, ci_file, force=args.force)
    if args.json:
        payload = {"path": str(target), "image": ci_file.image, "packs_path": ci_file.packs_path, "warnings": warnings}
        _json({"command": "ci init", "ok": True, "provider": ci_file.provider.value, **payload})
        return EXIT_OK
    _out(f"{target}: {ci_file.provider.value}, образ {ci_file.image}, паки {ci_file.packs_path}")
    for warning in warnings:
        _out(f"  warning {warning}")
    _out("Дальше: закоммитьте файл; новая Студия, новый тег образа: запустите команду снова с --force.")
    return EXIT_OK


_COMMANDS: dict[str, Callable[[argparse.Namespace], int]] = {
    "lint": _lint,
    "check": _check,
    "classify": _classify,
    "new-version": _new_version,
    "freeze": _freeze,
    "ci": _ci,
}


def _fail(args: argparse.Namespace, code: int, kind: str, message: str, details: list[str] | None = None) -> int:
    if getattr(args, "json", False):
        error: dict[str, Any] = {"code": kind, "message": message}
        if details:
            error["errors"] = details
        _json({"command": args.pack_command, "ok": False, "error": error})
    else:
        _err(f"error: {message}")
        for line in details or []:
            _err(f"  ERROR   {line}")
    return code


def run_parsed(args: argparse.Namespace) -> int:
    """Запуск разобранной подкоманды `pack`; ошибки становятся кодом выхода и сообщением, не трассировкой."""
    try:
        return _COMMANDS[args.pack_command](args)
    except LintFailedError as exc:
        return _fail(args, EXIT_FAILED, "lint_failed", str(exc), exc.errors)
    except PackVersionError as exc:
        return _fail(args, EXIT_FAILED, "refused", str(exc))
    except PackCiError as exc:
        return _fail(args, EXIT_FAILED if exc.code == "exists" else EXIT_USAGE, exc.code, str(exc))
    except (PackPathError, BaseRefError) as exc:
        return _fail(args, EXIT_USAGE, "usage", str(exc))


def run_pack(argv: Sequence[str]) -> int:
    """`hse-doc-studio pack ...` без остального CLI (прежний вход `pack_lint` и тесты)."""
    parser = argparse.ArgumentParser(prog="hse-doc-studio pack", description="Команды автора паков")
    configure_parser(parser)
    return run_parsed(parser.parse_args(list(argv)))
