"""Хук `push-to-checkout`: принятый коммит переносится в рабочую папку проекта.

Стор лежит в `<папка>/.hse-studio/git`, и встроенный `updateInstead` git сравнивал бы с самим стором как с
рабочим деревом. Хук делает то же явно: двусторонний `read-tree -u -m HEAD <new>` над настоящей папкой; если
он не проходит (в папке правка того же файла), git отклоняет обновление ветки целиком.
"""

from __future__ import annotations

import os
import subprocess
import sys

_DROP = ("GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_DIR", "GIT_PREFIX")


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        return 1
    env = {k: v for k, v in os.environ.items() if k not in _DROP}
    result = subprocess.run(  # noqa: S603 — аргументы собраны здесь
        [  # noqa: S607
            "git",
            "-c",
            "core.fsmonitor=false",
            "--git-dir",
            env["HSE_GIT_DIR"],
            "--work-tree",
            env["HSE_WORK_TREE"],
            "read-tree",
            "-u",
            "-m",
            "HEAD",
            argv[0],
        ],
        env=env,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(result.stderr.decode(errors="replace"))
    return result.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
