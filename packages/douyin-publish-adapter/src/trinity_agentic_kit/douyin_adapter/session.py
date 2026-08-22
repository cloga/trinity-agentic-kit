from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Final, Protocol, cast

from .protocols import SessionProtector

_DEFAULT_APP_NAME: Final = "trinity-agentic-kit"


class _KeyringBackend(Protocol):
    def set_password(self, service_name: str, username: str, password: str) -> None: ...

    def get_password(self, service_name: str, username: str) -> str | None: ...


def user_app_data_dir(app_name: str = _DEFAULT_APP_NAME) -> Path:
    normalized = app_name.strip()
    if not normalized or Path(normalized).name != normalized:
        raise ValueError("app_name must be a single non-empty path component")
    if os.name == "nt":
        root = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if root:
            return Path(root).expanduser().resolve() / normalized
    if sys_platform() == "darwin":
        return Path.home().resolve() / "Library" / "Application Support" / normalized
    xdg_root = os.environ.get("XDG_DATA_HOME")
    root_path = (
        Path(xdg_root).expanduser().resolve()
        if xdg_root
        else Path.home().resolve() / ".local" / "share"
    )
    return root_path / normalized


def sys_platform() -> str:
    import sys

    return sys.platform


class AppDataSessionStore:
    """Atomic opaque session storage under the current user's app-data path."""

    def __init__(
        self,
        *,
        app_name: str = _DEFAULT_APP_NAME,
        filename: str = "douyin-session.bin",
        directory: Path | None = None,
        protector: SessionProtector | None = None,
    ) -> None:
        if not filename or Path(filename).name != filename:
            raise ValueError("filename must be a single non-empty path component")
        if directory is not None and not directory.is_absolute():
            raise ValueError("directory must be absolute")
        self._directory = (
            directory.expanduser().resolve()
            if directory is not None
            else user_app_data_dir(app_name)
        )
        self._path = self._directory / filename
        self._protector = protector

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> bytes | None:
        try:
            payload = self._path.read_bytes()
        except FileNotFoundError:
            return None
        if self._protector is not None:
            return self._protector.unprotect(payload)
        return payload

    def save(self, session: bytes) -> None:
        if not session:
            raise ValueError("session cannot be empty")
        payload = (
            self._protector.protect(session)
            if self._protector is not None
            else bytes(session)
        )
        self._directory.mkdir(parents=True, exist_ok=True)
        self._restrict_permissions(self._directory, 0o700)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{self._path.name}.",
            dir=self._directory,
        )
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            self._restrict_permissions(temporary_path, 0o600)
            os.replace(temporary_path, self._path)
            self._restrict_permissions(self._path, 0o600)
        finally:
            temporary_path.unlink(missing_ok=True)

    def clear(self) -> None:
        self._path.unlink(missing_ok=True)

    @staticmethod
    def _restrict_permissions(path: Path, mode: int) -> None:
        try:
            path.chmod(mode)
        except OSError:
            # Some filesystems do not support POSIX-style modes.
            return


class MemorySessionStore:
    """In-memory store for offline tests."""

    def __init__(self, session: bytes | None = None) -> None:
        self._session = bytes(session) if session is not None else None

    def load(self) -> bytes | None:
        return bytes(self._session) if self._session is not None else None

    def save(self, session: bytes) -> None:
        if not session:
            raise ValueError("session cannot be empty")
        self._session = bytes(session)

    def clear(self) -> None:
        self._session = None


class KeyringSessionProtector:
    """Store session bytes in an opt-in keyring backend by random handle."""

    def __init__(
        self,
        *,
        service_name: str = _DEFAULT_APP_NAME,
        entry_name: str = "douyin-session",
    ) -> None:
        self._service_name = service_name
        self._entry_name = entry_name

    def protect(self, session: bytes) -> bytes:
        import base64

        self._keyring().set_password(
            self._service_name,
            self._entry_name,
            base64.b64encode(session).decode("ascii"),
        )
        return b"keyring-v1"

    def unprotect(self, protected_session: bytes) -> bytes:
        import base64

        if protected_session != b"keyring-v1":
            raise RuntimeError("Unsupported protected session handle")
        value = self._keyring().get_password(
            self._service_name,
            self._entry_name,
        )
        if value is None:
            raise RuntimeError("Protected session is unavailable in keyring")
        return base64.b64decode(value, validate=True)

    @staticmethod
    def _keyring() -> _KeyringBackend:
        try:
            import keyring
        except ImportError as exc:
            raise RuntimeError(
                "Install trinity-agentic-kit-douyin-adapter[keyring]"
            ) from exc
        return cast(_KeyringBackend, keyring)
