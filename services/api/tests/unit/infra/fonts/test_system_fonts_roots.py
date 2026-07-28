from __future__ import annotations

from pathlib import Path

import pytest
from hse_doc_studio.infra.fonts.system_fonts import OsSystemFontProvider


@pytest.fixture
def host_fonts(tmp_path: Path) -> Path:
    """Каталог шрифтов хоста, смонтированный в контейнер."""
    mounted = tmp_path / "host-fonts"
    mounted.mkdir()
    (mounted / "times.ttf").write_bytes(b"x")
    return mounted


@pytest.mark.unit
async def test__list_fonts__extra_roots_configured__lists_the_mounted_host_fonts(host_fonts: Path) -> None:
    provider = OsSystemFontProvider(extra_roots=[str(host_fonts)])

    assert [f.name for f in await provider.list_fonts()] == ["times.ttf"]


@pytest.mark.unit
async def test__list_fonts__extra_root_missing__is_empty_not_a_crash(tmp_path: Path) -> None:
    # Оверлей не применён / путь опечатан — вкладка честно пуста.
    provider = OsSystemFontProvider(extra_roots=[str(tmp_path / "nope")])

    assert await provider.list_fonts() == []


@pytest.mark.unit
async def test__read_font__inside_a_configured_root__is_allowed(host_fonts: Path) -> None:
    provider = OsSystemFontProvider(extra_roots=[str(host_fonts)])

    assert await provider.read_font(str(host_fonts / "times.ttf")) == b"x"


@pytest.mark.unit
async def test__read_font__outside_every_configured_root__is_refused(host_fonts: Path, tmp_path: Path) -> None:
    # Настроенные корни — ещё и граница чтения: клиент присылает путь строкой.
    outside = tmp_path / "secret.ttf"
    outside.write_bytes(b"x")
    provider = OsSystemFontProvider(extra_roots=[str(host_fonts)])

    with pytest.raises(ValueError, match="not inside"):
        await provider.read_font(str(outside))
