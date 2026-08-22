from __future__ import annotations

import os
from pathlib import Path
from types import ModuleType

import pytest

from trinity_agentic_kit.douyin_adapter import (
    AppDataSessionStore,
    KeyringSessionProtector,
    MemorySessionStore,
    user_app_data_dir,
)


class ReversingProtector:
    def protect(self, session: bytes) -> bytes:
        return session[::-1]

    def unprotect(self, protected_session: bytes) -> bytes:
        return protected_session[::-1]


def configure_app_data(monkeypatch: pytest.MonkeyPatch, root: Path) -> None:
    monkeypatch.setenv("LOCALAPPDATA", str(root))
    monkeypatch.setenv("APPDATA", str(root))
    monkeypatch.setenv("XDG_DATA_HOME", str(root))


def test_app_data_store_is_atomic_protected_and_not_cwd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_data = tmp_path / "app-data"
    configure_app_data(monkeypatch, app_data)
    store = AppDataSessionStore(
        app_name="adapter-tests",
        protector=ReversingProtector(),
    )

    store.save(b"sensitive-state")

    assert store.path.parent == user_app_data_dir("adapter-tests")
    assert store.path.parent != Path.cwd()
    assert store.path.read_bytes() == b"etats-evitisnes"
    assert store.load() == b"sensitive-state"
    assert not list(store.path.parent.glob(f".{store.path.name}.*"))
    if os.name != "nt":
        assert store.path.stat().st_mode & 0o777 == 0o600
    store.clear()
    assert store.load() is None


def test_app_data_store_validates_names_and_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_app_data(monkeypatch, tmp_path)
    with pytest.raises(ValueError, match="app_name"):
        user_app_data_dir("../unsafe")
    with pytest.raises(ValueError, match="filename"):
        AppDataSessionStore(filename="../unsafe")
    with pytest.raises(ValueError, match="empty"):
        AppDataSessionStore(app_name="tests").save(b"")


def test_memory_session_store_copies_and_clears() -> None:
    store = MemorySessionStore()
    assert store.load() is None
    with pytest.raises(ValueError, match="empty"):
        store.save(b"")
    store.save(b"value")
    assert store.load() == b"value"
    store.clear()
    assert store.load() is None


def test_keyring_protector_uses_stable_entry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeKeyringModule(ModuleType):
        def __init__(self) -> None:
            super().__init__("keyring")
            self.values: dict[tuple[str, str], str] = {}

        def set_password(self, service: str, entry: str, value: str) -> None:
            self.values[(service, entry)] = value

        def get_password(self, service: str, entry: str) -> str | None:
            return self.values.get((service, entry))

    backend = FakeKeyringModule()
    monkeypatch.setitem(__import__("sys").modules, "keyring", backend)
    protector = KeyringSessionProtector(
        service_name="test-service",
        entry_name="test-entry",
    )

    handle = protector.protect(b"session")

    assert handle == b"keyring-v1"
    assert protector.unprotect(handle) == b"session"
    with pytest.raises(RuntimeError, match="Unsupported"):
        protector.unprotect(b"unknown")
    backend.values.clear()
    with pytest.raises(RuntimeError, match="unavailable"):
        protector.unprotect(handle)
