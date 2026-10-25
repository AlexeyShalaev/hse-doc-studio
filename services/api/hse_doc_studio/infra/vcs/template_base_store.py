"""Базы обновления шаблона в скрытом git проекта (core.template_update).

База версии — коммит в `refs/hse/template/<версия>`, дерево которого — чистый
рендер этой версии шаблона для проекта. Ссылка лежит вне `refs/heads` и
`refs/tags`: в ветках, тегах и истории интерфейса её не видно, а коммиты не
мешают пользовательскому git. Дерево собирается из временного каталога во
временный индекс — рабочее дерево и индекс проекта не задеваются.

Происхождение базы и приблизительные пути записаны трейлерами сообщения:
`Hse-Base-Provenance: recorded` и `Hse-Base-Approximate: <путь>`.
"""

from __future__ import annotations

import json
import re
import tempfile
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path

import structlog

from hse_doc_studio.core.entities import Project
from hse_doc_studio.core.enums import TemplateBaseProvenance
from hse_doc_studio.core.template_update.entities import TemplateBase
from hse_doc_studio.core.template_update.protocols import RootSnapshot
from hse_doc_studio.infra.persistence.serializers import deserialize_project
from hse_doc_studio.infra.vcs.git_vcs_service import GitVcsService

logger = structlog.get_logger()

TEMPLATE_BASE_REF_PREFIX = "refs/hse/template/"
_STUDIO_PREFIX = ".hse-studio/"
_PROJECT_JSON = ".hse-studio/project.json"

_PROVENANCE_RE = re.compile(r"^Hse-Base-Provenance:\s*(\S+)\s*$", re.MULTILINE)
_APPROXIMATE_RE = re.compile(r"^Hse-Base-Approximate:\s*(.+?)\s*$", re.MULTILINE)


def base_ref(version: str) -> str:
    return f"{TEMPLATE_BASE_REF_PREFIX}{version}"


def _project_from(raw: bytes | None, folder: Path) -> Project | None:
    if raw is None:
        return None
    try:
        data = json.loads(raw.decode("utf-8"))
        return deserialize_project(data, folder=folder) if isinstance(data, dict) else None
    except (ValueError, KeyError, TypeError):
        return None


class GitTemplateBaseStore:
    def __init__(self, vcs: GitVcsService) -> None:
        self._vcs = vcs

    # ── чтение ───────────────────────────────────────────────────────────────
    def _rev(self, project: Project, rev: str) -> str | None:
        proc = self._vcs.run_bytes(project, ["rev-parse", "--verify", "-q", f"{rev}^{{commit}}"], check=False)
        out = proc.stdout.decode().strip()
        return out if proc.returncode == 0 and out else None

    def head(self, project: Project) -> str | None:
        if not self._vcs.is_initialized(project):
            return None
        return self._rev(project, "HEAD")

    def commit_message(self, project: Project, commit: str) -> str:
        proc = self._vcs.run_bytes(project, ["log", "-1", "--format=%B", commit])
        return proc.stdout.decode("utf-8", "replace")

    def is_ancestor(self, project: Project, ancestor: str, descendant: str) -> bool:
        proc = self._vcs.run_bytes(project, ["merge-base", "--is-ancestor", ancestor, descendant], check=False)
        return proc.returncode == 0

    def _tree_entries(self, project: Project, treeish: str) -> dict[str, tuple[str, str]]:
        """Путь → (режим, id блоба) по всему дереву коммита."""
        proc = self._vcs.run_bytes(project, ["ls-tree", "-r", "-z", "--full-tree", treeish])
        entries: dict[str, tuple[str, str]] = {}
        for record in proc.stdout.split(b"\x00"):
            if not record:
                continue
            meta, _, path = record.partition(b"\t")
            parts = meta.split()
            if len(parts) == 3 and parts[1] == b"blob":
                entries[path.decode("utf-8", "surrogateescape")] = (parts[0].decode(), parts[2].decode())
        return entries

    def _tree(self, project: Project, treeish: str) -> dict[str, str]:
        """Путь → id блоба по всему дереву коммита."""
        return {path: blob for path, (_mode, blob) in self._tree_entries(project, treeish).items()}

    def _blobs(self, project: Project, blob_ids: Iterable[str]) -> dict[str, bytes]:
        ids = list(dict.fromkeys(blob_ids))
        if not ids:
            return {}
        proc = self._vcs.run_bytes(
            project, ["cat-file", "--batch"], input_bytes="".join(f"{i}\n" for i in ids).encode()
        )
        out = proc.stdout
        blobs: dict[str, bytes] = {}
        pos = 0
        for blob_id in ids:
            header_end = out.index(b"\n", pos)
            header = out[pos:header_end].split()
            if len(header) < 3:  # "<id> missing"
                pos = header_end + 1
                continue
            size = int(header[2])
            start = header_end + 1
            blobs[blob_id] = out[start : start + size]
            pos = start + size + 1
        return blobs

    def _files(self, project: Project, entries: Mapping[str, str]) -> dict[str, bytes]:
        blobs = self._blobs(project, entries.values())
        return {path: blobs[blob] for path, blob in entries.items() if blob in blobs}

    def files_at(self, project: Project, commit: str, paths: Iterable[str]) -> dict[str, bytes]:
        wanted = set(paths)
        tree = self._tree(project, commit)
        return self._files(project, {p: b for p, b in tree.items() if p in wanted})

    def changed_paths(self, project: Project, from_commit: str, to_commit: str) -> list[str]:
        proc = self._vcs.run_bytes(project, ["diff", "--name-only", "-z", "--no-renames", from_commit, to_commit])
        return [p.decode("utf-8", "surrogateescape") for p in proc.stdout.split(b"\x00") if p]

    def load(self, project: Project, version: str) -> TemplateBase | None:
        if not self._vcs.is_initialized(project):
            return None
        commit = self._rev(project, base_ref(version))
        if commit is None:
            return None
        message = self.commit_message(project, commit)
        provenance_match = _PROVENANCE_RE.search(message)
        try:
            provenance = TemplateBaseProvenance(provenance_match.group(1)) if provenance_match else None
        except ValueError:
            provenance = None
        return TemplateBase(
            version=version,
            files=self._files(project, self._tree(project, commit)),
            provenance=provenance or TemplateBaseProvenance.approximate,
            commit=commit,
            approximate_paths=frozenset(_APPROXIMATE_RE.findall(message)),
        )

    def root_snapshot(self, project: Project) -> RootSnapshot | None:
        if self.head(project) is None:
            return None
        proc = self._vcs.run_bytes(project, ["rev-list", "--max-parents=0", "HEAD"])
        roots = proc.stdout.decode().split()
        if not roots:
            return None
        root = roots[-1]
        tree = self._tree(project, root)
        files = self._files(project, tree)
        return RootSnapshot(
            commit=root,
            message=self.commit_message(project, root),
            project=_project_from(files.get(_PROJECT_JSON), project.folder),
            files={path: data for path, data in files.items() if not path.startswith(_STUDIO_PREFIX)},
        )

    # ── запись ───────────────────────────────────────────────────────────────
    def save(self, project: Project, base: TemplateBase, *, message: str, set_ref: bool = True) -> str:
        """Записать базу коммитом (родитель — прежняя база этой версии) и, если
        `set_ref`, передвинуть на него ссылку версии."""
        parent = self._rev(project, base_ref(base.version))
        trailers = [f"Hse-Base-Provenance: {base.provenance.value}"]
        trailers += [f"Hse-Base-Approximate: {path}" for path in sorted(base.approximate_paths)]
        full_message = f"{message}\n\n" + "\n".join(trailers) + "\n"
        with tempfile.TemporaryDirectory(prefix="hse-template-base-") as tmp:
            work_tree = Path(tmp) / "tree"
            work_tree.mkdir()
            for rel, content in base.files.items():
                target = work_tree / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            index = Path(tmp) / "index"
            # -f: в базе бывают файлы, подпадающие под исключения истории (*.pdf,
            # ассеты) — база обязана хранить ровно то, что пишет шаблон.
            self._vcs.run_bytes(project, ["add", "-A", "-f", "--", "."], work_tree=work_tree, index_file=index)
            tree = self._vcs.run_bytes(project, ["write-tree"], work_tree=work_tree, index_file=index)
        args = ["commit-tree", tree.stdout.decode().strip(), "-F", "-"]
        if parent is not None:
            args += ["-p", parent]
        commit = self._vcs.run_bytes(project, args, input_bytes=full_message.encode()).stdout.decode().strip()
        if set_ref:
            self.set_ref(project, base.version, commit)
        logger.debug("template base saved", version=base.version, commit=commit, files=len(base.files))
        return commit

    def record_from_head(
        self, project: Project, version: str, keep: Callable[[str], bool], *, message: str
    ) -> str | None:
        """База из дерева HEAD (только пути, для которых `keep`) — без чтения блобов.

        Для только что созданного проекта: корневой коммит содержит ровно то, что
        записало создание, поэтому рендерить шаблон второй раз незачем.
        """
        head = self.head(project)
        if head is None:
            return None
        entries = {path: entry for path, entry in self._tree_entries(project, head).items() if keep(path)}
        index_info = "".join(f"{mode} {blob}\t{path}\n" for path, (mode, blob) in sorted(entries.items()))
        with tempfile.TemporaryDirectory(prefix="hse-template-base-") as tmp:
            index = Path(tmp) / "index"
            self._vcs.run_bytes(
                project, ["update-index", "--add", "--index-info"], input_bytes=index_info.encode(), index_file=index
            )
            tree = self._vcs.run_bytes(project, ["write-tree"], index_file=index).stdout.decode().strip()
        trailer = f"Hse-Base-Provenance: {TemplateBaseProvenance.recorded.value}"
        commit = (
            self._vcs.run_bytes(
                project, ["commit-tree", tree, "-F", "-"], input_bytes=f"{message}\n\n{trailer}\n".encode()
            )
            .stdout.decode()
            .strip()
        )
        self.set_ref(project, version, commit)
        return commit

    def set_ref(self, project: Project, version: str, commit: str) -> None:
        self._vcs.run_bytes(project, ["update-ref", base_ref(version), commit])

    def find_commit(self, project: Project, trailer: str, value: str) -> str | None:
        """Последний коммит текущей ветки с трейлером `<trailer>: <value>`."""
        if self.head(project) is None:
            return None
        proc = self._vcs.run_bytes(
            project, ["log", "-1", "--format=%H", "--fixed-strings", f"--grep={trailer}: {value}", "HEAD"], check=False
        )
        out = proc.stdout.decode().strip()
        return out or None
