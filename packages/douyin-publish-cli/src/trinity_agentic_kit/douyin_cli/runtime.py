from __future__ import annotations

import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from trinity_agentic_kit.douyin_adapter import (
    AppDataSessionStore,
    BrowserDriver,
    DouyinPublisherAdapter,
    KeyringSessionProtector,
    SessionProtector,
)
from trinity_agentic_kit.social_publish import (
    HmacApprovalAuthority,
    InMemoryAuditSink,
    SocialPublishCoordinator,
    SQLitePublishStateStore,
)

from .config import CliConfig
from .models import EXIT_CONFIG, CliFailure, CliPaths

DriverFactory = Callable[[CliConfig], BrowserDriver]


@dataclass(slots=True)
class CliRuntime:
    driver: BrowserDriver
    adapter: DouyinPublisherAdapter
    store: SQLitePublishStateStore
    authority: HmacApprovalAuthority
    coordinator: SocialPublishCoordinator

    async def close(self) -> None:
        await self.driver.close()


def default_driver_factory(config: CliConfig) -> BrowserDriver:
    try:
        from trinity_agentic_kit.douyin_adapter import (
            PlaywrightBrowserDriver,
        )
    except RuntimeError as exc:
        raise CliFailure(
            "playwright_unavailable",
            "Install trinity-agentic-kit-douyin[playwright]",
            EXIT_CONFIG,
        ) from exc
    return PlaywrightBrowserDriver(browser_name=config.browser_name)


def build_runtime(
    config: CliConfig,
    paths: CliPaths,
    *,
    driver_factory: DriverFactory = default_driver_factory,
) -> CliRuntime:
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    _restrict_permissions(paths.data_dir, 0o700)
    authority = load_authority(paths, use_keyring=config.use_keyring)
    protector: SessionProtector | None = None
    if config.use_keyring:
        protector = KeyringSessionProtector(
            service_name="trinity-agentic-kit-douyin",
            entry_name="browser-session",
        )
    session_store = AppDataSessionStore(
        app_name="trinity-agentic-kit",
        filename=paths.session_file.name,
        directory=paths.data_dir,
        protector=protector,
    )
    store = open_store(paths)
    driver = driver_factory(config)
    adapter = DouyinPublisherAdapter(
        driver=driver,
        session_store=session_store,
        selector_profile=config.selector_profile,
    )
    coordinator = SocialPublishCoordinator(
        adapters={adapter.platform: adapter},
        store=store,
        approval_authority=authority,
        audit_sink=InMemoryAuditSink(),
    )
    return CliRuntime(
        driver=driver,
        adapter=adapter,
        store=store,
        authority=authority,
        coordinator=coordinator,
    )


def open_store(paths: CliPaths) -> SQLitePublishStateStore:
    paths.data_dir.mkdir(parents=True, exist_ok=True)
    _restrict_permissions(paths.data_dir, 0o700)
    store = SQLitePublishStateStore(paths.state_db)
    store.init_schema()
    _restrict_permissions(paths.state_db, 0o600)
    return store


def load_authority(
    paths: CliPaths,
    *,
    use_keyring: bool,
) -> HmacApprovalAuthority:
    key_store = AppDataSessionStore(
        app_name="trinity-agentic-kit",
        filename=paths.approval_key.name,
        directory=paths.data_dir,
        protector=(
            KeyringSessionProtector(
                service_name="trinity-agentic-kit-douyin",
                entry_name="approval-key",
            )
            if use_keyring
            else None
        ),
    )
    try:
        key = key_store.load()
        if key is None:
            key_store.save(secrets.token_bytes(32))
            key = key_store.load()
    except (OSError, RuntimeError, ValueError) as exc:
        raise CliFailure(
            "approval_key_unavailable",
            f"Cannot access approval key storage: {exc}",
            EXIT_CONFIG,
        ) from exc
    if key is None or len(key) < 32:
        raise CliFailure(
            "approval_key_invalid",
            "Approval key storage did not return a valid key",
            EXIT_CONFIG,
        )
    return HmacApprovalAuthority(
        key,
        issuer="douyin-publish-cli",
    )


def write_secret_file(path: Path, payload: str) -> None:
    if not path.is_absolute():
        raise CliFailure(
            "grant_path_invalid",
            "Grant file path must be absolute",
            EXIT_CONFIG,
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    _restrict_permissions(path.parent, 0o700)
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}")
    try:
        descriptor = os.open(
            temporary,
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o600,
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _restrict_permissions(path, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def read_secret_file(path: Path) -> str:
    try:
        token = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError) as exc:
        raise CliFailure(
            "grant_file_invalid",
            f"Cannot read grant file: {exc}",
            EXIT_CONFIG,
        ) from exc
    if not token:
        raise CliFailure(
            "grant_file_invalid",
            "Grant file is empty",
            EXIT_CONFIG,
        )
    return token


def _restrict_permissions(path: Path, mode: int) -> None:
    try:
        path.chmod(mode)
    except OSError:
        return
