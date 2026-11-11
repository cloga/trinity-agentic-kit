from __future__ import annotations

import pytest
from components.cross_repo_routing import load_manifest, plan_change


def test_public_contract_change_creates_dependent_private_task() -> None:
    plan = plan_change(
        repository="cloga/trinity-agentic-kit",
        paths=["packages/value-audit-core/src/example.py"],
        manifest=load_manifest(),
    )

    assert [task["repository"] for task in plan["tasks"]] == [
        "cloga/trinity-agentic-kit",
        "cloga/Trinity-Alpha",
    ]
    assert plan["tasks"][1]["depends_on"] == ["public-value-audit"]


def test_private_mirror_change_routes_public_first() -> None:
    plan = plan_change(
        repository="cloga/Trinity-Alpha",
        paths=["src/models/lynch.py"],
        manifest=load_manifest(),
    )

    assert plan["tasks"][0]["kind"] == "canonical-component-change"
    assert plan["tasks"][1]["kind"] == "consumer-update"


def test_private_douyin_adapter_change_stays_private() -> None:
    plan = plan_change(
        repository="cloga/Trinity-Alpha",
        paths=["src/services/douyin_runtime.py"],
        manifest=load_manifest(),
    )

    assert [task["repository"] for task in plan["tasks"]] == ["cloga/Trinity-Alpha"]
    assert plan["tasks"][0]["depends_on"] == []


@pytest.mark.parametrize(
    ("repository", "path"),
    [
        (
            "cloga/trinity-agentic-kit",
            "skills/theme-driven-visual-design/SKILL.md",
        ),
        (
            "cloga/Trinity-Alpha",
            ".agents/skills/theme-driven-visual-design/SKILL.md",
        ),
    ],
)
def test_visual_design_source_and_consumer_route_public_first(
    repository: str, path: str
) -> None:
    plan = plan_change(
        repository=repository,
        paths=[path],
        manifest=load_manifest(),
    )

    assert plan["affected_components"] == [
        {
            "component": "theme-driven-visual-design",
            "paths": [path],
            "policy": "public-first",
        }
    ]
    assert plan["tasks"] == [
        {
            "task_id": "public-theme-driven-visual-design",
            "repository": "cloga/trinity-agentic-kit",
            "kind": "canonical-component-change",
            "component": "theme-driven-visual-design",
            "depends_on": [],
        },
        {
            "task_id": "private-theme-driven-visual-design-consumer",
            "repository": "cloga/Trinity-Alpha",
            "kind": "consumer-update",
            "component": "theme-driven-visual-design",
            "depends_on": ["public-theme-driven-visual-design"],
        },
    ]


@pytest.mark.parametrize(
    ("repository", "path"),
    [
        ("cloga/Trinity-Alpha", "templates/home.html"),
        (
            "cloga/trinity-agentic-kit",
            "skills/theme-driven-visual-design-other/SKILL.md",
        ),
        (
            "cloga/Trinity-Alpha",
            ".agents/skills/theme-driven-visual-design-other/SKILL.md",
        ),
        ("cloga/Trinity-Alpha", ".agents/skills/douyin-generate-video/SKILL.md"),
    ],
)
def test_unowned_path_stays_in_source_repository(repository: str, path: str) -> None:
    plan = plan_change(
        repository=repository,
        paths=[path],
        manifest=load_manifest(),
    )

    assert plan["affected_components"] == []
    assert plan["tasks"] == [
        {
            "task_id": "repository-local-change",
            "repository": repository,
            "kind": "repository-local",
            "component": "",
            "depends_on": [],
        }
    ]
