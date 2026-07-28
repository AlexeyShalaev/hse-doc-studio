from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from hse_doc_studio.use_cases.projects.list_projects import ListProjectsUC

# How many folder roots to surface; the wizard shows the top few.
_MAX_FOLDER_ROOTS = 8


@dataclass(frozen=True)
class FolderRootSuggestion:
    path: str
    count: int


@dataclass(frozen=True)
class AuthorSuggestion:
    name: str
    group: str


@dataclass
class ProjectSuggestionsOutput:
    folder_roots: list[FolderRootSuggestion]
    authors: list[AuthorSuggestion]


class GetProjectSuggestionsUC:
    """Aggregates create-wizard hints from existing projects: the parent folders
    projects live under (ranked by how many projects sit in each — so the user
    can reuse a common location) and every distinct author (ranked by how often
    they appear — so co-authors autocomplete)."""

    def __init__(self, list_projects: ListProjectsUC, default_projects_dir: Path) -> None:
        self._list_projects = list_projects
        # `<data_dir>/projects` — создаётся приложением на старте, чтобы у
        # свежей установки сразу было готовое место под работы.
        self._default_projects_dir = default_projects_dir

    async def execute(self) -> ProjectSuggestionsOutput:
        projects = (await self._list_projects.execute()).projects

        # Parent dir of each project folder = the location the user keeps
        # projects in. Ranked by project count, most-used first.
        folder_counts: Counter[str] = Counter(str(p.folder.parent) for p in projects)
        folder_roots = [
            FolderRootSuggestion(path=path, count=count) for path, count in folder_counts.most_common(_MAX_FOLDER_ROOTS)
        ]

        # Дефолтный корень в конце: привычные пользователю места (по числу
        # проектов) важнее, но у пустой установки должен быть хотя бы один чип.
        default = self._default_projects_dir
        if default.is_dir() and str(default) not in {r.path for r in folder_roots}:
            folder_roots.append(FolderRootSuggestion(path=str(default), count=0))

        # Distinct authors (by name + group), ranked by frequency across all
        # projects. Blank names (draft/system rows) are dropped.
        author_counts: Counter[tuple[str, str]] = Counter()
        for p in projects:
            for a in p.authors:
                name = a.name.strip()
                if name:
                    author_counts[(name, (a.group or "").strip())] += 1
        authors = [AuthorSuggestion(name=name, group=group) for (name, group), _ in author_counts.most_common()]

        return ProjectSuggestionsOutput(folder_roots=folder_roots, authors=authors)
