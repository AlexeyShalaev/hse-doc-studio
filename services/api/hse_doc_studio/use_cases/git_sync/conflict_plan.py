"""План слияния двух коммитов хранилища: общий для синхронизации и для экрана конфликтов.

План строится только по объектам хранилища, без сети и без рабочего дерева. Один и тот же план нужен
синхронизации (применить или остановиться на конфликтах) и экрану конфликтов (показать, принять черновик,
решить), поэтому он собирается в одном месте. План неизменяем и определяется тройкой коммитов, поэтому
несколько последних держатся в памяти: экран читает его десятки раз подряд.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

from hse_doc_studio.core.git_sync.entities import TreeEntry
from hse_doc_studio.core.git_sync.error_messages import git_error
from hse_doc_studio.core.git_sync.errors import GitErrorCode
from hse_doc_studio.core.git_sync.incoming import ensure_incoming_fits
from hse_doc_studio.core.git_sync.merge.entities import MergePlan
from hse_doc_studio.core.git_sync.merge.paths import comparison_key, is_safe_entry
from hse_doc_studio.core.git_sync.merge.planner import MergeInput, plan_merge
from hse_doc_studio.core.git_sync.policy import GitSyncPolicy
from hse_doc_studio.core.git_sync.protocols import (
    IFileMergeStrategy,
    IGitMergeEngine,
    IGitRepoReader,
    MergeMeta,
)
from hse_doc_studio.core.template_update.text import is_binary

_STUDIO_PREFIX: Final = ".hse-studio/"
_CACHE_PLANS: Final = 4
# Планы тяжелее не кладутся в память: бинарные файлы проекта могут занимать сотни мегабайт.
_CACHE_BYTES: Final = 32_000_000

_CacheKey = tuple[str, str, str, bool]


class ConflictPlanner:
    def __init__(
        self, *, reader: IGitRepoReader, engine: IGitMergeEngine, structured: IFileMergeStrategy, policy: GitSyncPolicy
    ) -> None:
        self._policy = policy
        self._reader = reader
        self._engine = engine
        self._structured = structured
        self._cache: OrderedDict[_CacheKey, MergePlan] = OrderedDict()
        self._lock = threading.Lock()

    def plan(self, folder: Path, ours: str, theirs: str, *, adopted_unrelated: bool) -> MergePlan:
        """План слияния `theirs` в `ours`. Без общей истории нужно согласие человека (`adopted_unrelated`)."""
        key = (str(folder), ours, theirs, adopted_unrelated)
        with self._lock:
            cached = self._cache.get(key)
            if cached is not None:
                self._cache.move_to_end(key)
                return cached
        plan = self._build(folder, ours, theirs, adopted_unrelated=adopted_unrelated)
        if _weight(plan) <= _CACHE_BYTES:
            with self._lock:
                self._cache[key] = plan
                while len(self._cache) > _CACHE_PLANS:
                    self._cache.popitem(last=False)
        return plan

    def _build(self, folder: Path, ours: str, theirs: str, *, adopted_unrelated: bool) -> MergePlan:
        base = self._reader.merge_base(folder, ours, theirs)
        if base is None and not adopted_unrelated:
            raise git_error(GitErrorCode.unrelated_histories, can_adopt=True)
        theirs_entries = {entry.path: entry for entry in self._reader.tree_entries(folder, theirs)}
        paths = self._merge_paths(folder, base, ours, theirs, theirs_entries)
        # Размеры известны из дерева: гигантский блоб отвергается до того, как его прочтут в память.
        ensure_incoming_fits((theirs_entries[path] for path in paths if path in theirs_entries), self._policy)
        merge_input = self._merge_input(folder, base, ours, theirs, paths, theirs_entries)
        return plan_merge(merge_input, self._engine, self._structured)

    def _merge_paths(
        self, folder: Path, base: str | None, ours: str, theirs: str, theirs_entries: Mapping[str, TreeEntry]
    ) -> list[str]:
        """Пути, которые изменила чужая сторона: для остальных слияние ничего не меняет, читать их незачем.

        К ним добавляются мои пути, совпадающие с ними по имени без учёта регистра и NFC: иначе столкновение
        имён на регистронезависимых файловых системах планировщик не увидел бы.
        """
        if base is None:
            paths = set(theirs_entries)
        else:
            paths = {path for _, path in self._reader.changed_paths(folder, base, theirs)}
        mine: dict[str, list[str]] = {}
        for entry in self._reader.tree_entries(folder, ours):
            mine.setdefault(comparison_key(entry.path), []).append(entry.path)
        for path in tuple(paths):
            paths.update(mine.get(comparison_key(path), ()))
        return sorted(paths)

    def _merge_input(
        self,
        folder: Path,
        base: str | None,
        ours: str,
        theirs: str,
        paths: Sequence[str],
        theirs_entries: Mapping[str, TreeEntry],
    ) -> MergeInput:
        base_files = _present(self._reader.read_files(folder, base, paths)) if base else {}
        ours_files = _present(self._reader.read_files(folder, ours, paths))
        theirs_files = _present(self._reader.read_files(folder, theirs, paths))
        blocked = frozenset(
            path for path in paths if path in theirs_entries and not is_safe_entry(path, theirs_entries[path].mode)
        )
        return MergeInput(
            base=base_files,
            ours=ours_files,
            theirs=theirs_files,
            base_commit=base,
            theirs_commit=theirs,
            meta=self._meta(folder, base, ours, theirs, base_files, ours_files, theirs_files),
            blocked=blocked,
        )

    def _meta(
        self,
        folder: Path,
        base: str | None,
        ours: str,
        theirs: str,
        base_files: Mapping[str, bytes],
        ours_files: Mapping[str, bytes],
        theirs_files: Mapping[str, bytes],
    ) -> dict[str, MergeMeta]:
        """Кто правил файл позже: нужно бинарникам и файлам состояния, где побеждает более новая правка."""
        both = {path for path in theirs_files.keys() & ours_files.keys() if base_files.get(path) != ours_files[path]}
        meta: dict[str, MergeMeta] = {}
        for path in sorted(both):
            if not _needs_stamps(path, base_files.get(path), ours_files[path], theirs_files[path]):
                continue
            mine = self._reader.path_stamp(folder, ours, path, exclude_reachable_from=base)
            other = self._reader.path_stamp(folder, theirs, path, exclude_reachable_from=base)
            meta[path] = MergeMeta(
                ours_changed_at=mine.committed_at if mine else None,
                theirs_changed_at=other.committed_at if other else None,
                ours_commit=mine.sha if mine else None,
                theirs_commit=other.sha if other else None,
            )
        return meta


def _present(files: Mapping[str, bytes | None]) -> dict[str, bytes]:
    return {path: data for path, data in files.items() if data is not None}


def _needs_stamps(path: str, *contents: bytes | None) -> bool:
    if path.lower().endswith(".pdf") or is_binary(path, *contents):
        return True
    return path.startswith(_STUDIO_PREFIX) and path.endswith(".json")


def _weight(plan: MergePlan) -> int:
    return sum(
        len(data or b"") for op in plan.ops for data in (op.base, op.ours, op.theirs, op.merged, op.copy_content)
    )
