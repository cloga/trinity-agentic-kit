from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
INSTALL_COMMAND = "python -m pip install -r requirements-dev.in"
PACKAGE_MODULES = {
    "douyin-publish-adapter": "douyin_adapter",
    "github-resilient-transport": "github_resilience",
    "social-publish-core": "social_publish",
    "value-audit-core": "value_audit",
    "value-audit-tushare": "value_audit_tushare",
    "value-investing-explainer": "value_explainer",
}


def validate_install_input(content: str) -> None:
    configured_packages: list[str] = []
    for line in content.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"-e (packages/[a-z0-9-]+)\[dev\]", line)
        if match is None:
            raise ValueError(f"Expected an editable local package with [dev]: {line}")
        configured_packages.append(match[1])
    if len(configured_packages) != len(set(configured_packages)):
        raise ValueError("Duplicate development package")
    package_projects = {
        path.parent.relative_to(PROJECT_ROOT).as_posix()
        for path in (PROJECT_ROOT / "packages").glob("*/pyproject.toml")
    }
    if set(configured_packages) != package_projects:
        raise ValueError("Development install input must cover every package exactly")


def test_development_install_input_covers_every_package() -> None:
    validate_install_input(
        (PROJECT_ROOT / "requirements-dev.in").read_text(encoding="utf-8")
    )


@pytest.mark.parametrize("mutation", ["missing-dev", "invalid", "duplicate", "missing"])
def test_development_install_input_rejects_drift(mutation: str) -> None:
    content = (PROJECT_ROOT / "requirements-dev.in").read_text(encoding="utf-8")
    lines = content.splitlines()
    if mutation == "missing-dev":
        lines[0] = lines[0].replace("[dev]", "")
    elif mutation == "invalid":
        lines[0] = "-e packages/does-not-exist[dev]"
    elif mutation == "duplicate":
        lines.append(lines[0])
    else:
        lines.pop()
    with pytest.raises(ValueError):
        validate_install_input("\n".join(lines))


@pytest.mark.parametrize(("package", "module"), PACKAGE_MODULES.items())
def test_imports_resolve_to_current_worktree(package: str, module: str) -> None:
    imported = importlib.import_module(f"trinity_agentic_kit.{module}")
    assert imported.__file__ is not None
    expected = (
        PROJECT_ROOT
        / "packages"
        / package
        / "src"
        / "trinity_agentic_kit"
        / module
        / "__init__.py"
    )
    assert Path(imported.__file__).resolve() == expected.resolve()


def test_docs_and_ci_use_the_canonical_development_install_input() -> None:
    for relative_path in (
        "README.md",
        "CONTRIBUTING.md",
        "AGENTS.md",
        ".github/workflows/ci.yml",
    ):
        content = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")
        assert INSTALL_COMMAND in content
