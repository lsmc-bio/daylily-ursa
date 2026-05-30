from __future__ import annotations

import shlex
from importlib import import_module
from typing import Any

from daylib_ursa.ephemeral_cluster.runner import require_daylily_ec_version


def load_dayec_command_catalog() -> Any:
    """Load the day-ec repository command catalog through the ==5.1.2 surface."""

    require_daylily_ec_version()
    module = import_module("daylily_ec.repositories")
    loader = getattr(module, "load_repository_catalog", None)
    if not callable(loader):
        raise RuntimeError("daylily_ec.repositories.load_repository_catalog is not available")
    return loader()


def command_catalog_payload() -> dict[str, Any]:
    catalog = load_dayec_command_catalog()
    payload = catalog.to_public_payload()
    if not isinstance(payload, dict):
        raise RuntimeError("day-ec command catalog returned a non-object payload")
    return payload


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
) -> dict[str, Any]:
    command = get_analysis_command(command_id, optional_features=optional_features)
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
    analysis_id: str | None = None,
    executing_entity: str | None = None,
    run_context_file: str | None = None,
    export_trigger: str = "none",
    dry_run: bool = False,
) -> dict[str, Any]:
    command = get_analysis_command(command_id, optional_features=optional_features)
    resolved_analysis_id = analysis_id or f"preview-{command_id}"
    resolved_executing_entity = executing_entity or "ursa"
    argv = command.launch_argv(
        analysis_id=resolved_analysis_id,
        executing_entity=resolved_executing_entity,
        profile=profile,
        region=region,
        cluster=cluster_name,
        stage_dir=stage_dir,
        session_name=session_name,
        export_destination_s3_uri=destination,
        project=project,
        run_context_file=run_context_file,
        export_trigger=export_trigger,
        dry_run=dry_run,
    )
    return {
        "valid": True,
        "command": command.model_dump(mode="json"),
        "argv": list(argv),
        "shell_preview": shlex.join(["daylily-ec", *argv]),
    }
