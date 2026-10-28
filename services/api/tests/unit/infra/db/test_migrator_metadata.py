from __future__ import annotations

import subprocess
import sys


def test__migrator_import__registers_orm_tables_in_metadata() -> None:
    """`db check` в свежем процессе CLI иначе сравнивает пустые метаданные и видит дрейф в каждой таблице."""
    code = "import hse_doc_studio.infra.db.migrator as m; print(len(m.Base.metadata.tables))"

    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True).stdout

    assert int(out) > 0
