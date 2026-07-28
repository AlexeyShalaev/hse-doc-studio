#!/usr/bin/env python3
"""Скопировать общие ассеты сайта из docs/ru в docs/en перед сборкой английской версии.

docs/ru — единственный источник правды для стилей, скриптов, шрифтов, бренда и
скриншотов. Английское дерево docs/en содержит только переведённые .md; всё
остальное приезжает сюда этим скриптом и перечислено в docs/en/.gitignore.
Сниппеты не копируются: оба конфига читают их из docs/ru/_snippets через base_path.

Только stdlib — скрипт запускается в CI без venv.

Использование:
    python scripts/docs/sync_shared.py
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SRC = ROOT / "docs" / "ru"
DST = ROOT / "docs" / "en"

# Каталоги, общие для обеих языковых сборок.
SHARED_DIRS = ("stylesheets", "javascripts", "assets")


def sync() -> int:
    if not SRC.is_dir():
        print("error: docs/ru not found", file=sys.stderr)  # noqa: T201 — CLI-скрипт
        return 1
    DST.mkdir(exist_ok=True)
    for name in SHARED_DIRS:
        src_dir = SRC / name
        dst_dir = DST / name
        if not src_dir.is_dir():
            continue
        if dst_dir.exists():
            shutil.rmtree(dst_dir)
        shutil.copytree(src_dir, dst_dir)
        files = sum(1 for path in dst_dir.rglob("*") if path.is_file())
        print(f"synced docs/en/{name}/ ({files} files)")  # noqa: T201 — CLI-скрипт
    return 0


if __name__ == "__main__":
    sys.exit(sync())
