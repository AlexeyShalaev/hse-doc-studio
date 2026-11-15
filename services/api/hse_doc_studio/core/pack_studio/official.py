"""Официальные паки (docs/design/template-studio.md, 4.7, срез T22): чистые правила без сети и базы.

Официальный репозиторий паков это репозиторий самой Студии (`packs/` в монорепе); его адрес задаёт установка
(`HSE_STUDIO__PACK_STUDIO__OFFICIAL_REPO_URL`), пустой адрес прячет кнопку «Официальные паки». Вклад в него идёт
через PR только своим аккаунтом GitHub: токен человека, форк в его аккаунт (поток T6).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import quote, urlsplit

from hse_doc_studio.core.pack_studio.git_flow import repo_key, repo_path_of

LICENSE_FILE = "LICENSE"
CONTRIBUTING_FILE = "CONTRIBUTING.md"
# Якорь раздела про паки в CONTRIBUTING.md репозитория Студии.
CONTRIBUTING_ANCHOR = "contributing-to-the-official-packs"


@dataclass(frozen=True)
class OfficialRepo:
    """Официальный репозиторий паков установки: адрес для git, папка паков, базовая ветка, лицензия вклада."""

    url: str
    packs_path: str
    base_branch: str
    license: str
    key: str
    web_url: str

    def _blob(self, name: str) -> str:
        return f"{self.web_url}/blob/{quote(self.base_branch, safe='/')}/{name}"

    @property
    def license_url(self) -> str:
        return self._blob(LICENSE_FILE)

    @property
    def contributing_url(self) -> str:
        return f"{self._blob(CONTRIBUTING_FILE)}#{CONTRIBUTING_ANCHOR}"

    def matches(self, remote_url: str | None) -> bool:
        """Адрес пространства указывает на этот репозиторий (хост, порт и путь без регистра и `.git`)."""
        key = url_key(remote_url) if remote_url else None
        return key is not None and key == self.key


def url_key(url: str) -> str | None:
    """Ключ репозитория по адресу http(s); None для пустого или не http-адреса."""
    parts = urlsplit(url.strip())
    if parts.scheme not in {"https", "http"} or not parts.hostname:
        return None
    try:
        port = parts.port
    except ValueError:
        return None
    return repo_key(parts.hostname, port, repo_path_of(url.strip(), None))


def official_repo(url: str | None, *, packs_path: str, base_branch: str, license: str) -> OfficialRepo | None:  # noqa: A002 — так поле зовётся в pack.yaml
    """Официальный репозиторий из настроек установки; пустой адрес, не https или без пути: кнопки нет."""
    raw = (url or "").strip()
    if not raw:
        return None
    parts = urlsplit(raw)
    key = url_key(raw)
    path = repo_path_of(raw, None)
    if parts.scheme != "https" or key is None or "/" not in path:
        return None
    authority = parts.hostname or ""
    if parts.port:
        authority += f":{parts.port}"
    return OfficialRepo(
        url=raw,
        packs_path=packs_path.strip().strip("/") or ".",
        base_branch=base_branch.strip() or "master",
        license=license.strip() or "Apache-2.0",
        key=key,
        web_url=f"https://{authority}/{path}",
    )


def outside_packs(paths: Iterable[str], packs_path: str) -> tuple[str, ...]:
    """Пути от корня репозитория вне папки паков: предложение в официальные паки или через служебный доступ их не
    несёт (раздел 9)."""
    if packs_path in {"", "."}:
        return ()
    prefix = f"{packs_path.strip('/')}/"
    return tuple(sorted({path for path in paths if path and not path.startswith(prefix)}))
