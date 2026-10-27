from pathlib import Path

from hse_doc_studio.api.config import ServerConfig, Settings


def test__from_settings__default__projects_under_data_dir(tmp_path: Path) -> None:
    cfg = ServerConfig.from_settings(Settings(_env_file=None, data_dir=tmp_path))

    assert cfg.projects_root == tmp_path / "projects"


def test__from_settings__explicit_root__wins(tmp_path: Path) -> None:
    cfg = ServerConfig.from_settings(
        Settings(_env_file=None, data_dir=tmp_path / "d", server={"projects_root": tmp_path / "vol"})
    )

    assert cfg.projects_root == tmp_path / "vol"


def test__caps__server_defaults__no_local_only_features() -> None:
    caps = ServerConfig.from_settings(Settings(_env_file=None)).caps

    assert not caps.fs_browse
    assert not caps.connect_folder
    assert not caps.docker_ui
    assert not caps.self_update
    assert caps.personal_signing_keys
