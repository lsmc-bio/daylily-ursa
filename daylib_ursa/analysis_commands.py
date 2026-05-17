from __future__ import annotations

import shlex
from importlib import import_module
from typing import Any

from daylib_ursa.ephemeral_cluster.runner import require_daylily_ec_version


def load_dayec_command_catalog() -> Any:
    """Load the day-ec repository command catalog through the 3.0.0 library surface."""

    require_daylily_ec_version()
    module = import_module("daylily_ec.repositories")
    loader = getattr(module, "load_repository_catalog", None)
    if not callable(loader):
        raise RuntimeError("daylily_ec.repositories.load_repository_catalog is not available")
    return loader()


def _filter_catalog_payload(payload: dict[str, Any], *, command_class: str) -> dict[str, Any]:
    commands = [
        dict(item)
        for item in list(payload.get("commands") or [])
        if isinstance(item, dict) and item.get("command_class") == command_class
    ]
    repositories = {}
    for repo_key, repo_payload in dict(payload.get("repositories") or {}).items():
        if not isinstance(repo_payload, dict):
            continue
        repo_commands = [
            dict(item)
            for item in list(repo_payload.get("analysis_commands") or [])
            if isinstance(item, dict) and item.get("command_class") == command_class
        ]
        if repo_commands:
            repo_copy = dict(repo_payload)
            repo_copy["analysis_commands"] = repo_commands
            repositories[repo_key] = repo_copy
    return {**payload, "repositories": repositories, "commands": commands}


def command_catalog_payload(*, command_class: str | None = None) -> dict[str, Any]:
    catalog = load_dayec_command_catalog()
    payload = catalog.to_public_payload()
    if not isinstance(payload, dict):
        raise RuntimeError("day-ec command catalog returned a non-object payload")
    if command_class is None:
        return payload
    return _filter_catalog_payload(payload, command_class=command_class)


def sample_analysis_command_catalog_payload() -> dict[str, Any]:
    return command_catalog_payload(command_class="sample_analysis")


def run_analysis_command_catalog_payload() -> dict[str, Any]:
    return command_catalog_payload(command_class="run_analysis")


def get_analysis_command(command_id: str, *, optional_features: list[str] | None = None) -> Any:
    normalized = str(command_id or "").strip()
    if not normalized:
        raise ValueError("command_id is required")
    catalog = load_dayec_command_catalog()
    try:
        command = catalog.get_command(normalized)
    except KeyError as exc:
        raise ValueError(f"Unknown analysis command: {normalized}") from exc
    features = [
        str(item or "").strip() for item in list(optional_features or []) if str(item or "").strip()
    ]
    if features:
        command = command.with_features(features)
    return command


def analysis_command_payload(
    command_id: str,
    *,
    optional_features: list[str] | None = None,
    command_class: str | None = None,
) -> dict[str, Any]:
    command = get_analysis_command(command_id, optional_features=optional_features)
    if command_class is not None and command.command_class != command_class:
        raise ValueError(f"{command_id} is not a {command_class} command")
    return dict(command.model_dump(mode="json"))


def preview_analysis_command(
    command_id: str,
    *,
    optional_features: list[str] | None = None,
    profile: str | None = None,
    region: str | None = None,
    cluster_name: str | None = None,
    stage_dir: str | None = None,
    session_name: str | None = None,
    destination: str | None = None,
    project: str | None = None,
    run_context_file: str | None = None,
    command_class: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    command = get_analysis_command(command_id, optional_features=optional_features)
    if command_class is not None and command.command_class != command_class:
        raise ValueError(f"{command_id} is not a {command_class} command")
    argv = command.launch_argv(
        profile=profile,
        region=region,
        cluster=cluster_name,
        stage_dir=stage_dir,
        session_name=session_name,
        destination=destination,
        project=project,
        run_context_file=run_context_file,
        dry_run=dry_run,
    )
    return {
        "valid": True,
        "command": command.model_dump(mode="json"),
        "argv": list(argv),
        "shell_preview": shlex.join(["daylily-ec", *argv]),
    }


def run_analysis_command_payload(
    command_id: str,
    *,
    optional_features: list[str] | None = None,
) -> dict[str, Any]:
    return analysis_command_payload(
        command_id,
        optional_features=optional_features,
        command_class="run_analysis",
    )


def preview_run_analysis_command(
    command_id: str,
    *,
    optional_features: list[str] | None = None,
    profile: str | None = None,
    region: str | None = None,
    cluster_name: str | None = None,
    run_context_file: str | None = None,
    session_name: str | None = None,
    destination: str | None = None,
    project: str | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    resolved_run_context = str(run_context_file or "").strip()
    if not resolved_run_context:
        raise ValueError("run_context_file is required")
    return preview_analysis_command(
        command_id,
        optional_features=optional_features,
        profile=profile,
        region=region,
        cluster_name=cluster_name,
        run_context_file=resolved_run_context,
        session_name=session_name,
        destination=destination,
        project=project,
        command_class="run_analysis",
        dry_run=dry_run,
    )
