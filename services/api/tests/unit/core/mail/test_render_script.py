"""Скрипт выгрузки писем в файлы для просмотра глазами."""

from __future__ import annotations

import runpy
from pathlib import Path

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.mail import MailTemplate

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "render_mails.py"


def test__render_script__writes_html_and_text_for_every_mail_and_an_index(tmp_path: Path) -> None:
    module = runpy.run_path(str(_SCRIPT))

    code = module["main"](["render_mails.py", str(tmp_path)])

    assert code == 0
    for template in MailTemplate:
        for lang in Lang:
            html = (tmp_path / f"{template.value}.{lang.value}.html").read_text(encoding="utf-8")
            text = (tmp_path / f"{template.value}.{lang.value}.txt").read_text(encoding="utf-8")
            assert html.startswith("<!DOCTYPE html>")
            assert text.startswith("Subject: ")
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert index.count("<iframe") == len(MailTemplate) * len(Lang)
