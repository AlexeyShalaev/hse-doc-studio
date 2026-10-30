"""Генератор справочника env: имена, секреты, проверка актуальности и описаний."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from pydantic import BaseModel, Field, SecretStr

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "gen_env_reference.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_env_reference", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = _load()


class _Inner(BaseModel):
    token: SecretStr | None = Field(default=SecretStr("hunter2"), description="Token.")
    retries: int = Field(default=3, description="How many\ntimes | ok.")


class _Model(BaseModel):
    name: str = Field(default="x", description="Name.")
    db: _Inner = Field(default_factory=_Inner)


class _NoDescription(BaseModel):
    bare: int = 1


def test_names_types_defaults() -> None:
    text = gen.render(_Model)
    assert "| `HSE_STUDIO__NAME` | str | `x` | оба | Name. |" in text
    assert "`HSE_STUDIO__DB__RETRIES` | int | `3` | server | How many times \\| ok. |" in text


def test_secret_default_is_not_printed() -> None:
    text = gen.render(_Model)
    assert "hunter2" not in text
    assert "`HSE_STUDIO__DB__TOKEN` 🔒" in text


def test_field_without_description_fails() -> None:
    with pytest.raises(SystemExit, match="HSE_STUDIO__BARE"):
        gen.render(_NoDescription)


def test_check_fails_on_stale_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gen, "_load_settings_class", lambda: _Model)
    out = tmp_path / "env.md"
    assert gen.main(["--check", "--out", str(out)]) == 1
    assert gen.main(["--out", str(out)]) == 0
    assert gen.main(["--check", "--out", str(out)]) == 0
    out.write_text(out.read_text(encoding="utf-8") + "stale\n", encoding="utf-8")
    assert gen.main(["--check", "--out", str(out)]) == 1


def test_committed_reference_matches_settings() -> None:
    assert gen.main(["--check"]) == 0
