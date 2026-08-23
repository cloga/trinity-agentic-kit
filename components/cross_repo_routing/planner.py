from __future__ import annotations

import argparse
import fnmatch
import json
from pathlib import Path
from typing import Any, Literal, TypedDict, cast

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = Path(__file__).with_name("ownership.json")


class OwnershipManifestError(RuntimeError):
    """Raised when component ownership cannot be determined safely."""


class ComponentSpec(TypedDict):
    name: str
    public_paths: list[str]
    private_paths: list[str]
    private_change_policy: Literal["public-first", "private-only"]
    requires_private_consumer_update: bool


class OwnershipManifest(TypedDict):
    schema_version: int
    canonical_repository: str
    consumer_repositories: list[str]
    components: list[ComponentSpec]


def load_manifest(path: Path = DEFAULT_MANIFEST) -> OwnershipManifest:
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise OwnershipManifestError("ownership manifest must be an object")
    payload = cast(dict[str, object], raw)
    if payload.get("schema_version") != 1:
        raise OwnershipManifestError("ownership schema_version must be 1")
    if not str(payload.get("canonical_repository") or "").strip():
        raise OwnershipManifestError("canonical_repository is required")
    consumers = payload.get("consumer_repositories")
    components = payload.get("components")
    consumer_items = (
        cast(list[object], consumers) if isinstance(consumers, list) else []
    )
    if not consumer_items or not all(
        isinstance(item, str) and item for item in consumer_items
    ):
        raise OwnershipManifestError("consumer_repositories must be non-empty")
    if not isinstance(components, list) or not components:
        raise OwnershipManifestError("components must be non-empty")
    component_items = cast(list[object], components)
    names: set[str] = set()
    normalized_components: list[ComponentSpec] = []
    for raw_component in component_items:
        if not isinstance(raw_component, dict):
            raise OwnershipManifestError("component entries must be objects")
        component = cast(dict[str, object], raw_component)
        name = str(component.get("name") or "").strip()
        if not name or name in names:
            raise OwnershipManifestError(f"invalid or duplicate component name: {name}")
        names.add(name)
        if component.get("private_change_policy") not in {
            "public-first",
            "private-only",
        }:
            raise OwnershipManifestError(
                f"{name} private_change_policy must be public-first or private-only"
            )
        for field in ("public_paths", "private_paths"):
            patterns = component.get(field)
            pattern_items = (
                cast(list[object], patterns) if isinstance(patterns, list) else []
            )
            if not pattern_items or not all(
                isinstance(item, str) and item for item in pattern_items
            ):
                raise OwnershipManifestError(f"{name}.{field} must be non-empty")
        normalized_components.append(
            {
                "name": name,
                "public_paths": cast(list[str], component["public_paths"]),
                "private_paths": cast(list[str], component["private_paths"]),
                "private_change_policy": cast(
                    Literal["public-first", "private-only"],
                    component["private_change_policy"],
                ),
                "requires_private_consumer_update": bool(
                    component.get("requires_private_consumer_update")
                ),
            }
        )
    return {
        "schema_version": 1,
        "canonical_repository": str(payload["canonical_repository"]),
        "consumer_repositories": cast(list[str], consumer_items),
        "components": normalized_components,
    }


def _matches(path: str, patterns: list[str]) -> bool:
    normalized = str(path).replace("\\", "/").lstrip("/")
    return any(fnmatch.fnmatchcase(normalized, pattern) for pattern in patterns)


def plan_change(
    *,
    repository: str,
    paths: list[str],
    manifest: OwnershipManifest,
) -> dict[str, Any]:
    canonical = str(manifest["canonical_repository"])
    consumers = [str(item) for item in manifest["consumer_repositories"]]
    if repository not in {canonical, *consumers}:
        raise OwnershipManifestError(f"repository is not declared: {repository}")
    affected: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    seen_tasks: set[str] = set()

    def add_task(task: dict[str, Any]) -> None:
        task_id = str(task["task_id"])
        if task_id not in seen_tasks:
            tasks.append(task)
            seen_tasks.add(task_id)

    for component in manifest["components"]:
        public_matches = [
            path
            for path in paths
            if _matches(path, [str(item) for item in component["public_paths"]])
        ]
        private_matches = [
            path
            for path in paths
            if _matches(path, [str(item) for item in component["private_paths"]])
        ]
        matches = public_matches if repository == canonical else private_matches
        if not matches:
            continue
        name = str(component["name"])
        policy = str(component["private_change_policy"])
        affected.append(
            {
                "component": name,
                "paths": sorted(matches),
                "policy": policy,
            }
        )
        public_task_id = f"public-{name}"
        private_task_id = f"private-{name}-consumer"
        if repository == canonical or policy == "public-first":
            add_task(
                {
                    "task_id": public_task_id,
                    "repository": canonical,
                    "kind": "canonical-component-change",
                    "component": name,
                    "depends_on": [],
                }
            )
        if bool(component.get("requires_private_consumer_update")):
            dependency = (
                [public_task_id]
                if repository == canonical or policy == "public-first"
                else []
            )
            add_task(
                {
                    "task_id": private_task_id,
                    "repository": consumers[0],
                    "kind": "consumer-update",
                    "component": name,
                    "depends_on": dependency,
                }
            )
        elif repository != canonical:
            add_task(
                {
                    "task_id": f"private-{name}",
                    "repository": consumers[0],
                    "kind": "private-adapter-change",
                    "component": name,
                    "depends_on": [],
                }
            )
    if not affected:
        add_task(
            {
                "task_id": "repository-local-change",
                "repository": repository,
                "kind": "repository-local",
                "component": "",
                "depends_on": [],
            }
        )
    return {
        "schema_version": 1,
        "source_repository": repository,
        "affected_components": affected,
        "tasks": tasks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan public/private repository work")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--path", action="append", dest="paths", required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    args = parser.parse_args()
    plan = plan_change(
        repository=args.repository,
        paths=args.paths,
        manifest=load_manifest(args.manifest.resolve()),
    )
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    return 0
