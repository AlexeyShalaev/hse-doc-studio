from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from hse_doc_studio.core.catalog import TemplateVersion

# Patterns written verbatim into <git-dir>/info/exclude at init (and refreshed on
# connect). The version history holds the user's WORK — source documents,
# project settings, signatures and forms — and nothing else. Everything that is
# derived, generated, transient, or belongs to a different feature is excluded so
# that "compiled but didn't edit anything" never registers as a change (no
# million-entry history). PDFs are excluded per-commit via an :(exclude)*.pdf
# pathspec so the track_pdf toggle never has to rewrite this file.
DEFAULT_VCS_EXCLUDE: tuple[str, ...] = (
    "# LaTeX intermediates",
    "*.aux",
    "*.log",
    "*.synctex.gz",
    "*.out",
    "*.toc",
    "*.fls",
    "*.fdb_latexmk",
    "*.bbl",
    "*.blg",
    "*.nav",
    "*.snm",
    "*.vrb",
    "*.lof",
    "*.lot",
    "*.idx",
    "*.ind",
    "*.ilg",
    "*.run.xml",
    "# build dirs",
    ".build/",
    "**/.build/",
    "# generated from project.json before every compile (derived, not authored)",
    "common/meta.tex",
    "# the ChangeLog journal — a separate human log, not source",
    ".hse-studio/history.json",
    "# submission packaging — a separate feature, not version history",
    "submissions/",
    ".hse-studio/submissions/",
    "# our own store + a foreign user git",
    ".hse-studio/git/",
    # без слеша: ловит и файл вместо каталога (указатель на вынесенное хранилище)
    ".hse-studio/git",
    ".git/",
    ".gitmodules",
    "# hse-studio caches (sources stay tracked)",
    ".hse-studio/compiles/",
    ".hse-studio/chats/",
    "# template update journal and pre-migration backups — transaction state, not work",
    ".hse-studio/update/",
    ".hse-studio/backup/",
    "# временный файл записи применения: остаётся только после сбоя и в историю не идёт",
    "*.hse-update.tmp",
)


# Содержимое <git-dir>/info/attributes. Это самый сильный источник атрибутов: он перекрывает `.gitattributes` из
# рабочей папки, который приезжает с чужой веткой. Без него `working-tree-encoding`, `eol`, `ident` и `filter`
# из чужого файла меняют то, что попадает в коммит, или обрывают `git add` (BOM is required), и снимки перестают
# создаваться. Студия хранит файлы проекта байт в байт, поэтому все преобразования выключены.
VCS_ATTRIBUTES: str = "* -text -eol -ident -filter -working-tree-encoding\n"


def vcs_exclude_for(version: TemplateVersion | None) -> list[str]:
    """Исключения истории для проекта на версии шаблона `version`.

    Выходы dynamic include перегенерируются перед каждой сборкой — это не работа
    пользователя. Захардкоженный `common/meta.tex` выше покрывает только корень
    solo-проекта; здесь каждый выход версии исключается в любой базе раскладки
    (`shared/`, папки авторов) шаблоном `**/<выход>`.
    """
    patterns = list(DEFAULT_VCS_EXCLUDE)
    if version is not None and version.dynamic_includes:
        patterns.append("# dynamic includes of the template version (regenerated before every compile)")
        patterns += sorted({f"**/{inc.output.strip('/')}" for inc in version.dynamic_includes})
    return patterns
