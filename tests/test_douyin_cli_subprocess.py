from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


def subprocess_environment(root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(root)
    environment["APPDATA"] = str(root)
    environment["XDG_DATA_HOME"] = str(root)
    return environment


def test_module_version_subprocess() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "trinity_agentic_kit.douyin_cli",
            "--version",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == "0.1.0"


def test_console_script_version_subprocess() -> None:
    executable = shutil.which("douyin-publish")
    assert executable is not None
    completed = subprocess.run(
        [executable, "--version"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    assert completed.stdout.strip() == "0.1.0"


def test_missing_status_subprocess_is_structured(
    tmp_path: Path,
) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "trinity_agentic_kit.douyin_cli",
            "status",
            "--request-id",
            "missing",
        ],
        check=False,
        capture_output=True,
        text=True,
        env=subprocess_environment(tmp_path),
    )
    assert completed.returncode == 11
    payload = json.loads(completed.stdout)
    assert payload["error"]["code"] == "request_not_found"
    assert not completed.stderr


def test_malformed_config_subprocess_is_structured(
    tmp_path: Path,
) -> None:
    config = tmp_path / "bad.json"
    config.write_text("{", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "trinity_agentic_kit.douyin_cli",
            "login",
            "--config",
            str(config),
        ],
        check=False,
        capture_output=True,
        text=True,
        env=subprocess_environment(tmp_path / "app-data"),
    )
    assert completed.returncode == 10
    payload = json.loads(completed.stdout)
    assert payload["error"]["code"] == "config_invalid"
