"""Копия схем пака в пакете совпадает с контрактом: CLI в образе проверяет паки теми же схемами."""

from __future__ import annotations

from pathlib import Path

from hse_doc_studio.infra.pack_studio.pack_schemas import SCHEMAS_DIR

CONTRACT_DIR = Path(__file__).resolve().parents[6] / "contracts" / "pack"


def test_package_schemas_match_the_contract() -> None:
    contract = {p.name: p.read_bytes() for p in CONTRACT_DIR.glob("*.schema.json")}
    copy = {p.name: p.read_bytes() for p in SCHEMAS_DIR.glob("*.schema.json")}

    assert contract, CONTRACT_DIR
    assert copy == contract, (
        "схемы в hse_doc_studio/infra/pack_studio/schemas/ разошлись с contracts/pack/: "
        "скопируйте contracts/pack/*.schema.json"
    )
