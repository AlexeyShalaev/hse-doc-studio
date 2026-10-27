"""Каталог git-провайдеров: определение по хосту, ссылки на выпуск токена и ключа, права токена.

Данные лежат в providers.json рядом с модулем. Файл совпадает побайтно с contracts/git-sync/providers.json
(фронтенд читает такую же копию), а векторы provider_cases.json общие с TypeScript. Функции чистые:
сеть и хранение настроек хостов (подмена провайдера, свой CA) живут снаружи, сюда они приходят аргументами.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import quote

_CATALOG_FILE = Path(__file__).with_name("providers.json")
_MAX_EXPIRES_DAYS = 366
_WEB_BASE = re.compile(r"^https?://[^\s/?#]+(?:/[^\s?#]*)?$")
_SUBPATH_SEGMENT = re.compile(r"^[A-Za-z0-9._~%-]+$")
_PLACEHOLDER = re.compile(r"^\{(\w+)\}$")
_PERCENT_ESCAPE = re.compile(r"%[0-9A-Fa-f]{2}")


class GitProvider(StrEnum):
    github = "github"
    gitlab = "gitlab"
    gitea = "gitea"
    bitbucket = "bitbucket"
    other = "other"


class DetectedBy(StrEnum):
    """Откуда известен провайдер: выбор пользователя, имя хоста, ответ API сервера или не известен."""

    override = "override"
    host = "host"
    api = "api"
    unknown = "unknown"


class Sufficiency(StrEnum):
    sufficient = "sufficient"
    too_narrow = "too_narrow"
    too_broad = "too_broad"
    unknown = "unknown"


class LinkKind(StrEnum):
    # Параметры страницы проверены по документации: форма открывается заполненной.
    prefilled = "prefilled"
    # Просто страница: остальное человек делает по шагам.
    plain = "plain"


@dataclass(frozen=True)
class ProviderInfo:
    id: GitProvider
    detected_by: DetectedBy
    version: str | None = None


@dataclass(frozen=True)
class ApiDetection:
    """Что ответил API сервера на проверку: провайдер, версия, если сервер её назвал, и корень API, где он нашёлся."""

    provider: GitProvider
    version: str | None = None
    api_base: str | None = None


@dataclass(frozen=True)
class HostRule:
    # exact: весь хост; first_label: первая метка; label: любая метка.
    match: str
    value: str


@dataclass(frozen=True)
class LinkTemplate:
    kind: LinkKind
    broad: bool
    path: str
    query: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class ApiDetect:
    path: str
    version_header: str | None
    version_key: str | None


@dataclass(frozen=True)
class ApiSpec:
    base: str | None
    base_by_host: Mapping[str, str]
    detect: ApiDetect | None


@dataclass(frozen=True)
class Permissions:
    required: tuple[str, ...]
    optional: tuple[str, ...]
    too_broad: tuple[str, ...]
    implies: Mapping[str, tuple[str, ...]]
    human: Mapping[str, str]


@dataclass(frozen=True)
class Introspection:
    method: str
    path: str
    auth: str
    # Откуда брать права: header:<Имя>, body:<поле> или none.
    scopes: str


@dataclass(frozen=True)
class SshLinkTemplates:
    user_keys: LinkTemplate | None
    deploy_key: LinkTemplate | None


@dataclass(frozen=True)
class ProviderSpec:
    id: GitProvider
    label: str
    host_rules: tuple[HostRule, ...]
    api: ApiSpec
    auth_variants: tuple[str, ...]
    name_limit: int
    description_limit: int
    token_primary: LinkTemplate | None
    token_fallback: LinkTemplate | None
    permissions: Permissions
    introspection: Introspection | None
    ssh_links: SshLinkTemplates | None
    docs_url: str | None


@dataclass(frozen=True)
class ProviderLink:
    kind: LinkKind
    url: str
    # Токен с широким доступом: интерфейс предупреждает и советует точный.
    broad: bool = False


@dataclass(frozen=True)
class TokenLinks:
    primary: ProviderLink | None
    fallback: ProviderLink | None


@dataclass(frozen=True)
class SshLinks:
    user_keys: ProviderLink | None
    deploy_key: ProviderLink | None


@dataclass(frozen=True)
class ScopeAssessment:
    sufficiency: Sufficiency
    missing: tuple[str, ...] = ()


@dataclass(frozen=True)
class CatalogDefaults:
    token_name_with_project: str
    token_name_without_project: str
    token_description: Mapping[str, str]
    expires_in_days: int
    instance_prefix_max_depth: int


@dataclass(frozen=True)
class ProviderCatalog:
    providers: tuple[ProviderSpec, ...]
    defaults: CatalogDefaults

    def spec(self, provider: GitProvider | str) -> ProviderSpec:
        wanted = GitProvider(provider)
        return next(spec for spec in self.providers if spec.id is wanted)


def _link(raw: dict[str, Any] | None) -> LinkTemplate | None:
    if raw is None:
        return None
    return LinkTemplate(
        kind=LinkKind(raw["kind"]),
        broad=bool(raw.get("broad", False)),
        path=raw["path"],
        query=tuple((item["key"], item["value"]) for item in raw.get("query", [])),
    )


def _api(raw: dict[str, Any]) -> ApiSpec:
    detect = raw["detect"]
    return ApiSpec(
        base=raw["base"],
        base_by_host=dict(raw["base_by_host"]),
        detect=(
            ApiDetect(path=detect["path"], version_header=detect["version_header"], version_key=detect["version_key"])
            if detect
            else None
        ),
    )


def _permissions(raw: dict[str, Any]) -> Permissions:
    return Permissions(
        required=tuple(raw["required"]),
        optional=tuple(raw["optional"]),
        too_broad=tuple(raw["too_broad"]),
        implies={key: tuple(value) for key, value in raw["implies"].items()},
        human=dict(raw["human"]),
    )


def _spec(raw: dict[str, Any]) -> ProviderSpec:
    links = raw["token_links"] or {}
    introspection = raw["introspection"]
    ssh = raw["ssh_links"]
    return ProviderSpec(
        id=GitProvider(raw["id"]),
        label=raw["label"],
        host_rules=tuple(HostRule(match=rule["match"], value=rule["value"]) for rule in raw["host_rules"]),
        api=_api(raw["api"]),
        auth_variants=tuple(raw["auth_variants"]),
        name_limit=raw["limits"]["name"],
        description_limit=raw["limits"]["description"],
        token_primary=_link(links.get("primary")),
        token_fallback=_link(links.get("fallback")),
        permissions=_permissions(raw["permissions"]),
        introspection=(
            Introspection(
                method=introspection["method"],
                path=introspection["path"],
                auth=introspection["auth"],
                scopes=introspection["scopes"],
            )
            if introspection
            else None
        ),
        ssh_links=(
            SshLinkTemplates(user_keys=_link(ssh["user_keys"]), deploy_key=_link(ssh["deploy_key"])) if ssh else None
        ),
        docs_url=raw["docs_url"],
    )


@lru_cache(maxsize=1)
def catalog() -> ProviderCatalog:
    raw = json.loads(_CATALOG_FILE.read_text(encoding="utf-8"))
    defaults = raw["defaults"]
    return ProviderCatalog(
        providers=tuple(_spec(item) for item in raw["providers"]),
        defaults=CatalogDefaults(
            token_name_with_project=defaults["token_name"]["with_project"],
            token_name_without_project=defaults["token_name"]["without_project"],
            token_description=dict(defaults["token_description"]),
            expires_in_days=defaults["expires_in_days"],
            instance_prefix_max_depth=defaults["instance_prefix_max_depth"],
        ),
    )


def provider_spec(provider: GitProvider | str) -> ProviderSpec:
    return catalog().spec(provider)


# --- определение провайдера ---------------------------------------------------


def _rule_matches(rule: HostRule, host: str) -> bool:
    labels = host.split(".")
    if rule.match == "exact":
        return host == rule.value
    if rule.match == "first_label":
        return labels[0] == rule.value
    return rule.value in labels


def provider_for_host(host: str | None) -> GitProvider:
    """Провайдер по имени хоста; первое совпадение в порядке каталога, иначе other."""
    if host is None:
        return GitProvider.other
    name = host.lower()
    for spec in catalog().providers:
        if any(_rule_matches(rule, name) for rule in spec.host_rules):
            return spec.id
    return GitProvider.other


def detect_provider(
    host: str | None,
    *,
    overrides: Mapping[str, GitProvider] | None = None,
    api: ApiDetection | None = None,
) -> ProviderInfo:
    """Порядок такой: выбор пользователя для хоста, имя хоста, ответ API, иначе other и unknown.

    Версия берётся из ответа API, если он назвал того же провайдера, что выбран.
    """
    name = host.lower() if host else None
    if name and overrides and name in overrides:
        chosen, by = overrides[name], DetectedBy.override
    elif (heuristic := provider_for_host(name)) is not GitProvider.other:
        chosen, by = heuristic, DetectedBy.host
    elif api is not None:
        chosen, by = api.provider, DetectedBy.api
    else:
        chosen, by = GitProvider.other, DetectedBy.unknown
    version = api.version if api is not None and api.provider is chosen else None
    return ProviderInfo(id=chosen, detected_by=by, version=version)


# --- адреса сайта и API -------------------------------------------------------


def web_base(*, host: str | None, port: int | None, secure: bool = True, subpath: str = "") -> str | None:
    """Корень сайта сервера: схема, хост, порт и путь установки (https://host/gitlab).

    Порт нужен только у https/http; порт ssh к сайту не относится, вызывающий передаёт None.
    Путь установки без хвостового слэша; недопустимый путь даёт None.
    """
    if host is None:
        return None
    trimmed = subpath.strip("/")
    segments = trimmed.split("/") if trimmed else []
    if not all(_SUBPATH_SEGMENT.match(segment) and segment not in {".", ".."} for segment in segments):
        return None
    authority = host + (f":{port}" if port else "")
    return f"{'https' if secure else 'http'}://{authority}" + "".join(f"/{segment}" for segment in segments)


def api_base(provider: GitProvider | str, *, host: str | None, base: str | None) -> str | None:
    """Корень API: известный хост (api.github.com) или шаблон от корня сайта."""
    api = provider_spec(provider).api
    if host is not None and host.lower() in api.base_by_host:
        return api.base_by_host[host.lower()]
    if api.base is None or base is None:
        return None
    return api.base.replace("{web_base}", base)


def instance_prefix_candidates(segments: Sequence[str]) -> list[str]:
    """Возможные пути установки по пути репозитория: у сервера под /gitlab группа и проект идут после префикса.

    От короткого к длинному; после префикса остаются как минимум владелец и репозиторий.
    """
    depth_limit = catalog().defaults.instance_prefix_max_depth
    longest = min(len(segments) - 2, depth_limit - 1)
    return ["".join(f"/{segment}" for segment in segments[:depth]) for depth in range(0, longest + 1)]


# --- ссылки -------------------------------------------------------------------


def encode_component(text: str) -> str:
    """Строгое кодирование значения параметра: без кодирования остаются только буквы, цифры и -._~."""
    return quote(text, safe="")


def _encode_segment(segment: str) -> str:
    parts: list[str] = []
    position = 0
    for match in _PERCENT_ESCAPE.finditer(segment):
        parts.append(quote(segment[position : match.start()], safe=""))
        parts.append(match.group())
        position = match.end()
    parts.append(quote(segment[position:], safe=""))
    return "".join(parts)


def clean_text(text: str, limit: int) -> str:
    """Однострочный текст для параметра: управляющие символы и переносы заменены пробелом, длина в символах."""
    spaced = "".join(" " if char.isspace() or unicodedata.category(char).startswith("C") else char for char in text)
    return " ".join(spaced.split())[:limit].rstrip()


def default_token_name(project_name: str | None) -> str:
    defaults = catalog().defaults
    project = clean_text(project_name or "", 200)
    if not project:
        return defaults.token_name_without_project
    return defaults.token_name_with_project.replace("{project}", project)


def default_token_description(day: date, lang: str) -> str:
    templates = catalog().defaults.token_description
    return templates.get(lang, templates["en"]).replace("{date}", day.isoformat())


def _path_of(owner: str | None, repo: str | None) -> str | None:
    if not owner or not repo:
        return None
    return "/".join(_encode_segment(segment) for segment in [*owner.split("/"), repo])


def _checked_base(base: str) -> str:
    if not _WEB_BASE.match(base):
        raise ValueError("web_base must be an http(s) address without query")
    return base.rstrip("/")


def _expand_query(template: LinkTemplate, values: Mapping[str, str | None]) -> str:
    pairs: list[str] = []
    for key, value in template.query:
        placeholder = _PLACEHOLDER.match(value)
        if placeholder is None:
            pairs.append(f"{key}={encode_component(value)}")
        elif data := values.get(placeholder.group(1)):
            pairs.append(f"{key}={data}")
    return f"?{'&'.join(pairs)}" if pairs else ""


def _render(
    template: LinkTemplate | None, base: str, path: str | None, values: Mapping[str, str | None]
) -> ProviderLink | None:
    if template is None:
        return None
    if "{path}" in template.path:
        if path is None:
            return None
        route = template.path.replace("{path}", path)
    else:
        route = template.path
    return ProviderLink(kind=template.kind, url=f"{base}{route}{_expand_query(template, values)}", broad=template.broad)


def token_links(
    provider: GitProvider | str,
    *,
    web_base: str,
    name: str,
    description: str,
    owner: str | None = None,
    repo: str | None = None,
    expires_in_days: int | None = None,
) -> TokenLinks:
    """Ссылки на выпуск токена: основная и запасная (для старых версий сервера или широкого токена).

    Имя и описание очищаются и укорачиваются до лимитов провайдера, затем кодируются строго.
    `expires_in_days` попадает в ссылку только там, где у страницы есть такой параметр (1..366).
    """
    spec = provider_spec(provider)
    base = _checked_base(web_base)
    clean_name = clean_text(name, spec.name_limit)
    clean_description = clean_text(description, spec.description_limit)
    single_owner = owner if owner and "/" not in owner else None
    values: dict[str, str | None] = {
        "name": encode_component(clean_name) if clean_name else None,
        "description": encode_component(clean_description) if clean_description else None,
        "scopes": ",".join(encode_component(scope) for scope in spec.permissions.required),
        "target_name": encode_component(single_owner) if single_owner else None,
        "expires_in": str(min(max(expires_in_days, 1), _MAX_EXPIRES_DAYS)) if expires_in_days is not None else None,
    }
    path = _path_of(owner, repo)
    return TokenLinks(
        primary=_render(spec.token_primary, base, path, values),
        fallback=_render(spec.token_fallback, base, path, values),
    )


def ssh_links(
    provider: GitProvider | str, *, web_base: str, owner: str | None = None, repo: str | None = None
) -> SshLinks:
    """Страницы добавления ключа: ключ пользователя и deploy-ключ репозитория."""
    spec = provider_spec(provider)
    if spec.ssh_links is None:
        return SshLinks(user_keys=None, deploy_key=None)
    base = _checked_base(web_base)
    path = _path_of(owner, repo)
    return SshLinks(
        user_keys=_render(spec.ssh_links.user_keys, base, path, {}),
        deploy_key=_render(spec.ssh_links.deploy_key, base, path, {}),
    )


# --- права токена -------------------------------------------------------------


def assess_scopes(provider: GitProvider | str, scopes: Iterable[str] | None) -> ScopeAssessment:
    """Хватает ли найденных прав для чтения и записи.

    None значит, что права прочитать нельзя (старый сервер, точный токен): вывод unknown, дальше работает проверка git.
    Не хватает прав (push не пройдёт) важнее, чем лишние права.
    """
    permissions = provider_spec(provider).permissions
    if scopes is None:
        return ScopeAssessment(Sufficiency.unknown)
    given = set(scopes)
    granted = set(given)
    for scope in given:
        granted.update(permissions.implies.get(scope, ()))
    missing = tuple(scope for scope in permissions.required if scope not in granted)
    if missing:
        return ScopeAssessment(Sufficiency.too_narrow, missing)
    if given.intersection(permissions.too_broad):
        return ScopeAssessment(Sufficiency.too_broad)
    return ScopeAssessment(Sufficiency.sufficient)
