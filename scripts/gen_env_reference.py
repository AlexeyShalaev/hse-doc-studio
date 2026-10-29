#!/usr/bin/env python3
"""Сгенерировать справочник переменных окружения (docs/ru/deploy/env-reference.md) из Settings.

Единственный источник правды: pydantic `Settings` бэкенда (имена, типы, значения по умолчанию,
`description` полей). Файл производный: не правьте его руками, правьте поле и запускайте скрипт.
Поле без `description` роняет и генерацию, и `--check`: новую настройку нельзя добавить молча.

Секреты (`SecretStr`, а также перечисленные в `EXTRA_SECRETS`) помечены, значение по умолчанию
для них не печатается. Скрипту нужен venv бэкенда, поэтому запускать из `services/api`:

    uv run --frozen --all-extras python ../../scripts/gen_env_reference.py           # перезаписать файл
    uv run --frozen --all-extras python ../../scripts/gen_env_reference.py --check   # только проверить
"""

from __future__ import annotations

import argparse
import re
import sys
import types
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Union, get_args, get_origin

from pydantic import BaseModel, SecretStr
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = ROOT / "docs" / "ru" / "deploy" / "env-reference.md"
API_ROOT = ROOT / "services" / "api"

# Группы, которые имеют смысл только на общем сервере; остальное работает в обоих режимах.
SERVER_GROUPS = frozenset({"db", "s3", "auth", "mail", "admin", "egress", "rate_limit", "observability"})
# Секреты, не оформленные как SecretStr (в значении может быть пароль).
EXTRA_SECRETS = frozenset({"DB__DSN"})
# Значения по умолчанию, зависящие от места запуска: в справочнике они должны быть одинаковыми везде.
DEFAULT_OVERRIDES = {
    "DATA_DIR": "`~/.config/hse-studio`",
    "PACKS_DIR": "каталог `packs` монорепы, в образе `/app/packs`",
    "RELEASE_NOTES_FILE": "`release-notes.json` монорепы, в образе `/app/release-notes.json`",
}
PREFIX = "HSE_STUDIO__"
_LIST_PREVIEW = 3


class Row:
    __slots__ = ("default", "description", "mode", "name", "secret", "type_")

    def __init__(self, name: str, type_: str, default: str, description: str, mode: str, *, secret: bool) -> None:
        self.name = name
        self.type_ = type_
        self.default = default
        self.description = description
        self.mode = mode
        self.secret = secret


def _model_class(annotation: Any) -> type[BaseModel] | None:
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def _is_secret(annotation: Any) -> bool:
    if annotation is SecretStr:
        return True
    return any(_is_secret(arg) for arg in get_args(annotation))


def _type_name(annotation: Any) -> str:
    origin = get_origin(annotation)
    if origin in (Union, types.UnionType):
        parts = [a for a in get_args(annotation) if a is not type(None)]
        return " | ".join(_type_name(a) for a in parts)
    if origin is Literal:
        return " / ".join(str(a) for a in get_args(annotation))
    if origin is not None:
        args = get_args(annotation)
        inner = ", ".join(_type_name(a) for a in args)
        return f"{getattr(origin, '__name__', str(origin))}[{inner}]"
    if isinstance(annotation, type):
        if issubclass(annotation, Enum):
            return " / ".join(str(m.value) for m in annotation)
        if annotation is SecretStr:
            return "str"
        return annotation.__name__
    return str(annotation)


def _scalar(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _default_text(field: FieldInfo) -> str:
    value = field.get_default(call_default_factory=True)
    if value is PydanticUndefined or value is None:
        return "не задано"
    if isinstance(value, (list, tuple, set, frozenset)):
        items = list(value)
        if not items:
            return "пусто"
        if any(isinstance(i, BaseModel) for i in items):
            return f"встроенный список ({len(items)})"
        shown = ", ".join(f"`{_scalar(i)}`" for i in items[:_LIST_PREVIEW])
        return shown if len(items) <= _LIST_PREVIEW else f"{shown}, … (всего {len(items)})"
    if value == "":
        return "пусто"
    return f"`{_scalar(value)}`"


def _cell(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().replace("|", "\\|")


def collect(model: type[BaseModel], path: tuple[str, ...] = ()) -> tuple[list[Row], list[str]]:
    """Плоский список полей (вложенные модели через `__`) и имена полей без description."""
    rows: list[Row] = []
    missing: list[str] = []
    for name, field in model.model_fields.items():
        nested = _model_class(field.annotation)
        if nested is not None:
            sub_rows, sub_missing = collect(nested, (*path, name))
            rows.extend(sub_rows)
            missing.extend(sub_missing)
            continue
        suffix = "__".join(p.upper() for p in (*path, name))
        env = PREFIX + suffix
        if not (field.description or "").strip():
            missing.append(env)
            continue
        secret = _is_secret(field.annotation) or suffix in EXTRA_SECRETS
        if secret:
            default = "секрет, не печатается"
        else:
            default = DEFAULT_OVERRIDES.get(suffix) or _default_text(field)
        mode = "server" if path and path[0] in SERVER_GROUPS else "оба"
        rows.append(Row(env, _type_name(field.annotation), default, field.description or "", mode, secret=secret))
    return rows, missing


def render(model: type[BaseModel]) -> str:
    rows, missing = collect(model)
    if missing:
        msg = "У полей Settings нет description:\n  " + "\n  ".join(missing)
        raise SystemExit(msg)
    lines = [
        "---",
        "title: Переменные окружения",
        "description: Все настройки бэкенда, которые задаются переменными окружения HSE_STUDIO__*.",
        "tags:",
        "  - Развёртывание",
        "  - Справочник",
        "---",
        "",
        "<!-- Файл сгенерирован scripts/gen_env_reference.py из pydantic Settings. Не правьте его руками. -->",
        "",
        "# Переменные окружения",
        "",
        f"Имя переменной строится из префикса `{PREFIX}` и пути поля; вложенные группы разделяются `__`, "
        "регистр не важен. Значения можно положить и в файл `.env`.",
        "",
        "Режим «server» означает, что настройка действует только на общем сервере, «оба» "
        "значит, что она работает и в локальной установке. Секреты помечены 🔒, их значения "
        "по умолчанию не показываются: задавайте их через окружение или docker secrets.",
        "",
        "| Переменная | Тип | По умолчанию | Режим | Описание |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        name = f"`{row.name}`" + (" 🔒" if row.secret else "")
        lines.append(
            f"| {name} | {_cell(row.type_)} | {_cell(row.default)} | {row.mode} | {_cell(row.description)} |"
        )
    lines.append("")
    return "\n".join(lines)


def _load_settings_class() -> type[BaseModel]:
    sys.path.insert(0, str(API_ROOT))
    from hse_doc_studio.api.config.settings import Settings  # noqa: PLC0415

    return Settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="ничего не писать, упасть, если файл устарел")
    parser.add_argument("--out", type=Path, default=OUT_PATH, help="куда писать (по умолчанию docs/ru/deploy)")
    args = parser.parse_args(argv)

    text = render(_load_settings_class())
    out: Path = args.out
    if args.check:
        current = out.read_text(encoding="utf-8") if out.is_file() else None
        if current != text:
            print(
                f"{out} устарел или отсутствует: запустите scripts/gen_env_reference.py из services/api",
                file=sys.stderr,
            )
            return 1
        print("env-reference актуален")
        return 0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(f"записан {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
