"""Работа с каталогом шрифтов ХОСТА — исполняется ВНУТРИ одноразового контейнера.

Отдельный модуль, а не функция: контейнер, которому смонтировали каталог шрифтов
пользователя, запускает его как `python -m`. Образ у сайдкара наш собственный,
поэтому здесь доступен разбор sfnt-таблицы имён — человек увидит «Times New
Roman», а не «times.ttf».

Два режима, оба печатают результат в stdout:

* `scan <точка монтирования>` — JSON со списком файлов и семейств;
* `read <точка монтирования> <относительный путь>` — содержимое файла в base64.

Пути наружу отдаются ОТНОСИТЕЛЬНЫЕ. Внутри контейнера каталог называется иначе,
чем на хосте, и склеивать хостовое имя обязан вызывающий — он единственный, кто
знает обе стороны маунта.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path, PurePosixPath

from hse_doc_studio.infra.fonts.font_names import read_family_name

FONT_EXTENSIONS: frozenset[str] = frozenset({".ttf", ".otf", ".ttc"})
_MAX_FILES = 4000


def scan(root: Path, limit: int = _MAX_FILES) -> list[dict[str, str]]:
    """Шрифты каталога вместе с семействами.

    Дедупликация по имени файла в НИЖНЕМ регистре: Windows держит один и тот же
    шрифт и в системном каталоге, и в пользовательском, показывать его дважды
    незачем.
    """
    found: dict[str, dict[str, str]] = {}
    try:
        entries = sorted(root.rglob("*"))
    except OSError:
        return []
    for path in entries:
        if len(found) >= limit:
            break
        key = path.name.lower()
        if key in found or path.suffix.lower() not in FONT_EXTENSIONS:
            continue
        try:
            if not path.is_file():
                continue
        except OSError:
            continue
        found[key] = {
            "name": path.name,
            "rel": str(PurePosixPath(path.relative_to(root))),
            "family": read_family_name(path) or "",
        }
    return sorted(found.values(), key=lambda f: f["name"].lower())


def read(root: Path, relative: str) -> bytes:
    """Содержимое файла шрифта. Выход за пределы маунта запрещён."""
    target = (root / relative).resolve()
    if not target.is_relative_to(root.resolve()):
        msg = f"path escapes the mounted font directory: {relative!r}"
        raise ValueError(msg)
    if target.suffix.lower() not in FONT_EXTENSIONS:
        msg = f"not a font file: {relative!r}"
        raise ValueError(msg)
    return target.read_bytes()


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    minimal = 2
    if len(args) < minimal:
        print("usage: host_scan (scan <mount>|read <mount> <rel>)", file=sys.stderr)  # noqa: T201
        return 2
    mode, mount = args[0], Path(args[1])
    if mode == "scan":
        print(json.dumps(scan(mount), ensure_ascii=False))  # noqa: T201 — stdout ЕСТЬ результат
        return 0
    if mode == "read" and len(args) > minimal:
        print(base64.b64encode(read(mount, args[2])).decode("ascii"))  # noqa: T201
        return 0
    print(f"unknown mode: {mode!r}", file=sys.stderr)  # noqa: T201
    return 2


if __name__ == "__main__":
    sys.exit(main())
