"""Каталоги-владельцы определений документов.

Bundle-раскладка пака: дерево `files/` СОВПАДАЕТ с деревом проекта
(`files/<doc_id>/…` материализуется в `<doc_id>/…`), поэтому пути source_file
уже в проектном пространстве и никакого ремапа не существует. Здесь — только
вычисление каталогов, которыми владеет определение (сам док + все варианты):
инстанциация (skip-логика, довключение недостающих доков) и атрибуция файлов
к документам обязаны пользоваться одними и теми же функциями.
"""

from __future__ import annotations

from hse_doc_studio.core.catalog import DocumentDefinition


def _posix_parent(path: str) -> str:
    """Posix-каталог rel-пути ('' для файла верхнего уровня)."""
    normalized = str(path).replace("\\", "/").strip("/")
    return normalized.rsplit("/", 1)[0] if "/" in normalized else ""


def def_dirs(doc_def: DocumentDefinition) -> set[str]:
    """Каталоги всех source-файлов определения (сам док + варианты)."""
    dirs: set[str] = set()
    for source in (doc_def.source_file, *(v.source_file for v in doc_def.variants)):
        if source:
            parent = _posix_parent(source)
            if parent:
                dirs.add(parent)
    return dirs


def _common_dir(dirs: set[str]) -> str:
    """Общий родитель набора каталогов по сегментам ('' если общего нет)."""
    seg_lists = [d.split("/") for d in dirs]
    common: list[str] = []
    for seg_group in zip(*seg_lists, strict=False):
        if len(set(seg_group)) == 1:
            common.append(seg_group[0])
        else:
            break
    return "/".join(common)


def def_source_dirs(doc_def: DocumentDefinition) -> set[str]:
    """Каталог(и), которыми ВЛАДЕЕТ определение (для skip-логики).

    Один каталог-владелец = общий родитель всех каталогов определения: для
    обычного дока это его собственный каталог, для презентации (варианты в
    подпапках `presentation/pptx|reveal|beamer`) — родитель `presentation`
    целиком, чтобы служебная `presentation/assets/` не «протекала» в базы,
    где презентации нет (shared в команде).
    """
    raw = def_dirs(doc_def)
    if not raw:
        return set()
    common = _common_dir(raw)
    return {common} if common else raw
