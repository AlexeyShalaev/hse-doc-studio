"""Проверка обновлений: запрос к фиду релизов и выбор самой свежей версии.

По умолчанию фид — **официальные GitHub Releases** продукта (их наполняет
release-please), поэтому кнопка «Проверить обновления» работает из коробки без
настройки. `HSE_STUDIO__UPDATE_FEED_URL` можно переопределить (форк, зеркало, свой
фид) или выключить (`off`) — тогда проверка живёт по последнему известному ответу
из кэша, а приложение не стучится в интернет.

Понимаются два формата ответа:
  • GitHub API: массив релизов (или один релиз) с `tag_name`/`published_at`;
  • простой JSON: {"latest": "1.2.3"} или {"releases": [{"v": "1.2.3"}, …]}.

Из фида берутся номер последней версии, её дата и заметки. Заметки про УЖЕ
УСТАНОВЛЕННЫЕ версии приложение берёт из своего курируемого двуязычного списка
(release-notes.json), но про ещё не установленную версию тот список
знать не может — он едет внутри сборки. Поэтому для доступного обновления текст
приходит из фида; в тело GitHub-релиза его кладёт publish.yml из того же
курируемого источника (`scripts/gen_changelog.py --notes-for`).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import httpx
import structlog

from hse_doc_studio.core.i18n import localized_error
from hse_doc_studio.core.update.entities import ReleaseEntry, UpdateFeedProbe
from hse_doc_studio.core.update.services import extract_version, feed_disabled, parse_version

logger = structlog.get_logger()


def _usable(release: Any) -> bool:
    if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
        return False
    return bool(release.get("tag_name") or release.get("name") or release.get("v"))


def _release_version(release: dict[str, Any]) -> str:
    raw = release.get("tag_name") or release.get("name") or release.get("v") or ""
    return extract_version(str(raw))


def _release_date(release: dict[str, Any]) -> str:
    """`published_at` (ISO-8601) → YYYY-MM-DD; мусор и отсутствие → пустая строка."""
    raw = release.get("published_at") or release.get("created_at") or release.get("date") or ""
    if not isinstance(raw, str) or not raw:
        return ""
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return ""


def _release_notes(release: dict[str, Any], limit: int = 20) -> tuple[str, ...]:
    """Тело релиза (markdown) → пункты для UI; наш простой формат — готовый список.

    Берём строки-буллеты, снимаем markdown-выделение и хвостовую ссылку на коммит,
    которую добавляет release-please. Заголовки и пустые строки пропускаем.
    """
    ready = release.get("notes")
    if isinstance(ready, list):
        return tuple(str(note) for note in ready if str(note).strip())

    notes: list[str] = []
    for raw_line in str(release.get("body") or "").splitlines():
        line = raw_line.strip()
        if not line.startswith(("* ", "- ")):
            continue
        text = line[2:].split(" ([", 1)[0].replace("**", "").replace("`", "").strip()
        if text:
            notes.append(text)
        if len(notes) >= limit:
            break
    return tuple(notes)


def releases_from_feed(data: dict[str, Any] | list[Any]) -> tuple[ReleaseEntry, ...]:
    """Свести любой поддерживаемый ответ к списку релизов, свежие первыми.

    Возвращаем ВСЕ релизы, а не только последний: пользователь может переключиться
    на любую версию, в том числе более раннюю. Чистая функция — разбор тестируется
    без сети.
    """
    explicit = ""
    if isinstance(data, dict) and "tag_name" not in data:
        # Простой формат: `latest` и/или список записей.
        raw_releases = data.get("releases")
        entries: list[Any] = raw_releases if isinstance(raw_releases, list) else []
        raw_latest = data.get("latest")
        explicit = extract_version(raw_latest) if isinstance(raw_latest, str) else ""
    else:
        # GitHub: массив релизов или один релиз.
        entries = data if isinstance(data, list) else [data]

    by_version: dict[str, ReleaseEntry] = {}
    for item in entries:
        if not _usable(item):
            continue
        version = _release_version(item)
        # Дубли по версии не копим: первое вхождение выигрывает.
        if version and version not in by_version:
            by_version[version] = ReleaseEntry(
                version=version,
                date=_release_date(item),
                notes=_release_notes(item),
            )

    # Фид может сам назвать свежую версию, которой нет среди записей (наш простой
    # формат допускает голый `latest`) — тогда добавляем её без заметок.
    if explicit and explicit not in by_version:
        by_version[explicit] = ReleaseEntry(version=explicit, date="", notes=())

    # Порядок в ответе GitHub — по дате публикации; патч к старой ветке может
    # оказаться первым, поэтому сортируем по версии, а не по позиции.
    return tuple(sorted(by_version.values(), key=lambda r: parse_version(r.version), reverse=True))


class GithubUpdateFeedGateway:
    """`IUpdateFeedGateway` над HTTP-фидом релизов.

    Никогда не бросает исключений: недоступный фид — это не ошибка приложения, а
    состояние «проверить не удалось», которое UI показывает отдельно от «всё свежее».
    """

    def __init__(self, feed_url: str, timeout_s: float, user_agent: str) -> None:
        self._feed_url = feed_url
        self._timeout_s = timeout_s
        self._user_agent = user_agent

    async def probe(self) -> UpdateFeedProbe:
        if feed_disabled(self._feed_url):
            return UpdateFeedProbe(
                reason=localized_error(
                    "Проверка обновлений отключена в настройках.",
                    "Update checks are disabled in the settings.",
                )
            )
        try:
            data = await self._fetch()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("update_check_failed", url=self._feed_url, exc=str(exc))
            return UpdateFeedProbe(
                reason=localized_error(
                    f"Не удалось получить список релизов: {exc}",
                    f"Could not fetch the release feed: {exc}",
                )
            )
        return UpdateFeedProbe(releases=releases_from_feed(data), checked=True)

    async def _fetch(self) -> dict[str, Any] | list[Any]:
        if not self._feed_url.lower().startswith(("http://", "https://")):
            msg = "feed URL must be http(s)"
            raise ValueError(msg)
        async with httpx.AsyncClient(timeout=self._timeout_s, follow_redirects=True) as client:
            response = await client.get(
                self._feed_url,
                headers={
                    "User-Agent": self._user_agent,
                    # Игнорируется не-GitHub фидами.
                    "Accept": "application/vnd.github+json",
                },
            )
            response.raise_for_status()
            data: Any = response.json()
        if not isinstance(data, dict | list):
            # ValueError, а не TypeError: это нарушенный контракт фида (как и битый
            # JSON, который json() бросает тем же типом), а не ошибка типов в коде.
            msg = "feed must be a JSON object or array"
            raise ValueError(msg)  # noqa: TRY004
        return data
