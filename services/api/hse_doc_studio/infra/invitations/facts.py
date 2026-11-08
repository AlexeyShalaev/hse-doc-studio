"""Данные проекта для готового текста приглашения: люди и тема из `project.json`, вид работы и документы из шаблона."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import Lang
from hse_doc_studio.core.invitations.message import InvitationFacts, ProjectPerson
from hse_doc_studio.core.repositories import IProjectIndexLookup, IProjectIndexRepository, ITemplateRepository
from hse_doc_studio.core.value_objects import Person


def _pick(names: Mapping[str, str], lang: Lang) -> str | None:
    return names.get(lang.value) or names.get(Lang.ru.value) or next(iter(names.values()), None)


def _person(person: Person | None) -> ProjectPerson | None:
    return ProjectPerson(name=person.name) if person is not None and person.name.strip() else None


def _topic(project: Project) -> str | None:
    """Русское название работы, если проект назван иначе (поле пака `name_ru`)."""
    value = project.meta.get("name_ru")
    return value.strip() or None if isinstance(value, str) else None


class ProjectFileInvitationFacts:
    def __init__(self, index: IProjectIndexRepository, templates: ITemplateRepository) -> None:
        self._index = index
        self._templates = templates

    async def facts(self, project_id: UUID, lang: Lang) -> InvitationFacts | None:
        if not isinstance(self._index, IProjectIndexLookup):
            return None
        found = await self._index.locate(project_id)
        if found is None:
            return None
        project = found[1]
        work_kind, documents = self._template_facts(project, lang)
        supervisors = {
            persona: person
            for persona, person in (
                ("supervisor", _person(project.supervisor)),
                ("co_supervisor", _person(project.co_supervisor)),
                ("academic_supervisor", _person(project.academic_supervisor)),
            )
            if person is not None
        }
        return InvitationFacts(
            project_name=project.name,
            topic=_topic(project),
            work_kind=work_kind,
            documents=documents,
            authors=tuple(
                ProjectPerson(name=a.name, email=a.email, group=a.group, slug=a.slug)
                for a in project.authors
                if a.name.strip()
            ),
            supervisors=supervisors,
        )

    def _template_facts(self, project: Project, lang: Lang) -> tuple[str | None, tuple[str, ...]]:
        lock = project.lock
        info = next(
            (
                t
                for pack in self._templates.list_packs()
                if pack.id == lock.pack_id
                for t in pack.templates
                if t.id == lock.template_id
            ),
            None,
        )
        work_kind = _pick(info.name, lang) if info is not None else None
        version = self._templates.get_version(lock.pack_id, lock.template_id, lock.version)
        if version is None:
            return work_kind, ()
        names = {d.id: _pick(d.name, lang) for d in version.documents}
        seen: list[str] = []
        for doc in project.documents:
            name = names.get(doc.def_id)
            if name and name not in seen:
                seen.append(name)
        return work_kind, tuple(seen)
