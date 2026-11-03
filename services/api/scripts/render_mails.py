"""Выгружает все письма Студии в HTML и txt, чтобы посмотреть их глазами.

Запуск из services/api: `uv run python scripts/render_mails.py OUT_DIR`.

Для каждого вида и языка пишет `<вид>.<язык>.html` и `.txt`, рядом `index.html` со списком и встроенными
превью (светлая тема клиента, тёмную и узкий экран можно включить в DevTools браузера).
"""

from __future__ import annotations

import sys
from html import escape
from pathlib import Path

from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.mail.compose import MailTemplate
from hse_doc_studio.core.mail.samples import sample_mail


def main(argv: list[str]) -> int:
    out = Path(argv[1] if len(argv) > 1 else "mail-preview")
    out.mkdir(parents=True, exist_ok=True)
    cards: list[str] = []
    for template in MailTemplate:
        for lang in Lang:
            mail = sample_mail(template, lang)
            stem = f"{template.value}.{lang.value}"
            (out / f"{stem}.html").write_text(mail.html, encoding="utf-8")
            (out / f"{stem}.txt").write_text(f"Subject: {mail.subject}\n\n{mail.text}", encoding="utf-8")
            cards.append(
                f'<section><h2>{escape(stem)}</h2><p>{escape(mail.subject)} (<a href="{stem}.txt">txt</a>)</p>'
                f'<iframe src="{stem}.html" loading="lazy"></iframe></section>'
            )
    index = (
        '<!DOCTYPE html><meta charset="utf-8"><title>Письма Студии</title>'
        "<style>body{font:14px system-ui;margin:24px;background:#eee}section{display:inline-block;margin:0 16px 24px 0;"
        "vertical-align:top}iframe{width:640px;height:900px;border:1px solid #aaa;background:#fff}</style>"
        + "".join(cards)
    )
    (out / "index.html").write_text(index, encoding="utf-8")
    sys.stdout.write(f"{len(cards)} писем в {out}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
