r"""Модель версии для форм Студии шаблонов и операции на несколько файлов (template-studio.md, 5.2–5.3, T11 и T12).

Порт `IPackVersionModel` (core/pack_studio/protocols.py):

* `describe`: манифест версии и `doc.yaml` документов как их читает `safe_load`, с ETag; файлы папок документов по
  языкам (грамматика суффиксов загрузчика, `_split_lang_qualifier`); где печатается каждое поле (тот же разбор, что у
  настроек проекта, `field_prints_by_document`); где манифест упоминает документ; находки лоадера и схемы;
* `check_edit`: правка формы не добавляет находок лоадера и схемы файлу (сравнение по счёту находок с индексами
  списков без номеров: вставка элемента сдвигает индексы старых находок, но не делает их новыми);
* `plan`: записи и удаления файлов для переименования поля, нового и удаляемого документа, перевода.

Всё читается под папкой паков без выхода по символьным ссылкам; записи делает сценарий через слой файлов (замок,
защита выпущенных версий, атомарная запись).
"""

from __future__ import annotations

import os
import re
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from hse_doc_studio.core.file_version import file_etag
from hse_doc_studio.core.meta_usage import PERSON_KEYS
from hse_doc_studio.core.pack_studio.errors import PackStudioError, PackStudioErrorCode
from hse_doc_studio.core.pack_studio.model import (
    LANG_CODE,
    DocFile,
    DocumentModel,
    FieldUsage,
    FileChange,
    LibraryDocument,
    ModelAction,
    ModelActionKind,
    ModelEditError,
    ModelFile,
    VersionModel,
    valid_doc_id,
    valid_field_key,
)
from hse_doc_studio.core.pack_studio.paths import TEMPLATES_DIR, VERSIONS_DIR
from hse_doc_studio.core.template_versions import parse_version_key
from hse_doc_studio.infra.pack_studio import pack_schemas
from hse_doc_studio.infra.pack_studio import yaml_edits as edits
from hse_doc_studio.infra.project_init.template_renderer import DEFAULT_TEMPLATE_LANG, _split_lang_qualifier
from hse_doc_studio.infra.template.yaml_template_repository import (
    _parse_document_definition,
    _parse_documents,
    _parse_form,
    _parse_meta_field,
    _parse_meta_groups,
    _parse_version,
)
from hse_doc_studio.use_cases.projects.project_fields import field_prints_by_document

VERSION_MANIFEST = "version.yaml"
DOC_MANIFEST = "doc.yaml"
FILES_DIR = "files"
CHECKS_DIR = "checks"
# Файлов в папке документа модель показывает не больше: больше форма и не разберёт.
MAX_DOC_FILES = 400
# Копия заготовки и перевод: столько файлов и байт за одну операцию.
MAX_COPY_FILES = 300
MAX_COPY_BYTES = 40 * 1024 * 1024
MAX_TEXT_BYTES = 2 * 1024 * 1024
# Заготовок из пространства не больше: список для выбора, а не каталог.
MAX_LIBRARY = 300
# Текстовые файлы версии, где переименование поля ищет ссылки `project.meta.<ключ>`.
_TEXT_SUFFIXES = frozenset({".tex", ".j2", ".md", ".html", ".txt", ".sty", ".cls", ".bib", ".typ"})
_LOADER: Any = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
_INDEX = re.compile(r"/\d+(?=/|:|$)")
_DOC_FILE = re.compile(r"^files/(?P<doc>[^/]+)/doc\.yaml$")


class PackVersionModel:
    """Порт `IPackVersionModel`: модель версии, проверка правки формы и план операций на несколько файлов."""

    def describe(self, root: Path, version_dir: str) -> VersionModel:
        vdir = _inside(root, version_dir)
        text = _read_text(vdir / VERSION_MANIFEST, f"{version_dir}/{VERSION_MANIFEST}")
        data = _parse(text)
        langs = _langs(data)
        documents = tuple(_documents(vdir, version_dir, data, langs))
        problems = [*_version_problems(text, vdir)]
        for doc in documents:
            if doc.manifest is not None:
                problems.extend(f"{doc.manifest.path}: {p}" for p in _doc_problems(_dump_check(doc), doc.id))
        return VersionModel(
            manifest=ModelFile(f"{version_dir}/{VERSION_MANIFEST}", file_etag(text.encode("utf-8")), data),
            documents=documents,
            usage=tuple(_usage(vdir, version_dir)),
            checks=tuple(sorted(p.stem for p in (vdir / CHECKS_DIR).glob("*.yaml") if p.is_file())),
            problems=tuple(problems),
        )

    def check_edit(self, root: Path, version_dir: str, file: str, before: str, after: str) -> None:
        vdir = _inside(root, version_dir)
        if file == VERSION_MANIFEST:
            old, new = _version_problems(before, vdir), _version_problems(after, vdir)
        else:
            found = _DOC_FILE.match(file)
            if found is None:
                raise ModelEditError(f"{file!r} is not a manifest of this version")
            old, new = _doc_problems(before, found["doc"]), _doc_problems(after, found["doc"])
        added = _new_problems(old, new)
        if added:
            raise ModelEditError(added[0][:300])

    def plan(self, root: Path, version_dir: str, action: ModelAction) -> tuple[FileChange, ...]:
        vdir = _inside(root, version_dir)
        text = _read_text(vdir / VERSION_MANIFEST, f"{version_dir}/{VERSION_MANIFEST}")
        data = _parse(text)
        plan = _Plan(root, vdir, version_dir, text, data)
        if action.kind is ModelActionKind.rename_field:
            return plan.rename_field(action.field or "", action.to or "")
        if action.kind is ModelActionKind.add_document:
            return plan.add_document(action.document or "", action.name or {}, action.source)
        if action.kind is ModelActionKind.remove_document:
            return plan.remove_document(action.document or "")
        return plan.add_translation(action.document or "", action.lang or "", action.files)

    def library(self, root: Path) -> tuple[LibraryDocument, ...]:
        base = root.resolve()
        found: list[LibraryDocument] = []
        for (pack, template), vdir in sorted(_latest_versions(base).items()):
            for doc_yaml in sorted((vdir / FILES_DIR).glob(f"*/{DOC_MANIFEST}")):
                if doc_yaml.is_symlink() or doc_yaml.parent.is_symlink():
                    continue
                found.append(
                    LibraryDocument(
                        path=doc_yaml.parent.relative_to(base).as_posix(),
                        pack=pack,
                        template=template,
                        version=vdir.name,
                        id=doc_yaml.parent.name,
                        name=_localized(_safe_mapping(doc_yaml).get("name")),
                    )
                )
                if len(found) >= MAX_LIBRARY:
                    return tuple(found)
        return tuple(found)


def _latest_versions(base: Path) -> dict[tuple[str, str], Path]:
    """Каталог последней версии каждого шаблона пространства (по номеру `ГОД.MINOR.PATCH`)."""
    latest: dict[tuple[str, str], tuple[tuple[int, int, int], Path]] = {}
    for vdir in base.glob(f"*/{TEMPLATES_DIR}/*/{VERSIONS_DIR}/*"):
        key = parse_version_key(vdir.name)
        if key is None or not vdir.is_dir() or vdir.is_symlink():
            continue
        name = (vdir.parts[-5], vdir.parts[-3])
        if name not in latest or latest[name][0] < key:
            latest[name] = (key, vdir)
    return {name: vdir for name, (_, vdir) in latest.items()}


# ── чтение ──────────────────────────────────────────────────────────────────


def _inside(root: Path, rel: str) -> Path:
    """Путь под папкой паков без выхода наружу через символьные ссылки."""
    base = root.resolve()
    target = (root / rel).resolve()
    if target != base and base not in target.parents:
        raise PackStudioError(PackStudioErrorCode.path_not_allowed)
    return target


def _read_text(path: Path, rel: str) -> str:
    if path.is_symlink():
        raise PackStudioError(PackStudioErrorCode.path_not_allowed)
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise PackStudioError(PackStudioErrorCode.file_not_found, path=rel) from None
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"{rel}: {exc}") from None


def _parse(text: str) -> Any:
    try:
        data = yaml.load(text, Loader=_LOADER)  # noqa: S506 — безопасный загрузчик
    except yaml.YAMLError as exc:
        raise ValueError(f"not valid YAML: {_one_line(exc)}") from None
    return pack_schemas.as_json(data if data is not None else {})


def _safe_mapping(path: Path) -> dict[str, Any]:
    try:
        data = yaml.load(path.read_text(encoding="utf-8"), Loader=_LOADER)  # noqa: S506 — безопасный загрузчик
    except (OSError, UnicodeDecodeError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def _one_line(exc: BaseException) -> str:
    return " ".join(str(exc).split())[:300]


def _localized(value: Any) -> dict[str, str]:
    if isinstance(value, Mapping):
        return {str(k): str(v) for k, v in value.items() if isinstance(v, str | int | float)}
    if isinstance(value, str):
        return {DEFAULT_TEMPLATE_LANG: value}
    return {}


def _langs(data: Any) -> tuple[str, ...]:
    raw = data.get("langs") if isinstance(data, dict) else None
    codes = tuple(dict.fromkeys(str(c).lower() for c in raw if isinstance(c, str) and c.strip())) if raw else ()
    return codes or (DEFAULT_TEMPLATE_LANG,)


def _roster(data: Any) -> list[Any]:
    raw = data.get("documents") if isinstance(data, dict) else None
    return raw if isinstance(raw, list) else []


def _roster_id(entry: Any) -> str | None:
    if isinstance(entry, str):
        return entry.strip()
    if isinstance(entry, dict) and isinstance(entry.get("id"), str):
        return str(entry["id"])
    return None


def _documents(vdir: Path, version_dir: str, data: Any, langs: tuple[str, ...]) -> Iterator[DocumentModel]:
    for entry in _roster(data):
        doc_id = _roster_id(entry)
        if not doc_id:
            continue
        refs = tuple(_references(data, doc_id))
        if not isinstance(entry, str):
            yield DocumentModel(id=doc_id, manifest=None, data=entry, files=(), references=refs)
            continue
        folder = vdir / FILES_DIR / doc_id
        manifest: ModelFile | None = None
        doc_data: Any = None
        doc_yaml = folder / DOC_MANIFEST
        if doc_yaml.is_file() and not doc_yaml.is_symlink():
            raw = doc_yaml.read_bytes()
            try:
                doc_data = _parse(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                doc_data = None
            rel = f"{version_dir}/{FILES_DIR}/{doc_id}/{DOC_MANIFEST}"
            manifest = ModelFile(rel, file_etag(raw), doc_data)
        yield DocumentModel(
            id=doc_id,
            manifest=manifest,
            data=doc_data,
            files=tuple(_doc_files(vdir / FILES_DIR, folder, langs)),
            references=refs,
        )


def _doc_files(files_dir: Path, folder: Path, langs: tuple[str, ...]) -> Iterator[DocFile]:
    if not folder.is_dir() or folder.is_symlink():
        return
    count = 0
    for path in _walk(folder):
        if path.name == DOC_MANIFEST and path.parent == folder:
            continue
        rel = path.relative_to(files_dir).as_posix()
        bare, lang = _split_lang_qualifier(rel, langs)
        yield DocFile(path=rel, bare=bare, lang=lang, size=path.stat().st_size)
        count += 1
        if count >= MAX_DOC_FILES:
            return


def _walk(folder: Path) -> Iterator[Path]:
    """Файлы папки по алфавиту, без символьных ссылок и служебных имён."""
    for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and not Path(dirpath, d).is_symlink())
        for name in sorted(filenames):
            path = Path(dirpath, name)
            if not name.startswith(".") and not path.is_symlink() and path.is_file():
                yield path


def _references(data: Any, doc_id: str) -> Iterator[str]:
    """Где манифест версии называет документ: слоты подписей, места, метки даты, профили сдачи."""
    if not isinstance(data, dict):
        return
    signatures = data.get("signatures")
    for slot in signatures.get("slots") or [] if isinstance(signatures, dict) else []:
        if isinstance(slot, dict):
            yield from _slot_references(slot, doc_id)
    submission = data.get("pack_submission")
    for profile in submission.get("profiles") or [] if isinstance(submission, dict) else []:
        if isinstance(profile, dict):
            yield from _profile_references(profile, doc_id)
    requirements = data.get("requirements")
    if isinstance(requirements, dict) and doc_id in (requirements.get("definition_docs") or []):
        yield "requirements.definition_docs"


def _slot_references(slot: dict[str, Any], doc_id: str) -> Iterator[str]:
    name = slot.get("id", "?")
    if isinstance(slot.get("applies_to"), list) and doc_id in slot["applies_to"]:
        yield f"signatures.slots[{name}].applies_to"
    for key in ("placements", "default_dates"):
        if isinstance(slot.get(key), dict) and doc_id in slot[key]:
            yield f"signatures.slots[{name}].{key}.{doc_id}"


def _profile_references(profile: dict[str, Any], doc_id: str) -> Iterator[str]:
    name = profile.get("id", "?")
    for key in ("items", "signing_slots"):
        entries = profile.get(key)
        if isinstance(entries, list) and any(isinstance(i, dict) and i.get("doc_id") == doc_id for i in entries):
            yield f"pack_submission.profiles[{name}].{key}"


def _usage(vdir: Path, version_dir: str) -> Iterator[FieldUsage]:
    """Где печатается поле: тот же разбор исходников, что у настроек проекта (по модели лоадера)."""
    parts = version_dir.split("/")
    version = _parse_version(vdir, parts[0], parts[2])
    if version is None:
        return
    prints = field_prints_by_document(version, version.documents, vdir / FILES_DIR)
    for doc in version.documents:
        doc_prints = prints.get(doc.id)
        if doc_prints is None:
            continue
        for key in sorted(doc_prints.keys):
            yield FieldUsage(
                field=key,
                document=doc.id,
                macros=tuple(sorted(doc_prints.macros.get(key, ()))),
                direct=key in doc_prints.direct,
                whole=key in doc_prints.whole,
            )


# ── находки лоадера и схемы ─────────────────────────────────────────────────


def _dump_check(doc: DocumentModel) -> str:
    """Текст `doc.yaml` для подсчёта находок модели: данные снова в YAML (комментарии здесь не нужны)."""
    return yaml.safe_dump(doc.data, allow_unicode=True) if doc.data is not None else ""


def _new_problems(old: list[str], new: list[str]) -> list[str]:
    """Находки, которых до правки не было (индексы списков не в счёт: вставка сдвигает старые)."""
    before = Counter(_INDEX.sub("/*", p) for p in old)
    added: list[str] = []
    for problem in new:
        key = _INDEX.sub("/*", problem)
        if before[key] > 0:
            before[key] -= 1
        else:
            added.append(problem)
    return added


def _version_problems(text: str, vdir: Path) -> list[str]:
    try:
        data = yaml.load(text, Loader=_LOADER)  # noqa: S506 — безопасный загрузчик
    except yaml.YAMLError as exc:
        return [f"version.yaml is not valid YAML: {_one_line(exc)}"]
    if not isinstance(data, dict):
        return ["version.yaml must be a mapping"]
    found = [f"{p}: {m}" for p, m in _schema("version", data)]
    found.extend(_loader_problems(data, vdir))
    return found


def _doc_problems(text: str, doc_id: str) -> list[str]:
    try:
        data = yaml.load(text, Loader=_LOADER) if text else {}  # noqa: S506 — безопасный загрузчик
    except yaml.YAMLError as exc:
        return [f"doc.yaml is not valid YAML: {_one_line(exc)}"]
    if not isinstance(data, dict):
        return ["doc.yaml must be a mapping"]
    found = [f"{p}: {m}" for p, m in _schema("doc", data)]
    if data.get("id") is not None and str(data["id"]) != doc_id:
        found.append(f"/id: {data['id']!r} differs from the folder name {doc_id!r}")
    try:
        _parse_document_definition({**data, "id": doc_id})
    except Exception as exc:  # noqa: BLE001 — любая ошибка разбора лоадера это находка
        found.append(f"/: the loader rejects the document: {_one_line(exc)}")
    return found


def _schema(name: str, data: Any) -> list[tuple[str, str]]:
    return [(pack_schemas.pointer_of(path), message) for path, message in pack_schemas.validation_errors(name, data)]


def _loader_problems(data: dict[str, Any], vdir: Path) -> Iterator[str]:
    """Что лоадер отбросит молча: поле анкеты, группа, анкета, её секция или поле; ростер документов целиком."""
    fields = data.get("meta_fields")
    for key, spec in fields.items() if isinstance(fields, dict) else ():
        try:
            _parse_meta_field(spec)
        except Exception as exc:  # noqa: BLE001 — любая ошибка разбора лоадера это находка
            yield f"/meta_fields/{key}: the loader drops the field: {_one_line(exc)}"
    try:
        _parse_meta_groups(data.get("meta_groups") or [])
    except Exception as exc:  # noqa: BLE001
        yield f"/meta_groups: the loader rejects the groups: {_one_line(exc)}"
    forms = data.get("forms")
    for index, raw in enumerate(forms if isinstance(forms, list) else []):
        yield from _form_problems(index, raw)
    try:
        _parse_documents(data, vdir)
    except Exception as exc:  # noqa: BLE001
        yield f"/documents: the loader rejects the version: {_one_line(exc)}"


def _form_problems(index: int, raw: Any) -> Iterator[str]:
    where = f"/forms/{index}"
    parsed = _parse_form(raw) if isinstance(raw, dict) else None
    if parsed is None:
        yield f"{where}: the loader drops the form"
        return
    sections = [s for s in raw.get("sections") or [] if s is not None]
    kept = {section.id: section for section in parsed.sections}
    for s_index, section in enumerate(sections):
        if not isinstance(section, dict) or str(section.get("id")) not in kept:
            yield f"{where}/sections/{s_index}: the loader drops the section"
            continue
        fields = section.get("fields") or []
        if len(kept[str(section["id"])].fields) != len(fields):
            yield f"{where}/sections/{s_index}/fields: the loader drops a field"


# ── операции на несколько файлов ────────────────────────────────────────────


class _Plan:
    def __init__(self, root: Path, vdir: Path, version_dir: str, text: str, data: Any) -> None:
        self.root = root
        self.vdir = vdir
        self.version_dir = version_dir
        self.text = text
        self.data = data if isinstance(data, dict) else {}
        self.langs = _langs(self.data)

    def _rel(self, *parts: str) -> str:
        return "/".join((self.version_dir, *parts))

    def _manifest_change(self, new_text: str) -> FileChange:
        added = _new_problems(_version_problems(self.text, self.vdir), _version_problems(new_text, self.vdir))
        if added:
            raise ModelEditError(added[0][:300])
        return FileChange(self._rel(VERSION_MANIFEST), new_text.encode("utf-8"))

    # ── поле ──

    def rename_field(self, field: str, to: str) -> tuple[FileChange, ...]:
        self._check_rename(field, to)
        try:
            new_text = edits.rename_key(self.text, ("meta_fields", field), to)
        except edits.YamlEditError as exc:
            raise ModelEditError(str(exc)) from None
        return (self._manifest_change(new_text), *self._renamed_refs(field, to))

    def _check_rename(self, field: str, to: str) -> None:
        fields = self.data.get("meta_fields")
        if not isinstance(fields, dict) or field not in fields:
            raise ModelEditError(f"field {field!r} is not in meta_fields")
        if field in PERSON_KEYS:
            raise ModelEditError(f"{field!r} is a person of the project and keeps its key")
        if not valid_field_key(to) or to in PERSON_KEYS:
            raise ModelEditError(f"{to!r} is not a valid field key")
        if to in fields:
            raise ModelEditError(f"field {to!r} already exists")

    def _renamed_refs(self, field: str, to: str) -> Iterator[FileChange]:
        """Текстовые файлы версии, где ссылки на поле получили новый ключ."""
        pattern = _field_refs(field)
        files_dir = self.vdir / FILES_DIR
        for path in _walk(files_dir) if files_dir.is_dir() else ():
            source = _small_text(path)
            if source is None:
                continue
            renamed = pattern.sub(lambda m: _renamed(m.group(0), field, to), source)
            if renamed != source:
                yield FileChange(self._rel(path.relative_to(self.vdir).as_posix()), renamed.encode("utf-8"))

    # ── документы ──

    def _roster_index(self, doc_id: str) -> int | None:
        for index, entry in enumerate(_roster(self.data)):
            if _roster_id(entry) == doc_id:
                return index
        return None

    def add_document(self, doc_id: str, name: Mapping[str, str], source: str | None) -> tuple[FileChange, ...]:
        if not valid_doc_id(doc_id):
            raise ModelEditError(f"{doc_id!r} is not a valid document id")
        if self._roster_index(doc_id) is not None or (self.vdir / FILES_DIR / doc_id).exists():
            raise ModelEditError(f"document {doc_id!r} already exists")
        roster = _roster(self.data)
        try:
            if "documents" in self.data and isinstance(self.data.get("documents"), list):
                new_text = edits.insert_item(self.text, ("documents",), len(roster), doc_id)
            else:
                new_text = edits.set_value(self.text, ("documents",), [doc_id], block=True)
        except edits.YamlEditError as exc:
            raise ModelEditError(str(exc)) from None
        label = {k: v.strip() for k, v in name.items() if isinstance(v, str) and v.strip()}
        files = self._copied(doc_id, source, label) if source else self._blank(doc_id, label)
        return (*files, FileChange(self._rel(VERSION_MANIFEST), new_text.encode("utf-8")))

    def _blank(self, doc_id: str, label: Mapping[str, str]) -> list[FileChange]:
        names = dict(label) or {self.langs[0]: doc_id}
        manifest: dict[str, Any] = {
            "name": names,
            "source_file": f"{doc_id}/{doc_id}.tex",
            "output_file": f"{doc_id}/{doc_id}.pdf",
            "output_name": {lang: f"{value}.pdf" for lang, value in names.items()},
            "required": False,
            "supported_langs": list(self.langs),
            "scope": "shared",
        }
        header = (
            "# Манифест документа (bundle-раскладка v2): всё про документ в этой папке.\n"
            "# Языковые редакции это файлы-соседи <stem>.<код>.<ext>; файл без кода служит всем языкам.\n"
        )
        doc_yaml = header + yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False, width=10_000)
        title = names.get(self.langs[0]) or next(iter(names.values()))
        return [
            FileChange(self._rel(FILES_DIR, doc_id, DOC_MANIFEST), doc_yaml.encode("utf-8")),
            FileChange(self._rel(FILES_DIR, doc_id, f"{doc_id}.tex"), _blank_tex(title, self._includes()).encode()),
        ]

    def _includes(self) -> list[str]:
        """Динамические инклуды версии, которые новый документ подключает: шрифты и макросы полей."""
        outputs = []
        for item in self.data.get("dynamic_includes") or []:
            output = item.get("output") if isinstance(item, dict) else None
            if isinstance(output, str) and output.endswith(".tex"):
                outputs.append(output.removesuffix(".tex"))
        return outputs

    def _copied(self, doc_id: str, source: str, label: Mapping[str, str]) -> list[FileChange]:
        src = _inside(self.root, source)
        parts = PurePosixPath(source).parts
        if (
            len(parts) != 7  # noqa: PLR2004 — <пак>/templates/<шаблон>/versions/<в>/files/<id>
            or parts[1] != TEMPLATES_DIR
            or parts[3] != VERSIONS_DIR
            or parts[5] != FILES_DIR
            or not (src / DOC_MANIFEST).is_file()
        ):
            raise ModelEditError(f"{source!r} is not a document folder of a pack version")
        src_id = parts[6]
        changes: list[FileChange] = []
        total = 0
        for path in _walk(src):
            rel = path.relative_to(src).as_posix()
            content = path.read_bytes()
            total += len(content)
            if len(changes) >= MAX_COPY_FILES or total > MAX_COPY_BYTES:
                raise ModelEditError("the document folder is too large to copy")
            if rel == DOC_MANIFEST:
                content = _retarget_doc(content.decode("utf-8"), src_id, doc_id, label).encode("utf-8")
            changes.append(FileChange(self._rel(FILES_DIR, doc_id, rel), content))
        return changes

    def remove_document(self, doc_id: str) -> tuple[FileChange, ...]:
        index = self._roster_index(doc_id)
        if index is None:
            raise ModelEditError(f"document {doc_id!r} is not in the roster")
        try:
            new_text = edits.delete(self.text, ("documents", index))
        except edits.YamlEditError as exc:
            raise ModelEditError(str(exc)) from None
        changes = [FileChange(self._rel(VERSION_MANIFEST), new_text.encode("utf-8"))]
        folder = self.vdir / FILES_DIR / doc_id
        if isinstance(_roster(self.data)[index], str) and folder.is_dir() and not folder.is_symlink():
            changes.insert(0, FileChange(self._rel(FILES_DIR, doc_id), None))
        return tuple(changes)

    # ── перевод ──

    def add_translation(self, doc_id: str, lang: str, files: tuple[str, ...]) -> tuple[FileChange, ...]:
        self._check_translation(doc_id, lang)
        default = self.langs[0]
        files_dir = self.vdir / FILES_DIR
        groups: dict[str, dict[str, DocFile]] = {}
        for item in _doc_files(files_dir, files_dir / doc_id, self.langs):
            groups.setdefault(item.bare, {})[item.lang] = item
        wanted = set(files)
        unknown = sorted(wanted - set(groups))
        if unknown:
            raise ModelEditError(f"no such files in the document: {unknown}")
        changes: list[FileChange] = []
        for bare, by_lang in groups.items():
            if lang not in by_lang and (not wanted or bare in wanted) and not bare.endswith(".j2"):
                changes.extend(self._translated(bare, by_lang, lang, default, explicit=bare in wanted))
        if not changes:
            raise ModelEditError("nothing to translate: every file already has this language or serves all")
        changes.extend(self._doc_lang(doc_id, lang))
        return tuple(changes)

    def _check_translation(self, doc_id: str, lang: str) -> None:
        if not LANG_CODE.match(lang) or lang not in self.langs:
            raise ModelEditError(f"{lang!r} is not a language of this version (langs: {list(self.langs)})")
        if lang == self.langs[0]:
            raise ModelEditError(f"{lang!r} is the default language: its edition is the source of translations")
        index = self._roster_index(doc_id)
        if index is None or not isinstance(_roster(self.data)[index], str):
            raise ModelEditError(f"document {doc_id!r} is not a bundle of this version")

    def _translated(
        self, bare: str, by_lang: Mapping[str, DocFile], lang: str, default: str, *, explicit: bool
    ) -> list[FileChange]:
        """Перевод одной группы файлов: копия редакции по умолчанию; файл для всех языков только по явной просьбе."""
        if default in by_lang:
            return [self._copy(by_lang[default].path, _with_lang(bare, lang))]
        if "" in by_lang and explicit:
            # Файл без кода служил всем языкам: он становится редакцией языка по умолчанию и её переводом.
            shared = by_lang[""].path
            return [
                self._copy(shared, _with_lang(bare, default)),
                self._copy(shared, _with_lang(bare, lang)),
                FileChange(self._rel(FILES_DIR, shared), None),
            ]
        return []

    def _copy(self, src_rel: str, dst_rel: str) -> FileChange:
        if not dst_rel:
            raise ModelEditError(f"{src_rel!r} has no extension for a language code")
        content = (self.vdir / FILES_DIR / src_rel).read_bytes()
        if len(content) > MAX_COPY_BYTES:
            raise ModelEditError(f"{src_rel!r} is too large to copy")
        return FileChange(self._rel(FILES_DIR, dst_rel), content)

    def _doc_lang(self, doc_id: str, lang: str) -> list[FileChange]:
        """Код языка в `supported_langs` документа, если список там есть и кода нет."""
        path = self.vdir / FILES_DIR / doc_id / DOC_MANIFEST
        if not path.is_file() or path.is_symlink():
            return []
        text = path.read_text(encoding="utf-8")
        data = _parse(text)
        current = data.get("supported_langs") if isinstance(data, dict) else None
        if not isinstance(current, list) or not current or lang in current:
            return []
        try:
            new_text = edits.insert_item(text, ("supported_langs",), len(current), lang)
        except edits.YamlEditError as exc:
            raise ModelEditError(str(exc)) from None
        return [FileChange(self._rel(FILES_DIR, doc_id, DOC_MANIFEST), new_text.encode("utf-8"))]


def _field_refs(field: str) -> re.Pattern[str]:
    """Ссылки на поле в шаблонах: `project.meta.x`, `author.meta.x`, `meta['x']`, `meta.get('x'`."""
    name = re.escape(field)
    return re.compile(
        rf"(?:\b(?:project|author)\.meta\.{name}\b)"
        rf"|(?:\b(?:project|author)\.meta\[\s*(['\"]){name}\1\s*\])"
        rf"|(?:\b(?:project|author)\.meta\.get\(\s*(['\"]){name}\2)"
    )


def _small_text(path: Path) -> str | None:
    """Текст шаблона версии для поиска ссылок; двоичный, чужой кодировки или большой: None."""
    if path.suffix.lower() not in _TEXT_SUFFIXES or path.stat().st_size > MAX_TEXT_BYTES:
        return None
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def _renamed(match: str, field: str, to: str) -> str:
    """Имя поля в найденной ссылке: последнее вхождение (`project.meta.meta` меняет только ключ)."""
    at = match.rfind(field)
    return match[:at] + to + match[at + len(field) :]


def _with_lang(bare: str, lang: str) -> str:
    """`report/report.tex` с кодом `en`: `report/report.en.tex`; без расширения: ""."""
    parent, _, name = bare.rpartition("/")
    stem, dot, ext = name.rpartition(".")
    if not dot or not stem:
        return ""
    return f"{parent}/{stem}.{lang}.{ext}" if parent else f"{stem}.{lang}.{ext}"


def _retarget_doc(text: str, src_id: str, doc_id: str, label: Mapping[str, str]) -> str:
    """`doc.yaml` заготовки под новый id: пути `<старый>/...` в `<новый>/...`, `id` и название, если задано."""
    data = yaml.load(text, Loader=_LOADER) or {}  # noqa: S506 — безопасный загрузчик
    if not isinstance(data, dict):
        raise ModelEditError("doc.yaml of the source is not a mapping")
    changes: list[tuple[tuple[str | int, ...], Any]] = [(("id",), doc_id)] if "id" in data else []
    changes.extend(_moved_paths(data, (), f"{src_id}/", doc_id))
    variants = data.get("variants") or []
    for index, variant in enumerate(variants if isinstance(variants, list) else []):
        changes.extend(_moved_paths(variant, ("variants", index), f"{src_id}/", doc_id))
    if label:
        changes.append((("name",), dict(label)))
    try:
        for path, value in changes:
            text = edits.set_value(text, path, value)
    except edits.YamlEditError as exc:
        raise ModelEditError(str(exc)) from None
    return text


def _moved_paths(
    entry: Any, at: tuple[str | int, ...], prefix: str, doc_id: str
) -> Iterator[tuple[tuple[str | int, ...], str]]:
    """`source_file` и `output_file` записи, которые лежали в папке заготовки: тот же путь в папке нового id."""
    if not isinstance(entry, Mapping):
        return
    for key in ("source_file", "output_file"):
        value = entry.get(key)
        if isinstance(value, str) and value.startswith(prefix):
            yield (*at, key), f"{doc_id}/{value[len(prefix) :]}"


def _blank_tex(title: str, includes: Iterable[str]) -> str:
    lines = [
        "% !TeX program = xelatex",
        f"% {title}: новый документ пака. Замените содержимое своим.",
        r"\documentclass[12pt,a4paper]{article}",
        r"\usepackage{fontspec}",
        *(rf"\input{{../{output}}}" for output in includes),
        r"\begin{document}",
        "",
        rf"\section*{{{_tex_escape(title)}}}",
        "",
        "Текст документа.",
        "",
        r"\end{document}",
        "",
    ]
    return "\n".join(lines)


def _tex_escape(text: str) -> str:
    out = []
    for ch in text:
        if ch in "&%$#_{}":
            out.append("\\" + ch)
        elif ch in "~^\\":
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)
