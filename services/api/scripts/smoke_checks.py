"""Standalone smoke runner for the check engines.

Loads every YAML rule file from the hse-cs-se pack and executes the rules
against a real on-disk project (default: ../test-hsda) — without booting the
FastAPI app, without DI, without the broken signatures persistence chain.

Run from the service root:

    uv run python scripts/smoke_checks.py
    uv run python scripts/smoke_checks.py --project ../test-hsda --doc vkr

Output: a flat list of every check result (severity, rule_id, location,
message) plus a summary count per severity.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

# Make the package importable when invoked from the service root.
_SERVICE_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_SERVICE_ROOT))

from hse_doc_studio.core.catalog import CheckRule  # noqa: E402
from hse_doc_studio.core.enums import CheckEngine, CheckSeverity  # noqa: E402
from hse_doc_studio.infra.checks.file_exists_engine import FileExistsCheckEngine  # noqa: E402
from hse_doc_studio.infra.checks.log_parse_engine import LogParseCheckEngine  # noqa: E402
from hse_doc_studio.infra.checks.python_engine import PythonCheckEngine  # noqa: E402
from hse_doc_studio.infra.checks.reference_check_engine import ReferenceCheckEngine  # noqa: E402
from hse_doc_studio.infra.checks.regex_engine import RegexCheckEngine  # noqa: E402
from hse_doc_studio.infra.checks.structural_engine import StructuralCheckEngine  # noqa: E402
from hse_doc_studio.infra.checks.tex_command_count_engine import TexCommandCountEngine  # noqa: E402

_ENGINES = {
    CheckEngine.regex: RegexCheckEngine(),
    CheckEngine.file_exists: FileExistsCheckEngine(),
    CheckEngine.tex_command_count: TexCommandCountEngine(),
    CheckEngine.log_parse: LogParseCheckEngine(),
    CheckEngine.structural: StructuralCheckEngine(),
    CheckEngine.python: PythonCheckEngine(),
    CheckEngine.reference_check: ReferenceCheckEngine(),
}


def _to_rule(data: dict[str, Any]) -> CheckRule | None:
    """Mirror of yaml_template_repository._parse_check_rule, slimmed down."""
    try:
        applies = data.get("applies_to", "*")
        if applies != "*" and not isinstance(applies, list):
            applies = [str(applies)]
        # YAML uses `default_severity` (matches the existing convention); fall
        # back to `severity` for forward compatibility.
        sev_raw = data.get("default_severity") or data.get("severity") or "warn"
        return CheckRule(
            id=data["id"],
            title=data.get("title", {}),
            description=data.get("description", {}),
            category=data.get("category"),
            applies_to=applies,
            default_severity=CheckSeverity(sev_raw),
            engine=CheckEngine(data.get("engine", "structural")),
            params=dict(data.get("params", {})),
        )
    except (KeyError, ValueError) as exc:
        print(f"  ! skipped rule {data.get('id')!r}: {exc}", file=sys.stderr)
        return None


def _load_rules(checks_dir: Path) -> list[CheckRule]:
    rules: list[CheckRule] = []
    for yaml_file in sorted(checks_dir.glob("*.yaml")):
        try:
            doc = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            print(f"YAML error in {yaml_file.name}: {exc}", file=sys.stderr)
            continue
        if not isinstance(doc, dict):
            continue
        for raw in doc.get("rules", []) or []:
            rule = _to_rule(raw)
            if rule is not None:
                rules.append(rule)
    return rules


def _applies(rule: CheckRule, doc_id: str) -> bool:
    if rule.applies_to == "*":
        return True
    return doc_id in rule.applies_to


def _doc_source_file(doc_id: str) -> str:
    return f"{doc_id}/{doc_id}.tex"


_SEVERITY_GLYPH = {
    CheckSeverity.err: "ERR",
    CheckSeverity.warn: "WRN",
    CheckSeverity.info: "INF",
}


def main() -> int:
    repo_root = _SERVICE_ROOT.parent.parent  # services/<svc>/scripts/.. → repo
    default_project = repo_root / "test-hsda"
    default_checks = repo_root / "packs" / "hse-cs-se" / "templates" / "vkr" / "versions" / "2026.1" / "checks"

    parser = argparse.ArgumentParser(description="Run check engines on a project.")
    parser.add_argument("--project", type=Path, default=default_project)
    parser.add_argument("--checks", type=Path, default=default_checks)
    parser.add_argument(
        "--doc",
        action="append",
        default=None,
        help="Document id to evaluate (repeatable). Default: vkr, tz, pmi.",
    )
    parser.add_argument(
        "--engine",
        action="append",
        default=None,
        choices=[e.value for e in CheckEngine],
        help="Filter to one engine type (repeatable). Default: all.",
    )
    parser.add_argument(
        "--lt-url",
        default="http://localhost:8010",
        help="LanguageTool server URL for the `external` engine (default: http://localhost:8010).",
    )
    args = parser.parse_args()

    project_folder: Path = args.project.resolve()
    checks_dir: Path = args.checks.resolve()
    docs: list[str] = args.doc or ["vkr", "tz", "pmi"]
    engine_filter: set[CheckEngine] | None = {CheckEngine(e) for e in args.engine} if args.engine else None

    print(f"Project:  {project_folder}")
    print(f"Checks:   {checks_dir}")
    print(f"Docs:     {', '.join(docs)}")
    if engine_filter is not None:
        print(f"Engines:  {', '.join(sorted(e.value for e in engine_filter))}")
    print()

    if not project_folder.is_dir():
        print(f"!! project folder not found: {project_folder}", file=sys.stderr)
        return 2
    if not checks_dir.is_dir():
        print(f"!! checks dir not found: {checks_dir}", file=sys.stderr)
        return 2

    # The external (LanguageTool) engine is not in the module-level _ENGINES map
    # because it needs a settings repo + HTTP client. Register it on demand —
    # gated as enabled, pointing at --lt-url — so `--engine external` can smoke
    # a running LanguageTool without booting the API.
    if engine_filter is None or CheckEngine.external in engine_filter:
        import httpx  # noqa: PLC0415 — optional, only needed for the external engine
        from hse_doc_studio.infra.checks.external_engine import (  # noqa: PLC0415
            ExternalCheckEngine,
        )

        class _StaticSettingsRepo:
            def __init__(self, enabled: bool, url: str) -> None:
                self._data = {"languagetool_enabled": enabled, "languagetool_url": url}

            def get(self) -> dict[str, Any]:
                return dict(self._data)

            def save(self, settings: dict[str, Any]) -> None:  # pragma: no cover - unused
                self._data = dict(settings)

        _ENGINES[CheckEngine.external] = ExternalCheckEngine(
            settings_repo=_StaticSettingsRepo(enabled=True, url=args.lt_url),
            client=httpx.Client(timeout=30.0),
        )
        print(f"LanguageTool: {args.lt_url} (external engine enabled)")

    rules = _load_rules(checks_dir)
    if engine_filter is not None:
        rules = [r for r in rules if r.engine in engine_filter]
    print(f"Loaded {len(rules)} rules.\n")

    severity_total: Counter[CheckSeverity] = Counter()
    engine_total: Counter[CheckEngine] = Counter()
    diag_total = 0

    for doc_id in docs:
        print(f"=== {doc_id} ===")
        source_file = _doc_source_file(doc_id)
        log_path = project_folder / source_file.replace(".tex", ".log")
        log_content = log_path.read_text(encoding="utf-8", errors="replace") if log_path.is_file() else None

        doc_rules = [r for r in rules if _applies(r, doc_id)]
        if not doc_rules:
            print("  (no rules apply)\n")
            continue

        any_diag = False
        for rule in doc_rules:
            engine = _ENGINES.get(rule.engine)
            if engine is None:
                continue
            try:
                results = engine.run(
                    rule=rule,
                    severity=rule.default_severity,
                    project_folder=project_folder,
                    doc_id=doc_id,
                    source_file=source_file,
                    log_content=log_content,
                )
            except Exception as exc:  # noqa: BLE001 — surface engine bugs
                print(f"  !! engine error in {rule.id}: {exc}")
                continue
            for result in results:
                any_diag = True
                diag_total += 1
                severity_total[result.severity] += 1
                engine_total[rule.engine] += 1
                glyph = _SEVERITY_GLYPH.get(result.severity, "?")
                loc = result.location
                loc_s = f"{loc.file}:{loc.line}" if (loc and loc.line) else (loc.file if loc else "—")
                print(f"  {glyph} [{result.severity.value:4}] {rule.id}")
                print(f"      {loc_s}")
                print(f"      {result.message}")
        if not any_diag:
            print("  all good — no diagnostics.")
        print()

    print("=== summary ===")
    print(f"diagnostics: {diag_total}")
    for sev in (CheckSeverity.err, CheckSeverity.warn, CheckSeverity.info):
        print(f"  {sev.value:4}: {severity_total.get(sev, 0)}")
    print("  by engine:")
    for eng, count in sorted(engine_total.items(), key=lambda kv: -kv[1]):
        print(f"    {eng.value:18} {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
