"""Шрифты хоста, увиденные через docker-сокет.

Раньше вкладка «Системные» в контейнере была пуста всегда: каталоги ОС там
принадлежат образу, а не пользователю. Вместо шрифтов человеку показывали
команду монтирования — ручную работу, ради устранения которой продукт и
существует.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
from hse_doc_studio.infra.fonts.host_font_provider import DockerHostFontProvider
from hse_doc_studio.infra.fonts.host_scan import read, scan


@pytest.fixture
def host_fonts(tmp_path: Path) -> Path:
    root = tmp_path / "Fonts"
    (root / "sub").mkdir(parents=True)
    (root / "times.ttf").write_bytes(b"TIMES")
    (root / "sub" / "Arial Bold.otf").write_bytes(b"ARIAL")
    (root / "readme.txt").write_text("not a font", encoding="utf-8")
    return root


@pytest.mark.unit
def test__scan__mounted_directory__lists_only_font_files(host_fonts: Path) -> None:
    names = {item["name"] for item in scan(host_fonts)}

    assert names == {"times.ttf", "Arial Bold.otf"}


@pytest.mark.unit
def test__scan__nested_font__path_is_relative_to_the_mount(host_fonts: Path) -> None:
    # Наружу отдаются ОТНОСИТЕЛЬНЫЕ пути: внутри контейнера каталог называется
    # иначе, чем на хосте, и склеить хостовое имя может только вызывающий.
    entry = next(item for item in scan(host_fonts) if item["name"] == "Arial Bold.otf")

    assert entry["rel"] == "sub/Arial Bold.otf"


@pytest.mark.unit
def test__read__font_inside_the_mount__returns_its_bytes(host_fonts: Path) -> None:
    assert read(host_fonts, "times.ttf") == b"TIMES"


@pytest.mark.unit
@pytest.mark.parametrize(
    "relative",
    [
        pytest.param("../outside.ttf", id="parent_traversal"),
        pytest.param("readme.txt", id="not_a_font"),
    ],
)
def test__read__path_outside_the_mount_or_not_a_font__refuses(host_fonts: Path, relative: str) -> None:
    with pytest.raises(ValueError):  # noqa: PT011 — важен сам отказ, не текст
        read(host_fonts, relative)


# ── Провайдер: сборка хостовых путей и защита ручки импорта ─────────────────


@pytest.mark.unit
def test__relative_to_root__path_inside__is_reduced_to_the_relative_part() -> None:
    result = DockerHostFontProvider._relative_to_root("C:/Windows/Fonts/sub/times.ttf", "C:/Windows/Fonts")

    assert result == "sub/times.ttf"


@pytest.mark.unit
def test__relative_to_root__backslashes__are_accepted() -> None:
    # Путь приезжает от клиента, а тот берёт его из нашего же списка — но на
    # Windows человек вполне может подставить его руками с обратными слэшами.
    result = DockerHostFontProvider._relative_to_root("C:\\Windows\\Fonts\\times.ttf", "C:/Windows/Fonts")

    assert result == "times.ttf"


@pytest.mark.unit
def test__relative_to_root__path_outside__refuses() -> None:
    # Без этой проверки ручку импорта можно было бы попросить прочитать любой
    # файл хоста: путь она принимает от клиента.
    with pytest.raises(ValueError, match="not inside"):
        DockerHostFontProvider._relative_to_root("C:/Windows/System32/config/SAM", "C:/Windows/Fonts")


@pytest.mark.unit
async def test__list_fonts__scan_output__becomes_host_paths(monkeypatch) -> None:
    provider = DockerHostFontProvider(root_override="C:/Windows/Fonts")
    payload = '[{"name": "times.ttf", "rel": "times.ttf", "family": "Times New Roman"}]'

    async def fake_run(root: str, args: list[str], timeout: float) -> tuple[int, str, str]:
        return 0, payload, ""

    monkeypatch.setattr(provider, "_run", fake_run)

    fonts = await provider.list_fonts()

    assert [(f.name, f.path, f.family) for f in fonts] == [
        ("times.ttf", "C:/Windows/Fonts/times.ttf", "Times New Roman")
    ]


@pytest.mark.unit
async def test__host_font_dir__override_given__does_not_probe_the_standard_places(monkeypatch) -> None:
    # Явно заданный каталог перебивает перебор: шрифты можно держать где угодно,
    # а автоопределение знает только стандартные места.
    provider = DockerHostFontProvider(root_override="D:/MyFonts")
    probed: list[str] = []

    async def fake_run(root: str, args: list[str], timeout: float) -> tuple[int, str, str]:
        probed.append(root)
        return 0, '[{"name": "a.ttf", "rel": "a.ttf", "family": "A"}]', ""

    monkeypatch.setattr(provider, "_run", fake_run)

    assert await provider.host_font_dir() == "D:/MyFonts"
    assert probed == ["D:/MyFonts"]


@pytest.mark.unit
async def test__read_font__sidecar_output__is_decoded_from_base64(monkeypatch) -> None:
    provider = DockerHostFontProvider(root_override="C:/Windows/Fonts")

    async def fake_run(root: str, args: list[str], timeout: float) -> tuple[int, str, str]:
        if args[0] == "scan":
            return 0, '[{"name": "times.ttf", "rel": "times.ttf", "family": "Times"}]', ""
        return 0, base64.b64encode(b"TIMES").decode("ascii") + "\n", ""

    monkeypatch.setattr(provider, "_run", fake_run)

    assert await provider.read_font("C:/Windows/Fonts/times.ttf") == b"TIMES"
