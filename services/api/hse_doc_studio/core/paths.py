"""Соответствие путей контейнера путям на машине пользователя.

Продукт поставляется контейнером, но работает с ФАЙЛАМИ ПОЛЬЗОВАТЕЛЯ: его папки
приезжают внутрь бинд-маунтами. Из-за этого один и тот же каталог называется
по-разному:

* `/projects/vkr-ru` — как его видит процесс внутри контейнера;
* `D:/study/hse/vkr-ru` — как его знает пользователь и как его понимает
  docker-демон, когда мы просим смонтировать каталог в TeX-контейнер.

Внутри системы (project.json, реестр, сборка) живёт КОНТЕЙНЕРНЫЙ путь — он
стабилен и не зависит от того, где пользователь держит папку. Наружу — в файловый
браузер, карточку проекта, мастер создания — отдаётся ХОСТОВЫЙ: пользователю
нечего делать с `/projects`, он не найдёт такой папки у себя.

Класс — чистый домен: список пар «корень в контейнере → корень на хосте» и
перевод в обе стороны. Пустой список означает нативный запуск, где переводить
нечего и оба пути совпадают.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Mount:
    """Один бинд-маунт: как каталог зовётся внутри и снаружи."""

    container: str
    host: str


_DRIVE_ROOT_RE = re.compile(r"^[A-Za-z]:$")


def _normalise(value: str) -> str:
    """Единый вид пути: прямые слэши, без хвостового разделителя.

    Прямые слэши — единственное, что одинаково понимают и POSIX внутри
    контейнера, и docker на Windows.

    Исключение — КОРНИ. У `/` и `C:/` хвостовой слэш не украшение, а часть
    имени: срезав его у `C:\\`, получаем `C:`, а это в Windows не корень диска,
    а «текущий каталог диска C». В `docker run -v C::/work` демон видит пустой
    источник и монтирует не то, что просили.
    """
    normalised = value.replace("\\", "/").rstrip("/")
    if not normalised:
        return "/"
    if _DRIVE_ROOT_RE.match(normalised):
        return f"{normalised}/"
    return normalised


def _join(root: str, rest: str) -> str:
    """Приклеить остаток пути к корню, не удвоив разделитель у `/` и `C:/`."""
    return f"{root}{rest}" if root.endswith("/") else f"{root}/{rest}"


def looks_absolute(host_path: str) -> bool:
    """Пригоден ли путь как источник бинд-маунта на хосте.

    Проверяем сами, а не через `Path.is_absolute()`: бэкенд живёт в
    Linux-контейнере, и хостовый `C:/Users/...` тамошний PurePosixPath
    абсолютным не считает. А относительный путь докер примет за ИМЯ ТОМА и
    молча смонтирует пустоту вместо папки пользователя.
    """
    normalised = host_path.replace("\\", "/")
    return normalised.startswith("/") or (len(normalised) > 2 and normalised[1:3] == ":/")  # noqa: PLR2004


class PathMapping:
    """Перевод путей между контейнером и хостом по списку маунтов.

    Порядок маунтов значим: подходит первый, чей корень накрывает путь. Более
    специфичный маунт (`/projects`) обязан идти раньше общего (`/data`).
    """

    def __init__(self, mounts: Sequence[Mount] = ()) -> None:
        self._mounts = tuple(Mount(_normalise(m.container), _normalise(m.host)) for m in mounts)

    @property
    def mounts(self) -> tuple[Mount, ...]:
        return self._mounts

    def __bool__(self) -> bool:
        return bool(self._mounts)

    @staticmethod
    def _swap(path: str, from_root: str, to_root: str) -> str | None:
        normalised = _normalise(path)
        if normalised == from_root:
            return to_root
        prefix = from_root if from_root.endswith("/") else f"{from_root}/"
        if normalised.startswith(prefix):
            return _join(to_root, normalised[len(prefix) :])
        return None

    def to_host(self, path: str) -> str | None:
        """Контейнерный путь → путь на машине пользователя. None — вне маунтов."""
        if not self._mounts:
            return _normalise(path)
        for mount in self._mounts:
            swapped = self._swap(path, mount.container, mount.host)
            if swapped is not None:
                return swapped
        return None

    def to_container(self, path: str) -> str | None:
        """Путь на машине пользователя → контейнерный. None — вне маунтов."""
        if not self._mounts:
            return _normalise(path)
        for mount in self._mounts:
            swapped = self._swap(path, mount.host, mount.container)
            if swapped is not None:
                return swapped
        return None

    def is_root(self, path: str) -> bool:
        """Является ли путь корнем смонтированного каталога.

        Выше такого корня файловому браузеру подниматься нечего: там начинается
        файловая система ОБРАЗА, где создавать проект бессмысленно — он исчезнет
        при первом же обновлении версии.
        """
        normalised = _normalise(path)
        return any(normalised == m.container for m in self._mounts)

    def display(self, path: str) -> str:
        """Как показать путь пользователю; непереводимый отдаём как есть.

        Осознанно не бросаем: путь может прийти из проекта, подключённого до
        появления маунта, и подписать его контейнерным именем лучше, чем упасть.
        Без маунтов (нативный запуск) путь возвращается ДОСЛОВНО — там он уже
        пользовательский, и подменять `C:\\Users` на `C:/Users` незачем.
        """
        if not self._mounts:
            return path
        return self.to_host(path) or path

    def accept(self, path: str) -> str:
        """Как понять путь, пришедший от клиента (хостовый ИЛИ уже контейнерный).

        Клиент оперирует хостовыми путями, но URL можно вставить руками, а
        интеграции (агент, восстановление сессии) хранят контейнерные — принимаем
        оба, чтобы одинаковая по смыслу строка не зависела от происхождения.
        """
        if not self._mounts:
            return path
        normalised = _normalise(path)
        for mount in self._mounts:
            if normalised == mount.container or normalised.startswith(f"{mount.container}/"):
                return normalised
        return self.to_container(path) or path
