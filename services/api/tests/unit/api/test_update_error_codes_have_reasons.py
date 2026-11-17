"""Каждый код ошибки исполнителя и api имеет причину в админке: новый код без строки не пройдёт."""

from __future__ import annotations

import re
from pathlib import Path

from hse_doc_studio.infra.update import server_updater

_API = Path(__file__).resolve().parents[3]
_SRC = Path(server_updater.__file__).parent
_SERVICE = _API / "hse_doc_studio" / "use_cases" / "server_update" / "service.py"
_WEB = _API.parent / "web-app" / "src" / "features" / "admin-updates" / "lib" / "failureReason.ts"

# Коды, которые исполнитель кладёт в `error_code` литералом, и коды, которые ставит сам api.
_EXECUTOR = re.compile(r'(?:AbortError|_StepError)\(\s*"([a-z_]+)"')
_EMIT = re.compile(r'error_code="([a-z_]+)"')
_NAMED = re.compile(r'^[A-Z_]+ = "([a-z_]+)"$', re.M)
_API = re.compile(r'_finish\(\s*run,\s*RunStatus\.\w+,\s*"([a-z_]+)"')


def _codes() -> set[str]:
    found: set[str] = set()
    for path in _SRC.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        found |= set(_EXECUTOR.findall(text)) | set(_EMIT.findall(text))
        if path.name == "kube_engine.py":
            found |= set(_NAMED.findall(text))
    found |= set(_API.findall(_SERVICE.read_text(encoding="utf-8")))
    return found


def _known() -> set[str]:
    text = _WEB.read_text(encoding="utf-8")
    block = text[text.index("export const CODE_REASON") : text.index("// Коды, под которыми")]
    return set(re.findall(r"^\s+([a-z_]+): \"", block, re.M))


def test__every_error_code_has_a_reason_in_the_admin_ui() -> None:
    codes = _codes()
    assert {"migration_failed", "kube_forbidden", "updater_lost", "needs_manual_action"} <= codes, "поиск кодов сломан"
    missing = sorted(codes - _known())
    assert not missing, f"добавьте в CODE_REASON (web-app/.../failureReason.ts) и в словари: {missing}"
