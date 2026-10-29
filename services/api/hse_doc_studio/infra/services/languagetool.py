"""LanguageTool за пулом: прокси с кэшем абзацев и реализации порта ILanguageCheckService для сервера."""

from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx

from hse_doc_studio.infra.services.pool import ServicePool

_PARAGRAPH_SPLIT = re.compile(r"(?<=\n)(?=[ \t]*\n)")
_HEALTH_PATH = "/v2/languages"


class TextTooLargeError(ValueError):
    """Текст длиннее лимита прокси."""


def split_paragraphs(text: str) -> list[str]:
    """Кусочки идут подряд без потерь: `''.join(parts) == text`, границы на пустых строках."""
    parts = [p for p in _PARAGRAPH_SPLIT.split(text) if p]
    return parts or [text]


class ParagraphCache:
    """LRU по хешу (абзац, язык, параметры): совпадение пропускает реплику целиком."""

    def __init__(self, max_entries: int) -> None:
        self._max = max_entries
        self._data: OrderedDict[str, tuple[list[dict[str, Any]], dict[str, Any]]] = OrderedDict()

    @staticmethod
    def key(paragraph: str, params: Mapping[str, str]) -> str:
        blob = json.dumps([paragraph, sorted(params.items())], ensure_ascii=False, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()

    def get(self, key: str) -> tuple[list[dict[str, Any]], dict[str, Any]] | None:
        hit = self._data.get(key)
        if hit is not None:
            self._data.move_to_end(key)
        return hit

    def put(self, key: str, matches: list[dict[str, Any]], meta: dict[str, Any]) -> None:
        if self._max <= 0:
            return
        self._data[key] = (matches, meta)
        self._data.move_to_end(key)
        while len(self._data) > self._max:
            self._data.popitem(last=False)

    def __len__(self) -> int:
        return len(self._data)


def is_replica_fault(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500  # noqa: PLR2004
    return isinstance(exc, httpx.TransportError)


def _distribute(matches: list[dict[str, Any]], sizes: list[tuple[int, int]]) -> dict[int, list[dict[str, Any]]]:
    """Совпадения общего текста разложить по абзацам (`sizes`: индекс и длина), смещения станут локальными."""
    buckets: dict[int, list[dict[str, Any]]] = {i: [] for i, _ in sizes}
    bounds: list[tuple[int, int, int]] = []
    pos = 0
    for i, size in sizes:
        bounds.append((pos, pos + size, i))
        pos += size
    for match in matches:
        offset = match.get("offset")
        if not isinstance(offset, int):
            continue
        for lo, hi, i in bounds:
            if lo <= offset < hi:
                buckets[i].append({**match, "offset": offset - lo})
                break
    return buckets


class LanguageToolProxy:
    """Запрос `/v2/check` от раннера или пользователя: кэш абзацев, доля пользователя, пул реплик."""

    def __init__(
        self, pool: ServicePool, client: httpx.AsyncClient, *, cache_entries: int = 2048, max_text_chars: int = 400_000
    ) -> None:
        self._pool = pool
        self._client = client
        self._cache = ParagraphCache(cache_entries)
        self._max_text = max_text_chars

    async def check(self, user_key: str, form: Mapping[str, str]) -> dict[str, Any]:
        text = form.get("text", "")
        if len(text) > self._max_text:
            raise TextTooLargeError(len(text))
        params = {k: v for k, v in form.items() if k != "text"}
        parts = split_paragraphs(text)
        keys = [ParagraphCache.key(p, params) for p in parts]
        cached = [self._cache.get(k) for k in keys]
        missing = [i for i, hit in enumerate(cached) if hit is None]
        if missing:
            await self._ask_replica(user_key, parts, keys, cached, missing, params)
        matches: list[dict[str, Any]] = []
        meta: dict[str, Any] = {}
        start = 0
        for part, hit in zip(parts, cached, strict=True):
            assert hit is not None  # noqa: S101 — недостающие заполнены выше
            matches.extend({**match, "offset": start + int(match.get("offset", 0))} for match in hit[0])
            meta = meta or hit[1]
            start += len(part)
        return {**meta, "matches": matches}

    async def _ask_replica(
        self,
        user_key: str,
        parts: list[str],
        keys: list[str],
        cached: list[tuple[list[dict[str, Any]], dict[str, Any]] | None],
        missing: list[int],
        params: Mapping[str, str],
    ) -> None:
        combined = "".join(parts[i] for i in missing)

        async def ask(url: str) -> dict[str, Any]:
            response = await self._client.post(f"{url}/v2/check", data={**params, "text": combined})
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise httpx.DecodingError("languagetool answered not an object")
            return payload

        payload = await self._pool.call(user_key, ask, is_fault=is_replica_fault)
        meta = {k: v for k, v in payload.items() if k != "matches"}
        buckets = _distribute(payload.get("matches", []), [(i, len(parts[i])) for i in missing])
        for i in missing:
            self._cache.put(keys[i], buckets[i], meta)
            cached[i] = (buckets[i], meta)

    async def probe(self) -> bool:
        async def check(url: str) -> bool:
            return (await self._client.get(f"{url}{_HEALTH_PATH}")).is_success

        return any(r.healthy for r in await self._pool.probe(check))


class PooledLanguageCheckService:
    """ILanguageCheckService поверх пула: проверки внутри процесса идут на наименее занятую реплику."""

    def __init__(self, pool: ServicePool, probe: Callable[[], Awaitable[bool]]) -> None:
        self._pool = pool
        self._probe = probe

    @property
    def current_base_url(self) -> str | None:
        try:
            return self._pool.pick_url()
        except Exception:  # noqa: BLE001 — нет здоровой реплики: проверки LanguageTool пропускаются
            return None

    def auth_headers(self) -> Mapping[str, str]:
        return {}

    async def ensure_running(self, image: str) -> str | None:  # noqa: ARG002
        """Для пула «запуск» это опрос реплик; образ не используется."""
        await self._probe()
        return self.current_base_url


class RemoteLanguageCheckService:
    """ILanguageCheckService раннера: ходит в прокси API с токеном задачи."""

    def __init__(self, proxy_base_url: str, headers: Callable[[], Mapping[str, str]]) -> None:
        self._base = proxy_base_url.rstrip("/")
        self._headers = headers

    @property
    def current_base_url(self) -> str | None:
        return self._base

    def auth_headers(self) -> Mapping[str, str]:
        return self._headers()

    async def ensure_running(self, image: str) -> str | None:  # noqa: ARG002
        return self._base


__all__ = [
    "LanguageToolProxy",
    "ParagraphCache",
    "PooledLanguageCheckService",
    "RemoteLanguageCheckService",
    "TextTooLargeError",
    "split_paragraphs",
]
