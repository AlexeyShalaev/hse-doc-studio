"""Снимок живых ответов API для контракта git-sync: проверка схемами, нормализация и сравнение формы.

Тест сценария собирает настоящие ответы двух Студий, каждый проходит строгую модель из api/schemas/git_sync.py, затем
нормализуется (идентификаторы, хеши, даты и пути заменяются стабильными значениями) и сверяется с файлом в
contracts/git-sync/live/<Схема>/<вариант>.json. Те же файлы разбирает zod-тест фронтенда, поэтому ответ настоящего
бэкенда должен проходить обе стороны. Сравнивается форма (ключи и типы), а не значения: значения зависят от пакета
шаблонов и от часов машины, форма ловит именно расхождение контракта. Обновить файлы: HSE_UPDATE_LIVE=1.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

UPDATE_ENV = "HSE_UPDATE_LIVE"

# Идентификаторы заменяются порядковыми номерами по первому появлению: порядок ответов сценария один и тот же.
_NUMBERED: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "uuid",
        re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"),
        "00000000-0000-4000-8000-{:012d}",
    ),
    ("sha", re.compile(r"^[0-9a-f]{40}$"), "{:040x}"),
    ("operation", re.compile(r"^op_[0-9a-f]{12}$"), "op_{:012x}"),
    ("token", re.compile(r"^[0-9a-f]{12}$"), "{:012x}"),
)
_SHA64 = re.compile(r"^[0-9a-f]{64}$")
_SHORT_IN_TEXT = re.compile(r"\([0-9a-f]{7}\)")
_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}")
_CONFLICT_COPY = re.compile(r"\.conflict-[0-9a-f]{7}")
_FIXED_TIME = "2030-01-01T00:00:00Z"
# Размеры и счётчики файлов зависят от пакета шаблонов: их значение не контракт.
_VOLATILE_INTS = frozenset({"bytes", "size", "files", "commits"})


def live_dir(repo: Path) -> Path:
    return repo / "contracts" / "git-sync" / "live"


@dataclass
class Capture:
    """Нормализованные ответы сценария: (схема, вариант) -> тело."""

    root: str
    items: dict[tuple[str, str], Any] = field(default_factory=dict)
    _numbers: dict[str, dict[str, str]] = field(default_factory=dict)

    def add(self, schema_name: str, name: str, body: Any, schemas: dict[str, Any]) -> None:
        """Проверить ответ строгой моделью и сохранить нормализованную копию."""
        key = (schema_name, name)
        assert key not in self.items, f"дважды снят ответ {schema_name}/{name}"
        adapter = TypeAdapter(schemas[schema_name])
        model = adapter.validate_python(body)
        # В ответе обязаны быть все поля модели (null тоже); тела ошибок несут только поля своего кода.
        dumped = adapter.dump_python(model, mode="json", exclude_unset=schema_name == "GitErrorBody")
        assert dumped == body, f"{schema_name}/{name}: ответ расходится с моделью"
        self.items[key] = self._normalise(body, None)

    # --- нормализация --------------------------------------------------------------------------------------------

    def _normalise(self, value: Any, key: str | None) -> Any:
        if isinstance(value, dict):
            return {k: self._normalise(v, k) for k, v in value.items()}
        if isinstance(value, list):
            return [self._normalise(v, key) for v in value]
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, int):
            return 1000 if key in _VOLATILE_INTS else value
        return self._text(value, key) if isinstance(value, str) else value

    def _text(self, value: str, key: str | None) -> str:
        for kind, pattern, template in _NUMBERED:
            if pattern.match(value):
                numbers = self._numbers.setdefault(kind, {})
                return numbers.setdefault(value, template.format(len(numbers) + 1))
        if _SHA64.match(value):
            return "f" * 64
        if _ISO.match(value):
            return _FIXED_TIME
        if key == "short_id":
            full = next((new for old, new in self._numbers.get("sha", {}).items() if old.startswith(value)), None)
            return full[:7] if full else value
        text = _CONFLICT_COPY.sub(".conflict-0000000", value.replace(self.root, "/studio"))
        return _SHORT_IN_TEXT.sub("(0000000)", text)


# --- форма ------------------------------------------------------------------------------------------------------


def skeleton(value: Any) -> Any:
    """Ключи и типы без значений; элементы списка схлопнуты до уникальных форм."""
    if isinstance(value, dict):
        return {k: skeleton(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        shapes = {json.dumps(skeleton(v), sort_keys=True, ensure_ascii=False) for v in value}
        return [json.loads(shape) for shape in sorted(shapes)]
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int | float):
        return "number"
    return "str"


def write_snapshots(repo: Path, items: dict[tuple[str, str], Any]) -> None:
    base = live_dir(repo)
    for stale in base.glob("*/*.json"):
        stale.unlink()
    for (schema_name, name), body in items.items():
        target = base / schema_name / f"{name}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def compare_snapshots(repo: Path, items: dict[tuple[str, str], Any]) -> list[str]:
    """Расхождения живых ответов со снимками в contracts/git-sync/live; пустой список значит «совпало»."""
    base = live_dir(repo)
    problems: list[str] = []
    committed = {(path.parent.name, path.stem): path for path in base.glob("*/*.json")}
    for key, body in sorted(items.items()):
        path = committed.pop(key, None)
        if path is None:
            problems.append(f"нет снимка {key[0]}/{key[1]}")
            continue
        if skeleton(json.loads(path.read_text(encoding="utf-8"))) != skeleton(body):
            problems.append(f"форма ответа {key[0]}/{key[1]} изменилась")
    problems.extend(f"снимок {schema_name}/{name} больше не снимается" for schema_name, name in sorted(committed))
    return problems


def update_requested() -> bool:
    return os.environ.get(UPDATE_ENV) == "1"
