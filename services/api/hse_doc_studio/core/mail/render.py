"""Вёрстка письма: текстовая часть и HTML.

HTML рассчитан на почтовые клиенты: таблицы, стили inline, системные шрифты, без скриптов и картинок
по ссылкам (знак Студии набран текстом). Тёмная тема и узкий экран включаются классами `e-*` в блоке
`<style>` там, где клиент его читает; без него остаются светлые цвета с достаточным контрастом.
"""

from __future__ import annotations

from html import escape

from hse_doc_studio.core.mail.content import MailContent

_SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif"
_MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono','Courier New',monospace"

# Светлые цвета лежат в inline-стилях, тёмные подменяет @media (prefers-color-scheme: dark) по классам.
_STYLE = """
:root{color-scheme:light dark;supported-color-schemes:light dark}
body,table,td,a{-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%}
@media (prefers-color-scheme:dark){
.e-bg{background-color:#0a0a0a !important}
.e-card{background-color:#131313 !important;border-color:#262626 !important}
.e-tx{color:#f0f0f0 !important}
.e-tx2{color:#b8b8b8 !important}
.e-mut{color:#9a9a9a !important}
.e-line{border-color:#262626 !important}
.e-link{color:#5cc8ff !important}
.e-btn{background-color:#3ac7ff !important}
.e-btn-a{color:#0a0a0a !important}
.e-mark{background-color:#3ac7ff !important;color:#0a0a0a !important}
.e-code{background-color:#1a1a1a !important;border-color:#383838 !important;color:#f0f0f0 !important}
.e-note{background-color:#1a1a1a !important;border-color:#3a3a3a !important}
.e-sec{background-color:#2a2110 !important;border-color:#5a4614 !important}
.e-sec-tx{color:#f0dca8 !important}
}
@media only screen and (max-width:620px){
.e-wrap{padding:12px 8px !important}
.e-px{padding-left:20px !important;padding-right:20px !important}
.e-card{width:100% !important;border-radius:10px !important}
.e-btn-wrap{width:100% !important}
.e-btn-a{display:block !important;text-align:center !important;padding:15px 12px !important}
.e-code{font-size:26px !important;letter-spacing:4px !important}
.e-h1{font-size:22px !important}
.e-label{display:block !important;width:auto !important;padding-bottom:0 !important}
.e-value{display:block !important;padding-top:2px !important}
}
""".strip()

_STRONG = "font-weight:600"
_TABLE = 'role="presentation" cellpadding="0" cellspacing="0" border="0"'


def _table(inner: str, *, style: str = "", cls: str = "", width: str = "100%") -> str:
    attrs = f' class="{cls}"' if cls else ""
    return f'<table{attrs} {_TABLE} width="{width}" style="{style}">{inner}</table>'


def _text_block(c: MailContent) -> list[str]:
    out: list[str] = []
    if c.rows:
        out += [""] + [f"{row.label}: {row.value}" for row in c.rows]
    if c.note is not None:
        out += ["", f"{c.note.title}:"]
        out += [f"> {line}" if line else ">" for line in c.note.body.split("\n")]
    if c.code is not None:
        out += ["", f"    {c.code}"]
    href = c.action.href if c.action and c.action.href else c.plain_link
    if href:
        out += ["", f"{c.action.label}:"] if c.action else [""]
        out.append(href)
    if c.expiry:
        out += ["", c.expiry]
    return out


def render_text(c: MailContent) -> str:
    out = [c.brand, "", c.title.plain(), "", c.lead.plain(), *_text_block(c)]
    if c.context:
        out += ["", c.context_title, *(t.plain() for t in c.context)]
    if c.security:
        out += ["", c.security_title, *(t.plain() for t in c.security)]
    out += ["", "--", f"{c.footer_server_label}: {c.server_url}" if c.server_url else c.brand]
    out += [c.footer_recipient, c.footer_auto]
    return "\n".join(out) + "\n"


def _brand(c: MailContent) -> str:
    mark = (
        '<td class="e-mark" width="30" height="30" align="center" valign="middle" bgcolor="#0069b2" '
        'style="width:30px;height:30px;background-color:#0069b2;color:#ffffff;border-radius:8px;'
        f'font:700 16px/30px {_MONO};text-align:center">&sect;</td>'
    )
    name = (
        f'<td style="padding-left:10px;font-family:{_SANS}" valign="middle">'
        '<div class="e-tx" style="font-size:15px;line-height:18px;font-weight:700;color:#0b1024">'
        f"{escape(c.brand)}</div>"
        '<div class="e-mut" style="font-size:12px;line-height:16px;color:#5b6485">'
        f"{escape(c.tagline)}</div></td>"
    )
    return f"<table {_TABLE}><tr>{mark}{name}</tr></table>"


def _rows(c: MailContent) -> str:
    if not c.rows:
        return ""
    label = f"padding:9px 12px 9px 0;font:13px/18px {_SANS};color:#5b6485;border-top:1px solid #e3e8f3"
    value = f"padding:9px 0;font:14px/18px {_SANS};color:#0b1024;border-top:1px solid #e3e8f3;word-break:break-word"
    body = "".join(
        f'<tr><td class="e-label e-mut e-line" width="38%" valign="top" style="{label}">{escape(row.label)}</td>'
        f'<td class="e-value e-tx e-line" valign="top" style="{value}">{escape(row.value)}</td></tr>'
        for row in c.rows
    )
    return _table(body, style="margin:0 0 20px")


def _note(c: MailContent) -> str:
    if c.note is None:
        return ""
    body = escape(c.note.body).replace("\n", "<br>")
    box = "background-color:#eef1f8;border:1px solid #dbe1ec;border-radius:8px;padding:12px 14px"
    inner = (
        f'<tr><td class="e-note" style="{box}">'
        f'<div class="e-mut" style="font:12px/16px {_SANS};color:#5b6485;padding-bottom:4px">'
        f"{escape(c.note.title)}</div>"
        f'<div class="e-tx" style="font:15px/22px {_SANS};color:#0b1024;word-break:break-word">{body}</div>'
        "</td></tr>"
    )
    return _table(inner, style="margin:0 0 20px")


def _code(c: MailContent) -> str:
    if c.code is None:
        return ""
    box = (
        "background-color:#eef1f8;border:1px solid #c2cadd;border-radius:10px;padding:16px 12px;"
        f"font:700 32px/40px {_MONO};letter-spacing:8px;color:#0b1024;text-align:center;word-break:break-all"
    )
    return _table(
        f'<tr><td class="e-code" align="center" style="{box}">{escape(c.code)}</td></tr>', style="margin:0 0 12px"
    )


def _button(c: MailContent) -> str:
    if c.action is None:
        return ""
    style = (
        f"display:inline-block;padding:14px 28px;font:600 16px/20px {_SANS};color:#ffffff;"
        "text-decoration:none;border-radius:8px"
    )
    if c.action.href is None:
        # Письмо из журнала: кнопка того же вида, но без адреса.
        link = f'<span class="e-btn-a" style="{style}">{escape(c.action.label)}</span>'
    else:
        link = (
            f'<a class="e-btn-a" href="{escape(c.action.href, quote=True)}" target="_blank" rel="noopener" '
            f'style="{style}">{escape(c.action.label)}</a>'
        )
    cell = f'<td class="e-btn" bgcolor="#0069b2" style="background-color:#0069b2;border-radius:8px">{link}</td>'
    return _table(f"<tr>{cell}</tr>", cls="e-btn-wrap", style="margin:0 0 12px", width="auto")


def _link_fallback(c: MailContent) -> str:
    if c.action is not None and c.action.href is not None:
        href = escape(c.action.href, quote=True)
        link = f'<a class="e-link" href="{href}" style="color:#0069b2">{escape(c.action.href)}</a>'
    elif c.plain_link is not None:
        link = f'<span class="e-tx">{escape(c.plain_link)}</span>'
    else:
        return ""
    return (
        f'<p class="e-mut" style="margin:0 0 6px;font:13px/19px {_SANS};color:#5b6485">{escape(c.fallback_label)}</p>'
        f'<p style="margin:0 0 12px;font:13px/19px {_MONO};word-break:break-all">{link}</p>'
    )


def _expiry(c: MailContent) -> str:
    if not c.expiry:
        return ""
    return f'<p class="e-tx2" style="margin:0 0 12px;font:14px/21px {_SANS};color:#2e3553">{escape(c.expiry)}</p>'


def _context(c: MailContent) -> str:
    if not c.context:
        return ""
    paragraphs = "".join(
        f'<p class="e-tx2" style="margin:0 0 8px;font:14px/21px {_SANS};color:#2e3553">{t.html(_STRONG)}</p>'
        for t in c.context
    )
    heading = (
        f'<div class="e-mut" style="font:600 12px/16px {_SANS};color:#5b6485;text-transform:uppercase;'
        f'letter-spacing:.06em;padding-bottom:6px">{escape(c.context_title)}</div>'
    )
    return f'<tr><td class="e-px" style="padding:4px 32px 0">{heading}{paragraphs}</td></tr>'


def _security(c: MailContent) -> str:
    if not c.security:
        return ""
    paragraphs = "".join(
        f'<p class="e-sec-tx" style="margin:0 0 6px;font:14px/21px {_SANS};color:#4a3500">{t.html(_STRONG)}</p>'
        for t in c.security
    )
    box = "background-color:#fff7e8;border:1px solid #f0d9a6;border-radius:8px;padding:12px 14px"
    heading = (
        f'<div class="e-sec-tx" style="font:700 12px/16px {_SANS};color:#4a3500;text-transform:uppercase;'
        f'letter-spacing:.06em;padding-bottom:6px">{escape(c.security_title)}</div>'
    )
    inner = f'<tr><td class="e-sec" style="{box}">{heading}{paragraphs}</td></tr>'
    return f'<tr><td class="e-px" style="padding:20px 32px 0">{_table(inner)}</td></tr>'


def _footer(c: MailContent) -> str:
    server = ""
    if c.server_url:
        href = escape(c.server_url, quote=True)
        server = (
            f'{escape(c.footer_server_label)}: <a class="e-link" href="{href}" '
            f'style="color:#0069b2;text-decoration:underline">{escape(c.server_display)}</a><br>'
        )
    return (
        '<tr><td class="e-px" style="padding:24px 32px 28px">'
        f'<p class="e-mut" style="margin:0;font:12px/18px {_SANS};color:#5b6485">'
        f"{server}{escape(c.footer_recipient)}<br>{escape(c.footer_auto)}</p></td></tr>"
    )


_HIDDEN = "display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;opacity:0;overflow:hidden"
_CARD = "width:560px;max-width:100%;background-color:#ffffff;border:1px solid #dbe1ec;border-radius:14px"


def render_html(c: MailContent) -> str:
    main = "".join((_rows(c), _note(c), _code(c), _button(c), _link_fallback(c), _expiry(c)))
    h1 = (
        f'<h1 class="e-h1 e-tx" style="margin:0 0 10px;font:700 24px/30px {_SANS};letter-spacing:-.01em;'
        f'color:#0b1024">{escape(c.title.plain())}</h1>'
    )
    lead = f'<p class="e-tx2" style="margin:0 0 20px;font:16px/24px {_SANS};color:#2e3553">{c.lead.html(_STRONG)}</p>'
    card = (
        f'<tr><td class="e-px" style="padding:24px 32px 4px">{_brand(c)}</td></tr>'
        f'<tr><td class="e-px" style="padding:20px 32px 0">{h1}{lead}{main}</td></tr>'
        f"{_context(c)}{_security(c)}{_footer(c)}"
    )
    page = _table(
        f'<tr><td class="e-wrap" align="center" style="padding:28px 12px">'
        f"{_table(card, cls='e-card', style=_CARD, width='560')}</td></tr>",
        cls="e-bg",
        style="background-color:#f3f5fb",
    )
    return (
        f'<!DOCTYPE html>\n<html lang="{c.lang.value}">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        '<meta name="color-scheme" content="light dark">\n'
        '<meta name="supported-color-schemes" content="light dark">\n'
        f"<title>{escape(c.subject)}</title>\n<style>{_STYLE}</style>\n</head>\n"
        f'<body class="e-bg" style="margin:0;padding:0;background-color:#f3f5fb">\n'
        f'<div style="{_HIDDEN}">{escape(c.preheader.plain())}</div>\n{page}\n</body>\n</html>\n'
    )
