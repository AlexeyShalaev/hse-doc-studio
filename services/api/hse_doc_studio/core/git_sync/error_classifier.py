"""Разбор stderr git и ssh в код ошибки из закрытого списка, плюс очистка текста от секретов.

Разбор рассчитан на вывод с `LC_ALL=C`: раннер git всегда выставляет его. Таблица упорядочена,
побеждает первая сработавшая строка: узкие причины (SSO, защита ветки, размер файла) стоят выше
общих (403, 404, обрыв связи). Неизвестный текст даёт git_error с очищенным хвостом stderr.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from re import Pattern

from hse_doc_studio.core.git_sync.errors import GitErrorCode

DETAIL_TAIL_CHARS = 400
_MIN_SECRET_LENGTH = 4
_MASK = "***"


class GitOp(StrEnum):
    probe = "probe"
    fetch = "fetch"
    push = "push"
    clone = "clone"


class Transport(StrEnum):
    https = "https"
    http = "http"
    ssh = "ssh"
    file = "file"


@dataclass(frozen=True)
class ClassifiedError:
    code: GitErrorCode
    # Очищенный хвост stderr: для git_error идёт в detail, для остальных кодов только в журнал.
    detail: str


@dataclass(frozen=True)
class _Rule:
    code: GitErrorCode
    pattern: Pattern[str]
    # Правило действует только для этих операций и транспортов; None значит для любых.
    ops: frozenset[GitOp] | None = None
    transports: frozenset[Transport] | None = None


def _rule(
    code: GitErrorCode,
    pattern: str,
    *,
    ops: Iterable[GitOp] | None = None,
    transports: Iterable[Transport] | None = None,
) -> _Rule:
    return _Rule(
        code,
        re.compile(pattern, re.IGNORECASE),
        frozenset(ops) if ops is not None else None,
        frozenset(transports) if transports is not None else None,
    )


_PUSH = (GitOp.push,)
_SSH = (Transport.ssh,)
_HTTP = (Transport.https, Transport.http)

_RULES: tuple[_Rule, ...] = (
    _rule(
        GitErrorCode.host_key_changed,
        r"REMOTE HOST IDENTIFICATION HAS CHANGED|Offending \w+ key in",
        transports=_SSH,
    ),
    _rule(
        GitErrorCode.host_key_unknown,
        r"Host key verification failed|No \w+ host key is known|host key for .* not known",
        transports=_SSH,
    ),
    _rule(
        GitErrorCode.ssh_unavailable,
        r"cannot (?:run|exec) '?\S*ssh'?|ssh: (?:command )?not found|ssh: No such file or directory",
        transports=_SSH,
    ),
    _rule(GitErrorCode.git_unavailable, r"git: (?:command )?not found|git: No such file or directory"),
    _rule(GitErrorCode.sso_required, r"SAML (?:SSO|enforcement)|organization SAML|SSO session"),
    _rule(GitErrorCode.email_privacy, r"GH007|email privacy restrictions|push declined due to email", ops=_PUSH),
    _rule(
        GitErrorCode.workflow_scope_missing,
        r"refusing to allow an? (?:Personal Access Token|OAuth App) to create or update workflow"
        r"|without [`'\"]?workflow[`'\"]? scope",
        ops=_PUSH,
    ),
    _rule(
        GitErrorCode.large_file,
        r"GH001|exceeds GitHub's file size limit|this exceeds|Large files detected"
        r"|pack exceeds maximum allowed size|HTTP 413|Request Entity Too Large"
        r"|pre-receive hook declined[\s\S]*(?:file size|too large|size limit)",
        ops=_PUSH,
    ),
    _rule(
        GitErrorCode.protected_branch,
        r"protected branch|GH006|GH013|Repository rule violations|Changes must be made through a pull request",
        ops=_PUSH,
    ),
    _rule(
        GitErrorCode.remote_moved,
        r"\[rejected\][^\n]*\((?:fetch first|non-fast-forward|stale info)\)"
        r"|Updates were rejected because (?:the remote contains work|the tip of your current branch is behind)",
        ops=_PUSH,
    ),
    _rule(GitErrorCode.rate_limited, r"returned error: 429|rate limit|Too Many Requests"),
    _rule(
        GitErrorCode.branch_missing,
        r"couldn't find remote ref|Remote branch .* not found|src refspec .* does not match any",
    ),
    _rule(
        GitErrorCode.tls_untrusted_ca,
        r"unable to get (?:local )?issuer certificate|unable to verify the first certificate"
        r"|self[- ]signed certificate|certificate is not trusted|unknown certificate authority"
        # schannel (Git for Windows) называет причину кодом; текст рядом зависит от языка системы.
        r"|SEC_E_UNTRUSTED_ROOT|CERT_E_UNTRUSTEDROOT",
        transports=_HTTP,
    ),
    _rule(
        GitErrorCode.tls_error,
        r"SSL certificate problem|certificate verify failed|server certificate verification failed"
        r"|gnutls_handshake\(\) failed|no alternative certificate subject name"
        r"|certificate subject name .* does not match",
        transports=_HTTP,
    ),
    _rule(
        GitErrorCode.forbidden_write,
        r"returned error: 403|Permission to .* denied|key you've authenticated with is read-only"
        r"|You are not allowed to push|access denied or repository not exported|Write access to repository not granted",
        ops=_PUSH,
    ),
    _rule(
        GitErrorCode.auth_failed,
        r"Authentication failed|Invalid username or password|HTTP Basic: Access denied|returned error: 40[13]"
        r"|Permission denied \(publickey|could not read (?:Username|Password)|terminal prompts disabled"
        r"|Bad credentials|invalid credentials",
    ),
    _rule(
        GitErrorCode.not_found_or_no_access,
        r"Repository not found|returned error: 404|does not appear to be a git repository"
        r"|repository '.*' not found|Project not found|HTTP 404",
    ),
    _rule(
        GitErrorCode.offline,
        r"Could not resolve host|Could not resolve hostname|Name or service not known"
        r"|Temporary failure in name resolution|nodename nor servname provided|Failed to connect to"
        r"|Couldn't connect to server|Connection timed out|Connection refused|Network is unreachable"
        r"|No route to host|Connection reset|Connection closed by remote host|Operation timed out"
        r"|TLS connection was non-properly terminated|Could not connect|Unable to connect to|RPC failed; curl \d+",
    ),
)

# Причина, которую git назвал сам. У libcurl-gnutls (образ Студии на Debian) для любого сбоя проверки сертификата
# одна строка «server certificate verification failed»: чем он плох (чужой центр, срок, имя), по ней не видно.
_SPECIFIC_TLS_REASON = re.compile(
    r"SSL certificate problem|certificate verify failed|no alternative certificate subject name"
    r"|certificate subject name .* does not match|SEC_E_|CERT_E_",
    re.IGNORECASE,
)


def tls_reason_is_hidden(stderr: str) -> bool:
    """Git сообщил о сбое TLS, не назвав причины: центр выдачи надо выяснить самим (см. раннер)."""
    return not _SPECIFIC_TLS_REASON.search(stderr)


# Коды, которые способен вернуть classify_git_stderr; остальные коды из контракта ставят другие места.
CLASSIFIER_CODES = frozenset({rule.code for rule in _RULES} | {GitErrorCode.git_error})


def _applies(rule: _Rule, op: GitOp, transport: Transport) -> bool:
    return (rule.ops is None or op in rule.ops) and (rule.transports is None or transport in rule.transports)


def classify_git_stderr(
    stderr: str, *, op: GitOp, transport: Transport, secrets: Iterable[str] = ()
) -> ClassifiedError:
    """Код ошибки по тексту stderr и очищенный хвост этого текста (до 400 знаков)."""
    detail = scrub(stderr, secrets)[-DETAIL_TAIL_CHARS:].strip()
    for rule in _RULES:
        if rule.pattern.search(stderr) and _applies(rule, op, transport):
            return ClassifiedError(rule.code, detail)
    return ClassifiedError(GitErrorCode.git_error, detail)


_URL_USERINFO = re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*)://[^/\s@]*@")
_AUTH_HEADER = re.compile(r"(?i)\b(authorization|proxy-authorization)\s*[:=][^\r\n]*")
_BASIC_BEARER = re.compile(r"(?i)\b(basic|bearer)\s+[A-Za-z0-9+/=._~\-]{8,}")
_PEM_BLOCK = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL)
_PEM_OPEN = re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*", re.DOTALL)
_TOKEN_SHAPES = (
    re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bgl(?:pat|oas|dt|rt|cbt|ptt|soat|imt|agent)-[A-Za-z0-9_\-]{20,}"),
    re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}"),
)


def _secret_forms(secret: str) -> list[str]:
    encoded = (base64.b64encode(payload.encode()).decode().rstrip("=") for payload in (secret, f":{secret}"))
    return [secret, *encoded]


def scrub(text: str, secrets: Iterable[str] = ()) -> str:
    """Убрать из текста секреты: переданные явно, userinfo адресов, заголовки авторизации, ключи PEM, формы токенов."""
    for secret in sorted((s for s in secrets if len(s) >= _MIN_SECRET_LENGTH), key=len, reverse=True):
        for form in _secret_forms(secret):
            text = text.replace(form, _MASK)
    text = _PEM_BLOCK.sub(_MASK, text)
    text = _PEM_OPEN.sub(_MASK, text)
    text = _AUTH_HEADER.sub(rf"\1: {_MASK}", text)
    text = _BASIC_BEARER.sub(rf"\1 {_MASK}", text)
    text = _URL_USERINFO.sub(rf"\1://{_MASK}@", text)
    for shape in _TOKEN_SHAPES:
        text = shape.sub(_MASK, text)
    return text
