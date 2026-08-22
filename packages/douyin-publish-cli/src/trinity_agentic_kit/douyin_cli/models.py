from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DOUYIN_CLI_VERSION = "0.1.0"

EXIT_SUCCESS = 0
EXIT_USAGE = 2
EXIT_CONFIG = 10
EXIT_STATE = 11
EXIT_APPROVAL = 12
EXIT_SESSION = 13
EXIT_TIMEOUT = 14
EXIT_BROWSER = 15
EXIT_CONFIRMATION = 16
EXIT_INTERNAL = 20


@dataclass(frozen=True, slots=True)
class CliPaths:
    data_dir: Path
    state_db: Path
    approval_key: Path
    session_file: Path
    grants_dir: Path
    default_config: Path

    @classmethod
    def from_environment(
        cls,
        *,
        platform_name: str | None = None,
        environment: Mapping[str, str] | None = None,
        home: Path | None = None,
    ) -> CliPaths:
        platform_value = platform_name or sys.platform
        values = environment if environment is not None else os.environ
        home_path = (home or Path.home()).expanduser().resolve()
        if platform_value == "win32":
            root_value = values.get("LOCALAPPDATA") or values.get("APPDATA")
            if not root_value:
                raise ValueError("LOCALAPPDATA or APPDATA is required on Windows")
            root = Path(root_value).expanduser().resolve()
        elif platform_value == "darwin":
            root = home_path / "Library" / "Application Support"
        else:
            xdg_value = values.get("XDG_DATA_HOME")
            root = (
                Path(xdg_value).expanduser().resolve()
                if xdg_value
                else home_path / ".local" / "share"
            )
        data_dir = root / "trinity-agentic-kit" / "douyin-publish-cli"
        return cls(
            data_dir=data_dir,
            state_db=data_dir / "state.db",
            approval_key=data_dir / "approval.key",
            session_file=data_dir / "session.bin",
            grants_dir=data_dir / "grants",
            default_config=data_dir / "config.json",
        )


class CliFailure(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        exit_code: int,
        details: Mapping[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code
        self.details = details
