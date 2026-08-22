from __future__ import annotations

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


def test_unowned_path_stays_in_source_repository() -> None:
    plan = plan_change(
        repository="cloga/Trinity-Alpha",
        paths=["templates/home.html"],
        manifest=load_manifest(),
    )

    assert plan["tasks"] == [
        {
            "task_id": "repository-local-change",
            "repository": "cloga/Trinity-Alpha",
            "kind": "repository-local",
            "component": "",
            "depends_on": [],
        }
    ]
