"""TapDB lifecycle and Ursa overlay commands."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cli_core_yo.registry import CommandRegistry
    from cli_core_yo.spec import CliSpec

import typer
from rich.console import Console

from daylib_ursa.cli._registry_v2 import (
    REQUIRED_MUTATING,
    REQUIRED_MUTATING_INTERACTIVE,
    register_group_commands,
)
from daylib_ursa.analysis_store import AnalysisStore
from daylib_ursa.config import get_settings
from daylib_ursa.integrations.tapdb_runtime import (
    TapDBRuntimeError,
    ensure_local_tapdb_namespace_config,
    ensure_tapdb_version,
    export_database_url_for_target,
    run_tapdb_cli,
)

console = Console()
db_app = typer.Typer(help="TapDB lifecycle and Ursa overlay commands")


def _bootstrap_ursa_templates() -> None:
    store = AnalysisStore()
    store.bootstrap()


def _resolved_runtime_defaults(
    *,
    profile: str,
    region: str,
    namespace: str,
) -> tuple[str, str, str, str, str]:
    settings = get_settings()
    effective_client_id = str(getattr(settings, "tapdb_client_id", "") or "").strip()
    if not effective_client_id:
        raise TapDBRuntimeError("tapdb_client_id is required")
    effective_profile = str(profile or getattr(settings, "aws_profile", "") or "").strip()
    if not effective_profile:
        raise TapDBRuntimeError("AWS profile is required")

    effective_region = str(region or "").strip()
    if not effective_region:
        resolver = getattr(settings, "get_effective_region", None)
        if callable(resolver):
            effective_region = str(resolver() or "").strip()
    if not effective_region:
        raise TapDBRuntimeError("AWS region is required")

    effective_namespace = str(
        namespace or getattr(settings, "tapdb_database_name", "") or ""
    ).strip()
    if not effective_namespace:
        raise TapDBRuntimeError("tapdb_database_name is required")

    effective_config_path = str(getattr(settings, "tapdb_config_path", "") or "").strip()

    return (
        effective_client_id,
        effective_profile,
        effective_region,
        effective_namespace,
        effective_config_path,
    )


def _validate_target(target: str) -> str:
    normalized = str(target or "").strip().lower()
    if normalized not in {"local", "aurora"}:
        raise TapDBRuntimeError("Unsupported database target. Use local or aurora.")
    return normalized


def _confirm_target_label(*, namespace: str) -> str:
    settings = get_settings()
    schema_name = str(getattr(settings, "tapdb_schema_name", "") or "").strip()
    physical_database = str(getattr(settings, "tapdb_physical_database", "") or namespace).strip()
    if not schema_name:
        raise TapDBRuntimeError("tapdb_schema_name is required for destructive confirmation.")
    client_id = str(getattr(settings, "tapdb_client_id", "") or "").strip()
    if not client_id:
        raise TapDBRuntimeError("tapdb_client_id is required for destructive confirmation.")
    return f"{client_id}/{namespace}/{schema_name}@{physical_database}"


def _apply_ursa_overlay(*, start_step: int, total_steps: int) -> None:
    console.print(
        f"[cyan]Step {start_step}/{total_steps}:[/cyan] Applying Ursa TapDB template overlay"
    )
    _bootstrap_ursa_templates()


def _build_target(
    *,
    target: str,
    cluster: str,
    profile: str,
    region: str,
    namespace: str,
    overlay_start_step: int,
    overlay_total_steps: int,
) -> None:
    ensure_tapdb_version()
    target = _validate_target(target)
    client_id, profile, region, namespace, config_path = _resolved_runtime_defaults(
        profile=profile,
        region=region,
        namespace=namespace,
    )
    if target == "local":
        ensure_local_tapdb_namespace_config(
            client_id=client_id,
            profile=profile,
            region=region,
            namespace=namespace,
            config_path=config_path,
        )
        result = run_tapdb_cli(
            args=["bootstrap", "local", "--no-gui"],
            target=target,
            client_id=client_id,
            profile=profile,
            region=region,
            namespace=namespace,
            config_path=config_path,
        )
    else:
        if not cluster.strip():
            raise TapDBRuntimeError("--cluster is required for aurora target")
        result = run_tapdb_cli(
            args=[
                "bootstrap",
                "aurora",
                "--cluster",
                cluster.strip(),
                "--region",
                region,
                "--no-gui",
            ],
            target=target,
            client_id=client_id,
            profile=profile,
            region=region,
            namespace=namespace,
            config_path=config_path,
        )
    if result.stdout:
        console.print(result.stdout.rstrip())

    db_url = export_database_url_for_target(
        target=target,
        client_id=client_id,
        profile=profile,
        region=region,
        namespace=namespace,
        config_path=config_path,
    )
    console.print(f"[green]DATABASE_URL[/green] resolved: [dim]{db_url}[/dim]")
    _apply_ursa_overlay(start_step=overlay_start_step, total_steps=overlay_total_steps)
    console.print("[green]Ursa TapDB overlay complete[/green]")


@db_app.command("build")
def build(
    target: str = typer.Option("local", "--target", help="TapDB target: local|aurora"),
    cluster: str = typer.Option("", "--cluster", help="Aurora cluster ID for aurora target"),
    profile: str = typer.Option("", "--profile", help="AWS profile"),
    region: str = typer.Option("", "--region", help="AWS region"),
    namespace: str = typer.Option("", "--namespace", help="TapDB namespace"),
) -> None:
    """Bootstrap TapDB runtime and apply the Ursa overlay.

    Examples:
        ursa db build --target local
        ursa db build --target aurora --cluster daylily-ursa-dev
    """
    try:
        _build_target(
            target=target,
            cluster=cluster,
            profile=profile,
            region=region,
            namespace=namespace,
            overlay_start_step=3,
            overlay_total_steps=3,
        )
    except TapDBRuntimeError as exc:
        console.print(f"[red]DB build failed:[/red] {exc}")
        raise typer.Exit(1) from exc


@db_app.command("seed")
def seed(
    target: str = typer.Option("local", "--target", help="TapDB target: local|aurora"),
    profile: str = typer.Option("", "--profile", help="AWS profile"),
    region: str = typer.Option("", "--region", help="AWS region"),
    namespace: str = typer.Option("", "--namespace", help="TapDB namespace"),
) -> None:
    """Apply the Ursa TapDB template overlay only."""
    try:
        target = _validate_target(target)
        client_id, profile, region, namespace, config_path = _resolved_runtime_defaults(
            profile=profile,
            region=region,
            namespace=namespace,
        )
        db_url = export_database_url_for_target(
            target=target,
            client_id=client_id,
            profile=profile,
            region=region,
            namespace=namespace,
            config_path=config_path,
        )
        console.print(f"[green]DATABASE_URL[/green] resolved: [dim]{db_url}[/dim]")
        _apply_ursa_overlay(start_step=1, total_steps=1)
    except Exception as exc:
        console.print(f"[red]DB seed failed:[/red] {exc}")
        raise typer.Exit(1) from exc


@db_app.command("reset")
def reset(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    target: str = typer.Option("local", "--target", help="TapDB target: local|aurora"),
    cluster: str = typer.Option("", "--cluster", help="Aurora cluster ID for aurora target"),
    profile: str = typer.Option("", "--profile", help="AWS profile"),
    region: str = typer.Option("", "--region", help="AWS region"),
    namespace: str = typer.Option("", "--namespace", help="TapDB namespace"),
) -> None:
    """Delete and rebuild the TapDB target, then apply the Ursa overlay."""
    if not force and not typer.confirm("This will delete the current TapDB DB target. Continue?"):
        raise typer.Exit(0)

    try:
        target = _validate_target(target)
        client_id, profile, region, namespace, config_path = _resolved_runtime_defaults(
            profile=profile,
            region=region,
            namespace=namespace,
        )
        run_tapdb_cli(
            args=["db", "delete", "--confirm-target", _confirm_target_label(namespace=namespace)],
            target=target,
            client_id=client_id,
            profile=profile,
            region=region,
            namespace=namespace,
            config_path=config_path,
        )
    except TapDBRuntimeError as exc:
        console.print(f"[red]Delete failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    try:
        _build_target(
            target=target,
            cluster=cluster,
            profile=profile,
            region=region,
            namespace=namespace,
            overlay_start_step=4,
            overlay_total_steps=4,
        )
    except TapDBRuntimeError as exc:
        console.print(f"[red]DB build failed:[/red] {exc}")
        raise typer.Exit(1) from exc


@db_app.command("nuke")
def nuke(
    force: bool = typer.Option(False, "--force", "-f", help="Skip confirmation"),
    target: str = typer.Option("local", "--target", help="TapDB target: local|aurora"),
    profile: str = typer.Option("", "--profile", help="AWS profile"),
    region: str = typer.Option("", "--region", help="AWS region"),
    namespace: str = typer.Option("", "--namespace", help="TapDB namespace"),
) -> None:
    """Delete the TapDB target without rebuilding."""
    if not force and not typer.confirm("This will delete the current TapDB DB target. Continue?"):
        raise typer.Exit(0)

    try:
        target = _validate_target(target)
        client_id, profile, region, namespace, config_path = _resolved_runtime_defaults(
            profile=profile,
            region=region,
            namespace=namespace,
        )
        run_tapdb_cli(
            args=["db", "delete", "--confirm-target", _confirm_target_label(namespace=namespace)],
            target=target,
            client_id=client_id,
            profile=profile,
            region=region,
            namespace=namespace,
            config_path=config_path,
        )
    except TapDBRuntimeError as exc:
        console.print(f"[red]Delete failed:[/red] {exc}")
        raise typer.Exit(1) from exc


def register(registry: CommandRegistry, spec: CliSpec) -> None:
    """Register the db command group."""
    _ = spec
    register_group_commands(
        registry,
        "db",
        "TapDB lifecycle and overlay commands",
        [
            ("build", build, REQUIRED_MUTATING),
            ("seed", seed, REQUIRED_MUTATING),
            ("reset", reset, REQUIRED_MUTATING_INTERACTIVE),
            ("nuke", nuke, REQUIRED_MUTATING_INTERACTIVE),
        ],
    )
