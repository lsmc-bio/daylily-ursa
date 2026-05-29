"""Explicit Ursa API command wrappers."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Literal

import httpx
import typer
from cli_core_yo import output as cli_output

from daylib_ursa.cli._registry_v2 import (
    REQUIRED_JSON,
    REQUIRED_MUTATING_JSON,
    register_group_commands,
)

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec


AuthMode = Literal["bearer", "api-key"]


def _parse_json_object(raw: str, *, option_name: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise typer.BadParameter(f"Invalid JSON for {option_name}: {exc}") from exc
    if not isinstance(payload, dict):
        raise typer.BadParameter(f"{option_name} must decode to a JSON object")
    return payload


def _headers(*, token: str, auth_mode: AuthMode) -> dict[str, str]:
    clean_token = str(token or "").strip()
    if not clean_token:
        raise typer.BadParameter("--token is required")
    if auth_mode == "api-key":
        return {"X-API-Key": clean_token}
    return {"Authorization": f"Bearer {clean_token}"}


def _request(
    *,
    api_base_url: str,
    token: str,
    method: str,
    path: str,
    auth_mode: AuthMode = "bearer",
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = str(api_base_url or "").strip().rstrip("/")
    clean_path = str(path or "").strip()
    if not base:
        raise typer.BadParameter("--api-base-url is required")
    if not clean_path.startswith("/"):
        raise typer.BadParameter("--path must start with '/'")
    http_method = str(method or "").strip().upper()
    if http_method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise typer.BadParameter("--method must be one of GET, POST, PUT, PATCH, DELETE")
    url = f"{base}{clean_path}"
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.request(
                http_method,
                url,
                headers={**_headers(token=token, auth_mode=auth_mode), "Accept": "application/json"},
                json=body if body is not None else None,
            )
    except httpx.HTTPError as exc:
        cli_output.print_rich(f"[red]✗[/red] Ursa API request failed: {exc}")
        raise typer.Exit(1) from exc
    try:
        payload = response.json()
    except ValueError:
        payload = {"text": response.text}
    if response.status_code >= 400:
        cli_output.print_rich(
            f"[red]✗[/red] Ursa API returned HTTP {response.status_code}: {payload}"
        )
        raise typer.Exit(1)
    if isinstance(payload, dict):
        return payload
    return {"items": payload}


def request(
    api_base_url: str = typer.Option(..., "--api-base-url", help="Ursa API base URL"),
    token: str = typer.Option(..., "--token", help="Bearer token or X-API-Key value"),
    method: str = typer.Option("GET", "--method", help="HTTP method"),
    path: str = typer.Option(..., "--path", help="Ursa API path starting with /"),
    auth_mode: AuthMode = typer.Option("bearer", "--auth-mode", help="bearer or api-key"),
    body_json: str = typer.Option("{}", "--body-json", help="JSON object body"),
) -> None:
    """Call an Ursa API endpoint with explicit URL and credentials."""

    payload = _request(
        api_base_url=api_base_url,
        token=token,
        method=method,
        path=path,
        auth_mode=auth_mode,
        body=_parse_json_object(body_json, option_name="--body-json")
        if method.upper() != "GET"
        else None,
    )
    cli_output.emit_json(payload)


def list_compute_clusters(
    api_base_url: str = typer.Option(..., "--api-base-url", help="Ursa API base URL"),
    token: str = typer.Option(..., "--token", help="Bearer token"),
) -> None:
    """List Ursa compute-cluster objects."""

    cli_output.emit_json(
        _request(
            api_base_url=api_base_url,
            token=token,
            method="GET",
            path="/api/v1/compute-clusters",
        )
    )


def create_compute_cluster(
    api_base_url: str = typer.Option(..., "--api-base-url", help="Ursa API base URL"),
    token: str = typer.Option(..., "--token", help="Bearer token"),
    cluster_name: str = typer.Option(..., "--cluster-name", help="Cluster name"),
    cluster_type: str = typer.Option(
        ..., "--cluster-type", help="generic, vanilla_slurm, or aws_parallelcluster_slurm"
    ),
    region: str = typer.Option(..., "--region", help="Cluster region"),
    display_name: str = typer.Option("", "--display-name", help="Optional display name"),
    metadata_json: str = typer.Option("{}", "--metadata-json", help="Metadata JSON object"),
) -> None:
    """Create a durable Ursa compute-cluster object."""

    body = {
        "cluster_name": cluster_name,
        "cluster_type": cluster_type,
        "region": region,
        "metadata": _parse_json_object(metadata_json, option_name="--metadata-json"),
    }
    if str(display_name or "").strip():
        body["display_name"] = display_name
    cli_output.emit_json(
        _request(
            api_base_url=api_base_url,
            token=token,
            method="POST",
            path="/api/v1/compute-clusters",
            body=body,
        )
    )


def get_compute_cluster(
    cluster_euid: str = typer.Argument(..., help="Compute cluster EUID"),
    api_base_url: str = typer.Option(..., "--api-base-url", help="Ursa API base URL"),
    token: str = typer.Option(..., "--token", help="Bearer token"),
) -> None:
    """Fetch one Ursa compute-cluster object."""

    cli_output.emit_json(
        _request(
            api_base_url=api_base_url,
            token=token,
            method="GET",
            path=f"/api/v1/compute-clusters/{cluster_euid}",
        )
    )


def list_cluster_jobs(
    api_base_url: str = typer.Option(..., "--api-base-url", help="Ursa API base URL"),
    token: str = typer.Option(..., "--token", help="Bearer token"),
) -> None:
    """List Ursa cluster-job objects."""

    cli_output.emit_json(
        _request(
            api_base_url=api_base_url,
            token=token,
            method="GET",
            path="/api/v1/cluster-jobs",
        )
    )


def create_cluster_job(
    api_base_url: str = typer.Option(..., "--api-base-url", help="Ursa API base URL"),
    token: str = typer.Option(..., "--token", help="Bearer token"),
    cluster_euid: str = typer.Option(..., "--cluster-euid", help="Compute cluster EUID"),
    job_type: str = typer.Option("generic", "--job-type", help="generic or slurm"),
    job_name: str = typer.Option("", "--job-name", help="Optional job name"),
    analysis_job_euid: str = typer.Option("", "--analysis-job-euid", help="Optional analysis job"),
    scheduler_job_id: str = typer.Option("", "--scheduler-job-id", help="Optional Slurm job ID"),
    request_json: str = typer.Option("{}", "--request-json", help="Job request JSON object"),
    start: bool = typer.Option(False, "--start", help="Start the cluster job after creation"),
) -> None:
    """Create a durable Ursa cluster-job object."""

    body = {
        "cluster_euid": cluster_euid,
        "job_type": job_type,
        "request": _parse_json_object(request_json, option_name="--request-json"),
        "start": bool(start),
    }
    for key, value in {
        "job_name": job_name,
        "analysis_job_euid": analysis_job_euid,
        "scheduler_job_id": scheduler_job_id,
    }.items():
        if str(value or "").strip():
            body[key] = value
    cli_output.emit_json(
        _request(
            api_base_url=api_base_url,
            token=token,
            method="POST",
            path="/api/v1/cluster-jobs",
            body=body,
        )
    )


def start_cluster_job(
    cluster_job_euid: str = typer.Argument(..., help="Cluster job EUID"),
    api_base_url: str = typer.Option(..., "--api-base-url", help="Ursa API base URL"),
    token: str = typer.Option(..., "--token", help="Bearer token"),
) -> None:
    """Start a queued Ursa cluster-job worker."""

    cli_output.emit_json(
        _request(
            api_base_url=api_base_url,
            token=token,
            method="POST",
            path=f"/api/v1/cluster-jobs/{cluster_job_euid}/start",
            body={},
        )
    )


def get_cluster_job(
    cluster_job_euid: str = typer.Argument(..., help="Cluster job EUID"),
    api_base_url: str = typer.Option(..., "--api-base-url", help="Ursa API base URL"),
    token: str = typer.Option(..., "--token", help="Bearer token"),
) -> None:
    """Fetch one Ursa cluster-job object."""

    cli_output.emit_json(
        _request(
            api_base_url=api_base_url,
            token=token,
            method="GET",
            path=f"/api/v1/cluster-jobs/{cluster_job_euid}",
        )
    )


def get_run_directory_trigger(
    trigger_euid: str = typer.Argument(..., help="Run-directory trigger EUID"),
    api_base_url: str = typer.Option(..., "--api-base-url", help="Ursa API base URL"),
    token: str = typer.Option(..., "--token", help="Ursa write service token"),
) -> None:
    """Fetch an OWY/Dewey run-directory trigger with its current job statuses."""

    cli_output.emit_json(
        _request(
            api_base_url=api_base_url,
            token=token,
            method="GET",
            path=f"/api/v1/dewey/run-directory-analysis-triggers/{trigger_euid}",
            auth_mode="api-key",
        )
    )


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    """cli-core-yo plugin: register Ursa API command groups."""

    _ = spec
    register_group_commands(
        registry,
        "api",
        "Explicit Ursa API operations",
        [("request", request, REQUIRED_JSON)],
    )
    register_group_commands(
        registry,
        "compute-clusters",
        "Ursa compute-cluster operations",
        [
            ("list", list_compute_clusters, REQUIRED_JSON),
            ("create", create_compute_cluster, REQUIRED_MUTATING_JSON),
            ("get", get_compute_cluster, REQUIRED_JSON),
        ],
    )
    register_group_commands(
        registry,
        "cluster-jobs",
        "Ursa cluster-job operations",
        [
            ("list", list_cluster_jobs, REQUIRED_JSON),
            ("create", create_cluster_job, REQUIRED_MUTATING_JSON),
            ("start", start_cluster_job, REQUIRED_MUTATING_JSON),
            ("get", get_cluster_job, REQUIRED_JSON),
        ],
    )
    register_group_commands(
        registry,
        "run-directory-triggers",
        "Ursa run-directory trigger operations",
        [("get", get_run_directory_trigger, REQUIRED_JSON)],
    )
