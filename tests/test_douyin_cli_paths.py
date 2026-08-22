from __future__ import annotations

from pathlib import Path

import pytest

from trinity_agentic_kit.douyin_cli import CliPaths


def test_windows_paths_use_local_app_data(tmp_path: Path) -> None:
    paths = CliPaths.from_environment(
        platform_name="win32",
        environment={"LOCALAPPDATA": str(tmp_path)},
        home=tmp_path / "home",
    )
    assert paths.data_dir == (
        tmp_path.resolve() / "trinity-agentic-kit" / "douyin-publish-cli"
    )
    assert paths.state_db.parent == paths.data_dir
    assert paths.data_dir != Path.cwd()


def test_linux_paths_use_xdg_or_home(tmp_path: Path) -> None:
    xdg = tmp_path / "xdg"
    configured = CliPaths.from_environment(
        platform_name="linux",
        environment={"XDG_DATA_HOME": str(xdg)},
        home=tmp_path / "home",
    )
    assert configured.data_dir.parent.parent == xdg.resolve()

    fallback = CliPaths.from_environment(
        platform_name="linux",
        environment={},
        home=tmp_path / "home",
    )
    assert fallback.data_dir.parent.parent == (tmp_path / "home" / ".local" / "share")


def test_windows_requires_app_data(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="LOCALAPPDATA"):
        CliPaths.from_environment(
            platform_name="win32",
            environment={},
            home=tmp_path,
        )
