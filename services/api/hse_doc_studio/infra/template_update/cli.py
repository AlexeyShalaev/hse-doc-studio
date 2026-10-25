r"""Предпросмотр обновления шаблона на реальных проектах — без единой записи.

Для автора пака перед выпуском версии: прогнать план по копиям (или по самим
папкам — CLI ничего не пишет) проектов студентов и посмотреть, сколько файлов
обновится молча, сколько сольётся и где будут конфликты, и откуда взялась база.

  python -m hse_doc_studio.infra.template_update.cli plan <папка проекта>… --to 2026.1.1 [--packs DIR] [--json]
  python -m hse_doc_studio.infra.template_update.cli compare <папка проекта>… [--packs DIR] [--json]

База слияния при этом восстанавливается в памяти и в историю проекта не пишется.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import structlog

from hse_doc_studio.core.template_update.text import same_content
from hse_doc_studio.infra.persistence.project import JsonProjectRepository
from hse_doc_studio.infra.persistence.signature import JsonSignatureRepository
from hse_doc_studio.infra.project_init.template_renderer import TemplateRenderer
from hse_doc_studio.infra.template.yaml_template_repository import YamlTemplateRepository
from hse_doc_studio.infra.template_update.merge_engine import GitMergeFileEngine
from hse_doc_studio.infra.template_update.state import JsonTemplateTrackingRepository
from hse_doc_studio.infra.template_update.tree_renderer import TemplateTreeRenderer
from hse_doc_studio.infra.vcs.git_vcs_service import GitVcsService
from hse_doc_studio.infra.vcs.template_base_store import GitTemplateBaseStore
from hse_doc_studio.use_cases.template_update.base_service import TemplateBaseService
from hse_doc_studio.use_cases.template_update.planning import (
    TemplateUpdatePlanner,
    current_version,
    read_project_files,
)

_DEFAULT_PACKS = Path(__file__).resolve().parents[5] / "packs"


def _services(packs_dir: Path) -> tuple[YamlTemplateRepository, TemplateBaseService, TemplateUpdatePlanner]:
    template_repo = YamlTemplateRepository(packs_dir)
    template_repo.load()
    vcs = GitVcsService()
    bases = TemplateBaseService(TemplateTreeRenderer(template_repo, TemplateRenderer()), GitTemplateBaseStore(vcs), vcs)
    planner = TemplateUpdatePlanner(
        template_repo, bases, GitMergeFileEngine(), JsonTemplateTrackingRepository(), JsonSignatureRepository()
    )
    return template_repo, bases, planner


def _plan_report(planner: TemplateUpdatePlanner, folder: Path, to_version: str) -> dict[str, Any]:
    project = JsonProjectRepository().get(folder)
    if project is None:
        return {"folder": str(folder), "error": "not an HSE Studio project"}
    plan = planner.plan(project, to_version, persist_base=False).plan
    return {
        "folder": str(folder),
        "from": plan.from_version,
        "to": plan.to_version,
        "class": plan.update_class.value if plan.update_class else None,
        "provenance": plan.provenance.value,
        "counts": {action.value: count for action, count in sorted(plan.counts.items())},
        "files": {op.path: op.action.value for op in plan.ops},
        "warnings": [w.code.value for w in plan.warnings],
    }


def _compare_report(template_repo: YamlTemplateRepository, bases: TemplateBaseService, folder: Path) -> dict[str, Any]:
    project = JsonProjectRepository().get(folder)
    if project is None:
        return {"folder": str(folder), "error": "not an HSE Studio project"}
    base = bases.load_or_reconstruct(project, current_version(template_repo, project), persist=False)
    ours = read_project_files(folder, base.files)
    edited = sorted(p for p in base.files if not same_content(p, ours.get(p), base.files[p]))
    return {
        "folder": str(folder),
        "version": project.lock.version,
        "provenance": base.provenance.value,
        "template_files": len(base.files),
        "edited": edited,
        "approximate": sorted(base.approximate_paths),
    }


def _print_human(report: dict[str, Any]) -> None:
    if "error" in report:
        sys.stdout.write(f"{report['folder']}: {report['error']}\n")
        return
    if "counts" in report:
        counts = ", ".join(f"{k} {v}" for k, v in report["counts"].items()) or "без изменений"
        sys.stdout.write(
            f"{report['folder']}: {report['from']} → {report['to']} ({report['class']}), "
            f"база {report['provenance']}: {counts}\n"
        )
        for path, action in report["files"].items():
            sys.stdout.write(f"    {action:<13} {path}\n")
        for warning in report["warnings"]:
            sys.stdout.write(f"    ! {warning}\n")
        return
    sys.stdout.write(
        f"{report['folder']}: {report['version']}, база {report['provenance']}, "
        f"правлено {len(report['edited'])} из {report['template_files']} файлов шаблона\n"
    )
    for path in report["edited"]:
        sys.stdout.write(f"    {path}\n")


def _run(args: argparse.Namespace) -> list[dict[str, Any]]:
    template_repo, bases, planner = _services(args.packs)
    reports: list[dict[str, Any]] = []
    for folder in args.projects:
        try:
            if args.command == "plan":
                reports.append(_plan_report(planner, folder.resolve(), args.to_version))
            else:
                reports.append(_compare_report(template_repo, bases, folder.resolve()))
        except Exception as exc:  # noqa: BLE001 — один проект не мешает отчёту по остальным
            reports.append({"folder": str(folder), "error": str(exc)})
    return reports


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="template-update", description="Предпросмотр обновления шаблона")
    sub = parser.add_subparsers(dest="command", required=True)
    plan_cmd = sub.add_parser("plan", help="план обновления (ничего не пишет)")
    plan_cmd.add_argument("projects", nargs="+", type=Path)
    plan_cmd.add_argument("--to", required=True, dest="to_version")
    compare_cmd = sub.add_parser("compare", help="какие файлы шаблона правил пользователь")
    compare_cmd.add_argument("projects", nargs="+", type=Path)
    for cmd in (plan_cmd, compare_cmd):
        cmd.add_argument("--packs", type=Path, default=_DEFAULT_PACKS)
        cmd.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    # Отчёт — в stdout (его читают скрипты с --json), журнал Студии — в stderr и только важное.
    previous = structlog.get_config()
    structlog.configure(
        logger_factory=structlog.PrintLoggerFactory(sys.stderr),
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
    )
    try:
        reports = _run(args)
    finally:
        structlog.configure(**previous)
    if args.json:
        sys.stdout.write(json.dumps(reports, ensure_ascii=False, indent=2) + "\n")
    else:
        for report in reports:
            _print_human(report)
    return 1 if any("error" in r for r in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
