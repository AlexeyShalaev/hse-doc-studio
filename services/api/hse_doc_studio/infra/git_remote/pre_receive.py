"""Хук `pre-receive` сервера Студии: тонкий слой над `core.git_remote.push_policy`.

Запускается процессом `git receive-pack` как `python -I -m ...`: читает строки `old new ref` из stdin, политику
из файла `HSE_PUSH_POLICY`, смотрит итоговую разницу `old..new` (объекты ещё в карантине, git видит их через
окружение хука) и при нарушениях печатает по строке на нарушение и выходит с 1. Импортирует только `core`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path

from hse_doc_studio.core.git_remote.entities import ZERO_SHA, PushChange, PushPolicy, PushViolation, PushViolationCode
from hse_doc_studio.core.git_remote.push_policy import (
    PROJECT_JSON_PATH,
    check_push,
    check_ref_update,
    policy_from_json,
)

MAX_LINES = 20
_STATUSES = frozenset({"A", "M", "D", "T"})

_TEXTS: dict[str, dict[PushViolationCode, str]] = {
    "ru": {
        PushViolationCode.ref_forbidden: (
            "можно отправлять только в текущую ветку проекта, без новых веток, тегов и удалений"
        ),
        PushViolationCode.not_fast_forward: "сервер получил новые правки: сделайте fetch, слияние и отправьте снова",
        PushViolationCode.path_outside_scope: "вне вашей папки в командном проекте",
        PushViolationCode.unsafe_path: "недопустимый путь",
        PushViolationCode.symlink: "символьные ссылки не принимаются",
        PushViolationCode.submodule: "подмодули не принимаются",
        PushViolationCode.large_file: "файл больше допустимого размера",
        PushViolationCode.schema_newer: "проект сохранён более новой версией Студии, чем на сервере",
        PushViolationCode.service_dir: "служебные файлы Студии не принимаются",
    },
    "en": {
        PushViolationCode.ref_forbidden: (
            "only the project's current branch can be pushed, no new branches, tags or deletes"
        ),
        PushViolationCode.not_fast_forward: "the server has new changes: fetch, merge and push again",
        PushViolationCode.path_outside_scope: "outside your folder in this team project",
        PushViolationCode.unsafe_path: "path is not allowed",
        PushViolationCode.symlink: "symbolic links are not accepted",
        PushViolationCode.submodule: "submodules are not accepted",
        PushViolationCode.large_file: "file exceeds the allowed size",
        PushViolationCode.schema_newer: "the project was saved by a newer Studio than the server runs",
        PushViolationCode.service_dir: "Studio service files are not accepted",
    },
}


def _git(*args: str, data: bytes | None = None) -> bytes:
    """git с окружением хука: GIT_DIR и каталоги карантина ставит сам receive-pack."""
    return subprocess.run(  # noqa: S603 — аргументы собраны здесь
        ["git", "-c", "core.fsmonitor=false", *args],  # noqa: S607
        input=data,
        capture_output=True,
        check=True,
    ).stdout


def is_ancestor(old: str, new: str) -> bool:
    result = subprocess.run(  # noqa: S603 — аргументы собраны здесь
        ["git", "merge-base", "--is-ancestor", old, new],  # noqa: S607
        capture_output=True,
        check=False,
    )
    return result.returncode == 0


def changes_between(old: str, new: str) -> list[PushChange]:
    """`diff-tree -r` без переименований: режим и blob нового состояния, размеры одним `cat-file --batch-check`."""
    raw = _git("diff-tree", "-r", "-z", "--no-renames", "--no-commit-id", old, new).split(b"\0")
    entries: list[tuple[str, str, str, str]] = []
    for meta, path in zip(raw[0::2], raw[1::2], strict=False):
        if not meta.startswith(b":"):
            continue
        _old_mode, new_mode, _old_sha, new_sha, status = meta[1:].decode().split(" ")
        entries.append((status[:1], path.decode("utf-8", errors="surrogateescape"), new_mode, new_sha))
    sizes = _blob_sizes([sha for st, _p, mode, sha in entries if st != "D" and mode not in ("160000",)])
    changes: list[PushChange] = []
    for raw_status, path, mode, sha in entries:
        status = raw_status if raw_status in _STATUSES else "M"
        deleted = status == "D"
        changes.append(
            PushChange(
                status=status,  # type: ignore[arg-type]
                path=path,
                mode=None if deleted else mode,
                size=None if deleted else sizes.get(sha),
            )
        )
    return changes


def _blob_sizes(shas: Sequence[str]) -> dict[str, int]:
    if not shas:
        return {}
    out = _git("cat-file", "--batch-check=%(objectname) %(objectsize)", data="\n".join(shas).encode() + b"\n")
    sizes: dict[str, int] = {}
    for line in out.decode().splitlines():
        parts = line.split(" ")
        if len(parts) == 2 and parts[1].isdigit():  # noqa: PLR2004 — «sha размер»
            sizes[parts[0]] = int(parts[1])
    return sizes


def project_json_at(new: str, changes: Sequence[PushChange]) -> bytes | None:
    if not any(c.path == PROJECT_JSON_PATH and c.status != "D" for c in changes):
        return None
    try:
        return _git("cat-file", "blob", f"{new}:{PROJECT_JSON_PATH}")
    except subprocess.CalledProcessError:
        return None


def check_updates(policy: PushPolicy, lines: Sequence[str]) -> list[PushViolation]:
    updates = [line.split() for line in lines if line.strip()]
    if len(updates) != 1 or len(updates[0]) != 3:  # noqa: PLR2004 — «old new ref»
        refs = ", ".join(parts[-1] for parts in updates if parts) or None
        return [PushViolation(PushViolationCode.ref_forbidden, refs)]
    old, new, ref = updates[0]
    if (violation := check_ref_update(policy, old, new, ref)) is not None:
        return [violation]
    if old != ZERO_SHA and not is_ancestor(old, new):
        return [PushViolation(PushViolationCode.not_fast_forward, ref)]
    changes = changes_between(old, new)
    return check_push(policy, changes, project_json_at(new, changes))


def render(violations: Sequence[PushViolation], lang: str) -> list[str]:
    texts = _TEXTS.get(lang, _TEXTS["en"])
    head = (
        f"HSE Doc Studio: отправка отклонена ({len(violations)})"
        if lang == "ru"
        else f"HSE Doc Studio: push rejected ({len(violations)} problems)"
    )
    lines = [head]
    for violation in violations[:MAX_LINES]:
        where = f"{violation.path}: " if violation.path else ""
        lines.append(f"- {where}{texts[violation.code]} [{violation.code.value}]")
    if len(violations) > MAX_LINES:
        rest = len(violations) - MAX_LINES
        lines.append(f"… и ещё {rest}" if lang == "ru" else f"… and {rest} more")
    return lines


def main() -> int:
    lang = os.environ.get("HSE_PUSH_LANG", "en")
    try:
        policy = policy_from_json(Path(os.environ["HSE_PUSH_POLICY"]).read_text(encoding="utf-8"))
        violations = check_updates(policy, sys.stdin.read().splitlines())
    except (KeyError, OSError, ValueError, subprocess.CalledProcessError):
        sys.stderr.write("HSE Doc Studio: push rejected (internal check failed)\n")
        return 1
    if not violations:
        return 0
    sys.stderr.write("\n".join(render(violations, lang)) + "\n")
    return 1


if __name__ == "__main__":
    sys.exit(main())
