from __future__ import annotations

import configparser
import contextlib
from importlib import import_module
from importlib import metadata as importlib_metadata
import json
import os
from packaging.version import InvalidVersion, Version
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, Mapping, Optional, Sequence, cast

DAYLILY_EC_DISTRIBUTION = "daylily-ephemeral-cluster"
REQUIRED_DAYLILY_EC_VERSION = "5.0.22"
MINIMUM_DAYLILY_EC_VERSION = REQUIRED_DAYLILY_EC_VERSION
DAYLILY_EC_VERSION_REQUIREMENT = f"=={REQUIRED_DAYLILY_EC_VERSION}"
DAYLILY_EC_INSTALL_SPEC = f"{DAYLILY_EC_DISTRIBUTION}{DAYLILY_EC_VERSION_REQUIREMENT}"


class _CasePreservingConfigParser(configparser.RawConfigParser):
    def optionxform(self, optionstr: str) -> str:
        return optionstr


def require_daylily_ec_version() -> str:
    """Require the installed daylily-ec distribution to satisfy Ursa's contract."""

    try:
        installed = importlib_metadata.version(DAYLILY_EC_DISTRIBUTION)
    except importlib_metadata.PackageNotFoundError as exc:
        raise RuntimeError(
            f"{DAYLILY_EC_DISTRIBUTION} is not installed. Install "
            f"{DAYLILY_EC_INSTALL_SPEC} in the active Ursa environment."
        ) from exc
    try:
        installed_version = Version(installed)
    except InvalidVersion as exc:
        raise RuntimeError(
            f"{DAYLILY_EC_DISTRIBUTION} version mismatch: expected "
            f"{DAYLILY_EC_VERSION_REQUIREMENT}, found invalid version {installed!r}."
        ) from exc
    if installed_version != Version(REQUIRED_DAYLILY_EC_VERSION):
        raise RuntimeError(
            f"{DAYLILY_EC_DISTRIBUTION} version mismatch: expected "
            f"{DAYLILY_EC_VERSION_REQUIREMENT}, found {installed}."
        )
    return installed


DAYEC_CLUSTER_CONFIG_FIELDS = (
    "reference_s3_uri",
    "control_data_s3_uri",
    "stage_s3_uri",
    "export_destination_s3_uri",
    "public_subnet_id",
    "private_subnet_id",
    "iam_policy_arn",
    "cluster_name",
    "budget_email",
    "allowed_budget_users",
    "budget_amount",
    "global_allowed_budget_users",
    "global_budget_amount",
    "enforce_budget",
    "cluster_template_yaml",
    "headnode_instance_type",
    "fsx_fs_size",
    "enable_detailed_monitoring",
    "delete_local_root",
    "auto_delete_fsx",
    "heartbeat_email",
    "heartbeat_schedule",
    "heartbeat_scheduler_role_arn",
    "spot_instance_allocation_strategy",
    "max_count_8I",
    "max_count_128I",
    "max_count_192I",
)


def _command_env(
    *,
    aws_profile: Optional[str],
    contact_email: Optional[str] = None,
    extra_env: Mapping[str, str] | None = None,
) -> Dict[str, str]:
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    if aws_profile:
        env["AWS_PROFILE"] = aws_profile
    if contact_email:
        env["DAY_CONTACT_EMAIL"] = contact_email
    if extra_env:
        env.update({str(key): str(value) for key, value in extra_env.items()})
    return env


def _aws_profile_section_name(profile: str) -> str:
    resolved = str(profile or "").strip()
    if not resolved:
        raise ValueError("AWS profile is required to build an AWS CLI profile section")
    if resolved == "default":
        return "default"
    return f"profile {resolved}"


def _s3_settings_without_acceleration(raw_value: str) -> str:
    existing = [line.strip() for line in str(raw_value or "").splitlines() if line.strip()]
    retained = [line for line in existing if not line.lower().startswith("use_accelerate_endpoint")]
    retained.append("use_accelerate_endpoint = false")
    return "\n" + "\n".join(f"    {line}" for line in retained)


def _write_aws_config_with_s3_acceleration_disabled(
    *,
    source: Path,
    dest: Path,
    profile: str,
) -> Path:
    parser = _CasePreservingConfigParser()
    if source.exists():
        read_paths = parser.read(source)
        if not read_paths:
            raise RuntimeError(f"Failed to read AWS config file: {source}")
    section = _aws_profile_section_name(profile)
    if not parser.has_section(section):
        parser.add_section(section)
    existing_s3 = parser.get(section, "s3") if parser.has_option(section, "s3") else ""
    parser.set(section, "s3", _s3_settings_without_acceleration(existing_s3))
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8") as handle:
        parser.write(handle)
    return dest


@contextlib.contextmanager
def _command_env_context(env: Mapping[str, str]) -> Iterator[Dict[str, str]]:
    child_env = dict(env)
    profile = str(child_env.get("AWS_PROFILE") or "").strip()
    if not profile:
        yield child_env
        return
    source = Path(
        str(child_env.get("AWS_CONFIG_FILE") or Path.home() / ".aws" / "config")
    ).expanduser()
    with tempfile.TemporaryDirectory(prefix="ursa-aws-config-") as tmpdir:
        config_path = _write_aws_config_with_s3_acceleration_disabled(
            source=source,
            dest=Path(tmpdir) / "config",
            profile=profile,
        )
        child_env["AWS_CONFIG_FILE"] = str(config_path)
        yield child_env


def _summarize_process_output(
    result: subprocess.CompletedProcess[str], *, max_chars: int = 4000
) -> str:
    output = (result.stderr or "").strip() or (result.stdout or "").strip()
    if not output:
        return f"exit code {result.returncode}"
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    tail = "\n".join(lines[-25:]) if lines else output
    if len(tail) > max_chars:
        return tail[-max_chars:]
    return tail


class DaylilyEcClient:
    """Strict Ursa client for the daylily-ephemeral-cluster ==5.0.22 contract."""

    def __init__(
        self,
        *,
        aws_profile: Optional[str] = None,
        python_executable: str | None = None,
    ) -> None:
        require_daylily_ec_version()
        self.aws_profile = aws_profile
        self.python_executable = python_executable or sys.executable

    def command(self, args: Iterable[str], *, json_mode: bool = False) -> list[str]:
        argv = [self.python_executable, "-m", "daylily_ec.cli"]
        if json_mode:
            argv.append("--json")
        argv.extend(str(item) for item in args)
        return argv

    def run(
        self,
        args: Iterable[str],
        *,
        json_mode: bool = False,
        aws_profile: Optional[str] = None,
        contact_email: Optional[str] = None,
        cwd: Optional[Path] = None,
        check: bool = False,
        timeout: Optional[int] = None,
        extra_env: Mapping[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        env = _command_env(
            aws_profile=aws_profile if aws_profile is not None else self.aws_profile,
            contact_email=contact_email,
            extra_env=extra_env,
        )
        with _command_env_context(env) as child_env:
            result = subprocess.run(
                self.command(args, json_mode=json_mode),
                text=True,
                capture_output=True,
                cwd=str(cwd) if cwd else None,
                env=child_env,
                timeout=timeout,
                check=False,
            )
        if check and result.returncode != 0:
            raise RuntimeError(_summarize_process_output(result))
        return result

    def run_json(
        self,
        args: Iterable[str],
        *,
        aws_profile: Optional[str] = None,
        cwd: Optional[Path] = None,
        timeout: Optional[int] = None,
    ) -> Dict[str, Any]:
        result = self.run(
            args,
            json_mode=True,
            aws_profile=aws_profile,
            cwd=cwd,
            timeout=timeout,
        )
        if result.returncode != 0:
            raise RuntimeError(_summarize_process_output(result))
        if not str(result.stdout or "").strip():
            detail = (result.stderr or "").strip() or "daylily-ec returned empty JSON output"
            raise RuntimeError(detail)
        try:
            payload = json.loads(result.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"daylily-ec returned invalid JSON: {exc}") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("daylily-ec returned non-object JSON")
        return cast(Dict[str, Any], payload)

    def repository_commands(self) -> Dict[str, Any]:
        return self.run_json(["repositories", "commands"])

    def cluster_list(self, *, region: str, details: bool = True) -> Dict[str, Any]:
        args = ["cluster", "list", "--region", region]
        if details:
            args.append("--details")
        if self.aws_profile:
            args.extend(["--profile", self.aws_profile])
        return self.run_json(args)

    def cluster_describe(self, *, cluster_name: str, region: str) -> Dict[str, Any]:
        args = ["cluster", "describe", "--region", region, "--cluster", cluster_name]
        if self.aws_profile:
            args.extend(["--profile", self.aws_profile])
        return self.run_json(args)

    def workflow_status(
        self, *, session_name: str, region: str, cluster_name: str
    ) -> Dict[str, Any]:
        args = [
            "workflow",
            "status",
            "--session",
            session_name,
            "--region",
            region,
            "--cluster",
            cluster_name,
        ]
        if self.aws_profile:
            args.extend(["--profile", self.aws_profile])
        return self.run_json(args)

    def workflow_logs(
        self,
        *,
        session_name: str,
        region: str,
        cluster_name: str,
        lines: int = 200,
    ) -> subprocess.CompletedProcess[str]:
        args = [
            "workflow",
            "logs",
            "--session",
            session_name,
            "--region",
            region,
            "--cluster",
            cluster_name,
            "--lines",
            str(lines),
        ]
        if self.aws_profile:
            args.extend(["--profile", self.aws_profile])
        return self.run(args)

    def stage_samples(
        self,
        *,
        analysis_samples: Path,
        reference_s3_uri: str,
        config_dir: Path,
        region: str,
        stage_target: str | None = None,
        aws_profile: Optional[str] = None,
        debug: bool = False,
        cwd: Optional[Path] = None,
    ) -> subprocess.CompletedProcess[str]:
        args = [
            "samples",
            "stage",
            str(analysis_samples),
            "--reference-s3-uri",
            reference_s3_uri,
            "--config-dir",
            str(config_dir),
            "--region",
            region,
        ]
        resolved_profile = aws_profile if aws_profile is not None else self.aws_profile
        if stage_target:
            args.extend(["--stage-target", stage_target])
        if resolved_profile:
            args.extend(["--profile", resolved_profile])
        if debug:
            args.append("--debug")
        return self.run(args, cwd=cwd)

    def workflow_launch(
        self,
        args: Iterable[str],
        *,
        cwd: Optional[Path] = None,
    ) -> subprocess.CompletedProcess[str]:
        return self.run(args, cwd=cwd)

    def export_analysis_results(
        self,
        *,
        cluster_name: str,
        source_path: str,
        destination_s3_uri: str,
        region: str,
        output_dir: str,
        aws_profile: Optional[str] = None,
    ) -> subprocess.CompletedProcess[str]:
        args = [
            "export",
            "--cluster-name",
            cluster_name,
            "--source-path",
            source_path,
            "--destination-s3-uri",
            destination_s3_uri,
            "--region",
            region,
            "--output-dir",
            output_dir,
        ]
        resolved_profile = aws_profile if aws_profile is not None else self.aws_profile
        if resolved_profile:
            args.extend(["--profile", resolved_profile])
        return self.run(args)

    def delete_dry_run(self, *, cluster_name: str, region: str) -> subprocess.CompletedProcess[str]:
        args = [
            "delete",
            "--dry-run",
            "--cluster-name",
            cluster_name,
            "--region",
            region,
        ]
        if self.aws_profile:
            args.extend(["--profile", self.aws_profile])
        return self.run(args)

    def delete(self, *, cluster_name: str, region: str) -> subprocess.CompletedProcess[str]:
        args = ["delete", "--yes", "--cluster-name", cluster_name, "--region", region]
        if self.aws_profile:
            args.extend(["--profile", self.aws_profile])
        return self.run(args)


def get_daylily_ec_client(*, aws_profile: Optional[str] = None) -> DaylilyEcClient:
    return DaylilyEcClient(aws_profile=aws_profile)


def write_dayec_cluster_config(
    *,
    dest: Path,
    cluster_name: str,
    ssh_key_name: str,
    reference_s3_uri: str,
    control_data_s3_uri: str,
    stage_s3_uri: str,
    export_destination_s3_uri: str,
    contact_email: Optional[str],
    config_values: Mapping[str, Any] | None = None,
) -> Path:
    """Write a non-interactive cluster request through the day-ec library."""

    require_daylily_ec_version()
    module = import_module("daylily_ec.config")
    builder = getattr(module, "build_noninteractive_cluster_config", None)
    writer = getattr(module, "write_config", None)
    triplet_type = getattr(module, "Triplet", None)
    if not callable(builder) or not callable(writer) or triplet_type is None:
        raise RuntimeError("daylily_ec.config non-interactive config helpers are not available")

    cfg = builder(
        cluster_name=cluster_name,
        ssh_key_name=ssh_key_name,
        reference_s3_uri=reference_s3_uri,
        control_data_s3_uri=control_data_s3_uri,
        stage_s3_uri=stage_s3_uri,
        export_destination_s3_uri=export_destination_s3_uri,
        contact_email=contact_email,
    )
    for key, raw_value in dict(config_values or {}).items():
        if key not in DAYEC_CLUSTER_CONFIG_FIELDS and key != "ssh_key_name":
            raise ValueError(f"Unsupported daylily-ec cluster config field: {key}")
        value = str(raw_value or "").strip()
        if not value:
            continue
        cfg.ephemeral_cluster.config[key] = triplet_type(
            action="USESETVALUE",
            default_value="",
            set_value=value,
        )
    writer(cfg, dest)
    return Path(dest)


def _cluster_command_args(
    verb: str,
    *,
    region_az: str,
    aws_profile: Optional[str],
    config_path: Path,
    pass_on_warn: bool,
    debug: bool,
    repo_overrides: Sequence[str] | None = None,
) -> list[str]:
    command = [
        verb,
        "--region-az",
        region_az,
        "--config",
        str(config_path),
        "--non-interactive",
    ]
    if aws_profile:
        command.extend(["--profile", aws_profile])
    if pass_on_warn:
        command.append("--pass-on-warn")
    if debug:
        command.append("--debug")
    if verb == "create":
        for override in list(repo_overrides or []):
            if str(override or "").strip():
                command.extend(["--repo-override", str(override).strip()])
    return command


def run_preflight_sync(
    *,
    region_az: str,
    aws_profile: Optional[str],
    config_path: Path,
    pass_on_warn: bool,
    debug: bool,
    contact_email: Optional[str],
    repo_overrides: Sequence[str] | None = None,
    cwd: Optional[Path] = None,
) -> subprocess.CompletedProcess[str]:
    client = get_daylily_ec_client(aws_profile=aws_profile)
    return client.run(
        _cluster_command_args(
            "preflight",
            region_az=region_az,
            aws_profile=aws_profile,
            config_path=config_path,
            pass_on_warn=pass_on_warn,
            debug=debug,
            repo_overrides=repo_overrides,
        ),
        contact_email=contact_email,
        cwd=cwd,
    )


def run_create_dry_run_sync(
    *,
    region_az: str,
    aws_profile: Optional[str],
    config_path: str,
    pass_on_warn: bool,
    debug: bool,
    contact_email: Optional[str],
    repo_overrides: Sequence[str] | None = None,
    cwd: Optional[Path] = None,
) -> subprocess.CompletedProcess[str]:
    resolved_config_path = Path(config_path).expanduser()
    if not resolved_config_path.is_absolute():
        resolved_config_path = ((cwd or Path.cwd()) / resolved_config_path).resolve()
    client = get_daylily_ec_client(aws_profile=aws_profile)
    return client.run(
        _cluster_command_args(
            "create",
            region_az=region_az,
            aws_profile=aws_profile,
            config_path=resolved_config_path,
            pass_on_warn=pass_on_warn,
            debug=debug,
            repo_overrides=repo_overrides,
        ),
        contact_email=contact_email,
        cwd=cwd,
        extra_env={"DAY_BREAK": "1"},
    )


def run_aws_validate_all_sync(
    *,
    region_az: str,
    aws_profile: str,
    gap_analysis_path: Path,
    config_path: str | None = None,
    cwd: Optional[Path] = None,
) -> subprocess.CompletedProcess[str]:
    args = [
        "aws",
        "validate",
        "all",
        "--profile",
        aws_profile,
        "--region-az",
        region_az,
    ]
    if config_path:
        args.extend(["--config", config_path])
    args.extend(["--gap-analysis", str(gap_analysis_path)])
    client = get_daylily_ec_client(aws_profile=aws_profile)
    return client.run(args, json_mode=True, cwd=cwd)


def run_create_sync(
    *,
    region_az: str,
    aws_profile: Optional[str],
    config_path: str,
    pass_on_warn: bool,
    debug: bool,
    contact_email: Optional[str],
    repo_overrides: Sequence[str] | None = None,
    cwd: Optional[Path] = None,
) -> subprocess.CompletedProcess[str]:
    resolved_config_path = Path(config_path).expanduser()
    if not resolved_config_path.is_absolute():
        resolved_config_path = ((cwd or Path.cwd()) / resolved_config_path).resolve()
    client = get_daylily_ec_client(aws_profile=aws_profile)
    return client.run(
        _cluster_command_args(
            "create",
            region_az=region_az,
            aws_profile=aws_profile,
            config_path=resolved_config_path,
            pass_on_warn=pass_on_warn,
            debug=debug,
            repo_overrides=repo_overrides,
        ),
        contact_email=contact_email,
        cwd=cwd,
    )


__all__ = [
    "DAYLILY_EC_DISTRIBUTION",
    "REQUIRED_DAYLILY_EC_VERSION",
    "MINIMUM_DAYLILY_EC_VERSION",
    "DAYLILY_EC_VERSION_REQUIREMENT",
    "DaylilyEcClient",
    "_summarize_process_output",
    "get_daylily_ec_client",
    "require_daylily_ec_version",
    "run_aws_validate_all_sync",
    "run_create_sync",
    "run_create_dry_run_sync",
    "run_preflight_sync",
    "write_dayec_cluster_config",
]
