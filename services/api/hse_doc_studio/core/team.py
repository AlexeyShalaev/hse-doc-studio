"""Team-mode primitives: doc-instance ids, per-base layout, author slugs.

Solo projects keep the flat legacy layout (document folders at the project
root). Team projects hold one "mini-project" tree per base: ``shared/`` for
scope=shared documents and ``<author.slug>/`` for each managed author's
personal set. Every base carries its own ``common/`` (+ ``assets/``) with the
dynamic includes regenerated from that base's context (author topic, his
doc-code, …), so pack sources with ``\\input{../common/...}`` work unchanged.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from hse_doc_studio.core.entities import Document, Project
from hse_doc_studio.core.enums import ProjectStaffing
from hse_doc_studio.core.value_objects import Author

# Разделитель "{def_id}--{owner}" в id инстанса документа; тот же сепаратор
# используют рантайм-слоты подписей ("author--shalaev") и инстансы форм
# ("ai_declaration--shalaev"). Ровно один URL-сегмент, валидное имя каталога,
# не пересекается с зарезервированными tool-id фронтенда (files/pack/…).
OWNER_SEPARATOR = "--"
# Имя базовой папки общих (scope=shared) документов team-проекта.
SHARED_DIR = "shared"

# Слаги, которые не могут быть папкой автора: общая база, служебные каталоги
# внутри баз и корневые группы файлов проекта.
RESERVED_SLUGS = frozenset({SHARED_DIR, "common", "assets", "nda", "submissions"})

_SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")

_TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
}  # fmt: skip


def is_team(project: Project) -> bool:
    return project.staffing == ProjectStaffing.team


def doc_instance_id(def_id: str, owner: str | None) -> str:
    return f"{def_id}{OWNER_SEPARATOR}{owner}" if owner else def_id


def split_instance_id(instance_id: str) -> tuple[str, str | None]:
    """Разбор "{base_id}--{owner}" → (base_id, owner); без сепаратора owner=None.

    Для сущностей, которые не несут def_id/owner явно (слоты подписей, формы).
    Базовые id пака не должны содержать "--" — это валидирует парсер пака.
    """
    if OWNER_SEPARATOR in instance_id:
        base_id, owner = instance_id.rsplit(OWNER_SEPARATOR, 1)
        return base_id, owner or None
    return instance_id, None


def base_dir_for_owner(project: Project, owner: str | None) -> str:
    """Базовая папка ('' = корень проекта; POSIX, без завершающего слэша)."""
    if not is_team(project):
        return ""
    return owner or SHARED_DIR


def doc_base_dir(project: Project, doc: Document) -> str:
    return base_dir_for_owner(project, doc.owner)


def prefix_path(base_dir: str, rel_path: str) -> str:
    return f"{base_dir}/{rel_path}" if base_dir else rel_path


def is_valid_slug(slug: str) -> bool:
    return bool(_SLUG_RE.match(slug))


def translit_slug(name: str) -> str:
    """Слаг из ФИО: транслит первого (фамильного) слова, «Шалаев А.Д.» → "shalaev".

    Возвращает "" для пустых/несловесных имён — вызывающий обязан проверить
    is_valid_slug и потребовать явный слаг.
    """
    parts = name.strip().split()
    surname = parts[0].lower() if parts else ""
    out = "".join(_TRANSLIT.get(ch, ch if ch.isascii() and ch.isalnum() else "") for ch in surname)
    return out if is_valid_slug(out) else ""


def normalize_team_authors(authors: list[Author]) -> list[Author]:
    """Гарантирует авторам валидные уникальные слаги (для team-проекта).

    Пустой/невалидный слаг выводится транслитом фамилии; коллизии и
    зарезервированные имена разрешаются числовым суффиксом. Порядок сохранён.

    НЕ бросает: автор, для которого слаг вывести нельзя (пустое/несловесное
    имя), — это ЧЕРНОВИК из настроек (строку только что добавили и ещё не
    заполнили). Он сохраняется со slug=None и принудительно managed=False —
    комплект без слага вести нельзя; слаг появится сам, как только впишут имя.
    Строгую проверку «у ведомого автора обязан быть слаг» делает создание
    проекта (см. create_project), где черновиков быть не должно.
    """
    seen: set[str] = set(RESERVED_SLUGS)
    result: list[Author] = []
    for author in authors:
        slug = author.slug if author.slug and is_valid_slug(author.slug) else translit_slug(author.name)
        if not slug:
            result.append(replace(author, slug=None, managed=False))
            continue
        base = slug
        counter = 2
        while slug in seen:
            slug = f"{base}{counter}"
            counter += 1
        seen.add(slug)
        result.append(replace(author, slug=slug))
    return result


def managed_authors(project: Project) -> list[Author]:
    """Авторы, чьи комплекты ведутся в этом проекте (в порядке списка авторов)."""
    if not is_team(project):
        return list(project.authors)
    return [a for a in project.authors if a.managed and a.slug]


def project_bases(project: Project) -> list[tuple[str, Author | None]]:
    """Базы раскладки проекта: [(base_dir, владелец|None)].

    Solo → [("", None)] — корень, владелец подставляется рендером (authors[0]).
    Team → shared-база (если ведётся) + папка каждого ведомого автора.
    """
    if not is_team(project):
        return [("", None)]
    bases: list[tuple[str, Author | None]] = []
    if project.shared_enabled:
        bases.append((SHARED_DIR, None))
    bases.extend((a.slug, a) for a in managed_authors(project) if a.slug)
    return bases


def nda_bases(project: Project) -> list[tuple[str, Author | None]]:
    """Базы для расписки NDA — персонального документа (у каждого автора своя).

    Solo → [("", authors[0])] (корень; владелец = единственный автор). Team →
    папка каждого ведомого автора, БЕЗ shared-базы: общей расписки не бывает,
    каждый подписывает свою (со своей темой ВКР). Пусто, если авторов нет.
    """
    if is_team(project):
        return [(a.slug or "", a) for a in managed_authors(project) if a.slug]
    return [("", project.authors[0] if project.authors else None)]


def author_by_slug(project: Project, slug: str | None) -> Author | None:
    if slug is None:
        return None
    return next((a for a in project.authors if a.slug == slug), None)


def effective_meta(project: Project, author: Author | None) -> dict[str, Any]:
    """project.meta с наложенными авторскими значениями (scope=author поля).

    Для базы автора его непустые author.meta перекрывают одноимённые системные
    ключи; для shared-базы (author=None) возвращаются системные значения.
    """
    merged = dict(project.meta)
    if author is not None:
        merged.update({k: v for k, v in author.meta.items() if v not in (None, "")})
    return merged


# ── Руководства в комплекте (РП/РО) ──────────────────────────────────────────
# def_id руководств: программиста (rp) и оператора (ro). Выбор «Руководства в
# комплекте» (мета `manuals`, scope=author) определяет, какие из них входят в
# комплект автора: только РП, только РО или оба.
_MANUAL_DEF_IDS: frozenset[str] = frozenset({"programmer_manual", "operator_manual"})

# Расписка NDA как документ: активна только при включённом project.meta.nda.
_NDA_DEF_ID = "nda"


def active_manuals(project: Project, owner: str | None) -> set[str]:
    """Какие руководства (def_id rp/ro) входят в комплект владельца.

    Читает мета-поле `manuals` (значение — одна из фиксированных опций select)
    с учётом авторского перекрытия. Не задано → оба (дефолт). Пустой результат
    невозможен (fallback на оба) — «минимум одно» гарантировано.
    """
    if owner:
        author: Author | None = author_by_slug(project, owner)
    else:
        author = project.authors[0] if project.authors else None
    selection = str(effective_meta(project, author).get("manuals") or "").lower()
    if not selection:
        return set(_MANUAL_DEF_IDS)
    active: set[str] = set()
    if "программиста" in selection:
        active.add("programmer_manual")
    if "оператора" in selection:
        active.add("operator_manual")
    return active or set(_MANUAL_DEF_IDS)


def is_doc_active(project: Project, doc: Document) -> bool:
    """Активен ли документ в текущем составе проекта.

    False для:
    - расписки NDA (def_id "nda"), пока не включён `project.meta.nda` — так NDA
      работает как «полноценный документ, появляющийся при включении NDA»;
    - руководства (РП/РО), не выбранного его владельцем (мета `manuals`).

    Прочие документы всегда активны. Неактивный документ скрывается из списка
    документов IDE, из пакета сдачи и из агрегированного нормоконтроля; сам файл
    и его содержимое при этом НЕ удаляются — повторное включение всё возвращает.
    """
    if doc.def_id == _NDA_DEF_ID:
        return bool(project.meta.get("nda"))
    if doc.def_id not in _MANUAL_DEF_IDS:
        return True
    return doc.def_id in active_manuals(project, doc.owner)
