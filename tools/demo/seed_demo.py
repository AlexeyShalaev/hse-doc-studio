#!/usr/bin/env python3
"""Сеет ИЗОЛИРОВАННЫЙ демо-стенд для съёмки скриншотов и ролика.

Реальные данные (~/.config/hse-studio) не затрагиваются: собирается отдельный
data dir + копии синтетических проектов из QA-матрицы (hse-rules-examples —
соседний репозиторий воркспейса; путь переопределяется через DEMO_SRC).

Матрица уже целиком синтетическая: автор «Шалаев Алексей Дмитриевич»,
руководитель «Петров Пётр Петрович», подписи — нарисованные закорючки.
Единственная правка: группа БПИ227 → БПИ222 (персона примеров сайта).

Идемпотентно: существующий стенд не пересеивается (RESEED=1 — пересоздать).

Использование:  python tools/demo/seed_demo.py
Выход:          tools/demo/.build/demo/{data,projects,manifest.json}
"""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import sys
from pathlib import Path


def _rmtree(path: Path) -> None:
    """rmtree, переживающий read-only объекты git на Windows."""

    def _onexc(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)

    shutil.rmtree(path, onexc=_onexc)

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
BUILD = HERE / ".build" / "demo"
DATA = BUILD / "data"

# Папки проектов — в «человеческом» месте: путь виден в кадрах (карточки проектов,
# «Папка проекта»), служебный tools/demo/.build там выглядел бы как леса стройки.
DEMO_HOME = Path(os.environ.get("DEMO_HOME") or Path.home() / "Documents" / "hse-studio-demo")
MARKER = DEMO_HOME / ".hse-studio-demo-stand"  # защита: удаляем только СВОЮ папку

SRC = Path(os.environ.get("DEMO_SRC") or REPO.parent / "hse-rules-examples" / "test-projects")

# Solo-проекты (без соавторов): welcome-список выглядит живым, «Иванов» в кадр не попадает.
# Ключ = имя папки в DEMO_HOME (короткое, «студенческое»).
PICKS = {
    "ru": ("vkr", "vkr-ru-project-solo"),
    "en": ("vkr-en", "vkr-en-project-solo"),
    "coursework": ("coursework", "coursework-ru-research-solo"),
    "pp": ("project-proposal", "pp-en-project-solo"),
}

GROUP_FROM, GROUP_TO = "БПИ227", "БПИ222"


def _patch_group(node):
    """Рекурсивно заменяет группу в паспорте проекта (authors[].group, meta…)."""
    if isinstance(node, dict):
        return {k: _patch_group(v) for k, v in node.items()}
    if isinstance(node, list):
        return [_patch_group(v) for v in node]
    if isinstance(node, str):
        return node.replace(GROUP_FROM, GROUP_TO)
    return node


def _inject_findings(tex_path: Path) -> None:
    """Пара нарочных огрехов типографики в русском тезисе: прямые кавычки и дефис
    вместо тире. После пересборки (prep.mjs) экран «Замечания» показывает живые
    находки, а не стерильные 100% — честный кадр «замечания приходят на поля»."""
    if not tex_path.is_file():
        return
    text = tex_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    quoted = re.compile(r"«([^«»]{3,40})»")
    done_q = done_d = False
    for i, line in enumerate(lines):
        if line.lstrip().startswith(("%", "\\")):
            continue
        if not done_q:
            m = quoted.search(line)
            if m:
                lines[i] = line[: m.start()] + f'"{m.group(1)}"' + line[m.end():]
                done_q = True
                continue
        if not done_d and " — " in line:
            lines[i] = line.replace(" — ", " - ", 1)
            done_d = True
        if done_q and done_d:
            break
    tex_path.write_text("\n".join(lines) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")


def main() -> int:
    # консоль Windows по умолчанию cp1251 — печатаем UTF-8 явно
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if BUILD.exists() and MARKER.exists() and os.environ.get("RESEED") != "1":
        print(f"demo stand exists: {BUILD} + {DEMO_HOME} (RESEED=1 to recreate)")
        return 0
    if not SRC.is_dir():
        print(f"error: source projects not found: {SRC}", file=sys.stderr)
        print("hint: clone hse-rules-examples next to hse-doc-studio or set DEMO_SRC", file=sys.stderr)
        return 1

    if BUILD.exists():
        _rmtree(BUILD)
    if DEMO_HOME.exists():
        if not MARKER.exists():
            print(f"error: {DEMO_HOME} exists but was not created by this script — refusing to delete", file=sys.stderr)
            return 1
        _rmtree(DEMO_HOME)
    DATA.mkdir(parents=True)
    DEMO_HOME.mkdir(parents=True)
    MARKER.write_text("created by hse-doc-studio tools/demo/seed_demo.py\n", encoding="utf-8")

    manifest: dict[str, dict[str, str]] = {}
    registered: list[str] = []

    for key, (folder, name) in PICKS.items():
        src = SRC / name
        dst = DEMO_HOME / folder
        print(f"→ copy {name} → {dst} …")
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns(".build"))

        passport_path = dst / ".hse-studio" / "project.json"
        passport = json.loads(passport_path.read_text(encoding="utf-8"))
        passport = _patch_group(passport)
        passport_path.write_text(
            json.dumps(passport, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # косметика: устаревший абсолютный worktree в конфиге изолированного git
        git_config = dst / ".hse-studio" / "git" / "config"
        if git_config.is_file():
            lines = []
            for line in git_config.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith("worktree ="):
                    line = f"\tworktree = {dst.as_posix()}"
                lines.append(line)
            git_config.write_text("\n".join(lines) + "\n", encoding="utf-8")

        if key == "ru":
            _inject_findings(dst / "thesis" / "thesis.tex")

        doc_ids = [d.get("id") for d in passport.get("documents") or []]
        manifest[key] = {
            "path": str(dst),
            "id": passport["id"],
            "name": passport.get("name") or name,
            "docs": ",".join(doc_ids),
        }
        registered.append(str(dst))

    (DATA / "projects.json").write_text(
        json.dumps(registered, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (BUILD / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"SEED_DONE → {BUILD}")
    for key, info in manifest.items():
        print(f"  {key}: {info['id']}  {info['name']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
