from __future__ import annotations

from pathlib import Path, PurePosixPath

import structlog

from hse_doc_studio.core.catalog import CheckRule
from hse_doc_studio.core.enums import CheckSeverity
from hse_doc_studio.core.value_objects import CheckLocation, CheckResult
from hse_doc_studio.infra.checks.base import BaseCheckEngine
from hse_doc_studio.infra.checks.utils import localized_message

logger = structlog.get_logger()


def _per_author_variant(rel_path: str, doc_id: str) -> str | None:
    """Имя того же файла для конкретного автора: `<stem>--<slug><suffix>`.

    В командной работе документ зовётся `thesis--shalaev`, и сопутствующие ему
    файлы движок форм пишет с тем же суффиксом (`ai_declaration--shalaev.json`).
    Правило же в паке называет файл одним именем — тем, что у одиночной работы.
    Без этой развёртки проверка в командном проекте не находит файл НИКОГДА,
    сколько бы форм автор ни заполнил.
    """
    owner = doc_id.split("--", 1)[1] if "--" in doc_id else ""
    if not owner:
        return None
    path = PurePosixPath(rel_path)
    return str(path.with_name(f"{path.stem}--{owner}{path.suffix}"))


class FileExistsCheckEngine(BaseCheckEngine):
    """Checks if a file exists at params['path'] relative to project folder."""

    def run(
        self,
        rule: CheckRule,
        severity: CheckSeverity,
        project_folder: Path,
        doc_id: str,
        source_file: str,  # noqa: ARG002
        log_content: str | None,  # noqa: ARG002
        base_dir: str = "",
    ) -> list[CheckResult]:
        rel_path: str = rule.params.get("path", "")
        if not rel_path:
            logger.warning("file_exists_engine: no path in rule", rule_id=rule.id)
            return []

        # Пути пака (`tz/tz.tex`, `common/fonts.tex`) — от базы инстанса;
        # служебные (`.hse-studio/...`) живут в корне, поэтому корень — фолбэк.
        # Пер-авторский вариант проверяем ПОСЛЕ общего: общий файл в командной
        # работе означает «заполнено на всех», и это тоже засчитывается.
        candidates = [rel_path]
        per_author = _per_author_variant(rel_path, doc_id)
        if per_author is not None:
            candidates.append(per_author)

        for candidate in candidates:
            base_target = (project_folder / base_dir / candidate) if base_dir else (project_folder / candidate)
            if base_target.exists() or (project_folder / candidate).exists():
                return []

        message = localized_message(
            rule.params.get("message"),
            fallback={
                "ru": f"Не найден обязательный файл: {rel_path}",
                "en": f"Required file not found: {rel_path}",
            },
        )
        return [
            CheckResult(
                rule_id=rule.id,
                severity=severity,
                message=message,
                location=CheckLocation(file=rel_path, line=None),
            )
        ]
