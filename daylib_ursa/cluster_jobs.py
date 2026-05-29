from __future__ import annotations

import logging
import os
import re
import shlex
import subprocess
import sys
import uuid
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from daylib_ursa.cluster_service import ClusterService
from daylib_ursa.ephemeral_cluster.runner import (
    _summarize_process_output,
    run_create_sync,
    run_preflight_sync,
    write_dayec_cluster_config,
)
from daylib_ursa.resource_store import ClusterJobRecord, ResourceStore
from daylib_ursa.tapdb_graph import utc_now_iso

LOGGER = logging.getLogger("daylily.ursa.cluster_jobs")
_SAFE_TMUX_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_SAFE_GENOME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")
_SAFE_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]*$")
_ALLOWED_DAYOA_DYR_HELP_ENV_KEYS = {"PUPPETEER_EXECUTABLE_PATH", "PUPPETEER_CACHE_DIR"}


def region_from_region_az(region_az: str) -> str:
    value = str(region_az or "").strip()
    if len(value) > 1 and value[-1].isalpha() and value[-2].isdigit():
        return value[:-1]
    return value


def _request_string(request: dict[str, Any], key: str, *, required: bool = True) -> str:
    value = str(request.get(key) or "").strip()
    if required and not value:
        raise ValueError(f"{key} is required")
    return value


def _request_int(request: dict[str, Any], key: str, *, minimum: int, maximum: int) -> int:
    raw = request.get(key)
    if raw is None or str(raw).strip() == "":
        raise ValueError(f"{key} is required")
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer") from exc
    if value < minimum or value > maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}")
    return value


def _request_environment(request: dict[str, Any]) -> dict[str, str]:
    raw = request.get("environment") or {}
    if not isinstance(raw, dict):
        raise ValueError("environment must be an object")
    environment: dict[str, str] = {}
    for raw_key, raw_value in raw.items():
        key = str(raw_key or "").strip()
        if key not in _ALLOWED_DAYOA_DYR_HELP_ENV_KEYS or not _SAFE_ENV_KEY_RE.fullmatch(key):
            allowed = ", ".join(sorted(_ALLOWED_DAYOA_DYR_HELP_ENV_KEYS))
            raise ValueError(f"environment keys must be one of: {allowed}")
        value = str(raw_value or "").strip()
        if not value:
            raise ValueError(f"environment.{key} must not be empty")
        if "\n" in value or "\x00" in value:
            raise ValueError(f"environment.{key} contains unsupported characters")
        if key.endswith("_PATH") or key.endswith("_DIR"):
            if not value.startswith("/"):
                raise ValueError(f"environment.{key} must be an absolute path")
        environment[key] = value
    return environment


def _dayoa_dyr_help_script(
    *,
    job: ClusterJobRecord,
    analysis_dir: str,
    executor: str,
    genome_build: str,
    tmux_session: str,
    timeout_seconds: int,
    environment: dict[str, str],
) -> str:
    marker_path = f"/tmp/ursa-cluster-job-{job.job_euid}.rc"
    output_path = f"/tmp/ursa-cluster-job-{job.job_euid}.out"
    remote_command = (
        "dy-r help; rc=$?; "
        f"tmux capture-pane -pt {shlex.quote(tmux_session)} -S -400 > {shlex.quote(output_path)}; "
        f"printf '%s\\n' \"$rc\" > {shlex.quote(marker_path)}; "
        "exit \"$rc\""
    )
    tmux_commands = [
        f"tmux send-keys -t \"$session\" {shlex.quote('cd ' + shlex.quote(analysis_dir))} Enter",
    ]
    for key, value in sorted(environment.items()):
        tmux_commands.append(
            f"tmux send-keys -t \"$session\" {shlex.quote('export ' + key + '=' + shlex.quote(value))} Enter"
        )
    tmux_commands.extend(
        [
            'tmux send-keys -t "$session" "source dyoainit" Enter',
            f"tmux send-keys -t \"$session\" {shlex.quote('dy-a ' + executor + ' ' + genome_build)} Enter",
            f"tmux send-keys -t \"$session\" {shlex.quote(remote_command)} Enter",
        ]
    )
    inner = "; ".join(
        [
            "set -e",
            'test "$(id -un)" = ubuntu',
            "command -v tmux >/dev/null",
            f"analysis_dir={shlex.quote(analysis_dir)}",
            f"session={shlex.quote(tmux_session)}",
            f"marker={shlex.quote(marker_path)}",
            f"output={shlex.quote(output_path)}",
            'test -d "$analysis_dir"',
            'test -f "$analysis_dir/dyoainit"',
            'rm -f "$marker" "$output"',
            'if tmux has-session -t "$session" 2>/dev/null; then '
            'printf "tmux session already exists: %s\\n" "$session"; exit 2; fi',
            'tmux new-session -d -s "$session" "bash -l"',
            "sleep 1",
            *tmux_commands,
            f"deadline=$((SECONDS + {timeout_seconds}))",
            'while [ ! -f "$marker" ] && [ "$SECONDS" -lt "$deadline" ]; do sleep 2; done',
            'if [ ! -f "$marker" ]; then '
            'tmux capture-pane -pt "$session" -S -400 > "$output" 2>/dev/null || true; '
            'cat "$output" 2>/dev/null || true; '
            'printf "__URSA_CLUSTER_JOB_TIMEOUT__=1\\n"; exit 124; fi',
            'cat "$output" 2>/dev/null || true',
            'rc=$(cat "$marker")',
            'printf "__URSA_CLUSTER_JOB_RC__=%s\\n" "$rc"',
            'exit "$rc"',
        ]
    )
    return "sudo -u ubuntu HOME=/home/ubuntu bash -lc " + shlex.quote(inner)


def _validate_dayoa_dyr_help_request(job: ClusterJobRecord) -> dict[str, Any]:
    request = dict(job.request or {})
    command = _request_string(request, "command")
    if command != "dy-r help":
        raise ValueError("cluster job command must be exactly 'dy-r help'")
    analysis_dir = _request_string(request, "analysis_dir")
    if not analysis_dir.startswith("/"):
        raise ValueError("analysis_dir must be an absolute headnode path")
    executor = _request_string(request, "executor")
    if executor not in {"local", "slurm"}:
        raise ValueError("executor must be local or slurm")
    genome_build = _request_string(request, "genome_build")
    if not _SAFE_GENOME_RE.fullmatch(genome_build):
        raise ValueError("genome_build contains unsupported characters")
    tmux_session = _request_string(request, "tmux_session")
    if not _SAFE_TMUX_RE.fullmatch(tmux_session):
        raise ValueError("tmux_session contains unsupported characters")
    timeout_seconds = _request_int(
        request,
        "timeout_seconds",
        minimum=10,
        maximum=900,
    )
    aws_profile = _request_string(request, "aws_profile")
    environment = _request_environment(request)
    return {
        "command": command,
        "analysis_dir": analysis_dir,
        "executor": executor,
        "genome_build": genome_build,
        "tmux_session": tmux_session,
        "timeout_seconds": timeout_seconds,
        "aws_profile": aws_profile,
        "environment": environment,
    }


def run_dayoa_dyr_help_job(
    *,
    resource_store: ResourceStore,
    cluster_service: ClusterService,
    job_euid: str,
) -> None:
    job = resource_store.get_cluster_job(job_euid)
    if job is None:
        raise KeyError(f"cluster job not found: {job_euid}")
    sponsor_user_id = str(job.sponsor_user_id or job.owner_user_id or "").strip()
    started_at = utc_now_iso()
    try:
        params = _validate_dayoa_dyr_help_request(job)
        resource_store.update_cluster_job_status(
            job_euid=job_euid,
            state="RUNNING",
            created_by=sponsor_user_id,
            started_at=started_at,
        )
        resource_store.add_cluster_job_event(
            job_euid=job_euid,
            event_type="headnode-command",
            status="RUNNING",
            summary="Started DayOA dy-r help smoke command",
            details={
                "cluster_name": job.cluster_name,
                "region": job.region,
                "analysis_dir": params["analysis_dir"],
                "tmux_session": params["tmux_session"],
                "command": params["command"],
                "environment_keys": sorted(params["environment"]),
            },
            created_by=sponsor_user_id,
        )
        script = _dayoa_dyr_help_script(
            job=job,
            analysis_dir=params["analysis_dir"],
            executor=params["executor"],
            genome_build=params["genome_build"],
            tmux_session=params["tmux_session"],
            timeout_seconds=int(params["timeout_seconds"]),
            environment=dict(params["environment"]),
        )
        _, result, error_result = cluster_service._run_headnode_script(
            cluster_name=job.cluster_name,
            region=job.region,
            probe_type="cluster-job",
            script=script,
            ttl_seconds=0,
            timeout=int(params["timeout_seconds"]) + 120,
        )
        if error_result is not None:
            payload = error_result.to_dict(cached=False)
            data = dict(payload.get("data") or {})
            error = str(payload.get("error") or "DayOA dy-r help command failed")
            resource_store.add_cluster_job_event(
                job_euid=job_euid,
                event_type="headnode-command",
                status="FAILED",
                summary=error,
                details=data,
                created_by=sponsor_user_id,
            )
            resource_store.update_cluster_job_status(
                job_euid=job_euid,
                state="FAILED",
                created_by=sponsor_user_id,
                started_at=started_at,
                completed_at=utc_now_iso(),
                return_code=int(data.get("response_code") or 1),
                error=error,
                output_summary=error,
                cluster={
                    "cluster_name": job.cluster_name,
                    "region": job.region,
                    "analysis_dir": params["analysis_dir"],
                    "tmux_session": params["tmux_session"],
                    "environment_keys": sorted(params["environment"]),
                    "stdout": str(data.get("stdout") or "")[-8000:],
                    "stderr": str(data.get("stderr") or "")[-8000:],
                },
            )
            return
        assert result is not None
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        summary = "DayOA dy-r help completed"
        resource_store.add_cluster_job_event(
            job_euid=job_euid,
            event_type="headnode-command",
            status="COMPLETED",
            summary=summary,
            details={
                "return_code": int(result.response_code),
                "status": result.status,
                "stdout": stdout[-8000:],
                "stderr": stderr[-8000:],
            },
            created_by=sponsor_user_id,
        )
        resource_store.update_cluster_job_status(
            job_euid=job_euid,
            state="COMPLETED",
            created_by=sponsor_user_id,
            started_at=started_at,
            completed_at=utc_now_iso(),
            return_code=0,
            error=None,
            output_summary=summary,
            cluster={
                "cluster_name": job.cluster_name,
                "region": job.region,
                "analysis_dir": params["analysis_dir"],
                "tmux_session": params["tmux_session"],
                "environment_keys": sorted(params["environment"]),
                "stdout": stdout[-8000:],
                "stderr": stderr[-8000:],
            },
        )
    except Exception as exc:
        LOGGER.exception("DayOA dy-r help cluster job %s failed", job_euid)
        error_message = f"{type(exc).__name__}: {exc}"
        try:
            resource_store.add_cluster_job_event(
                job_euid=job_euid,
                event_type="headnode-command",
                status="FAILED",
                summary=error_message,
                details={},
                created_by=sponsor_user_id,
            )
            resource_store.update_cluster_job_status(
                job_euid=job_euid,
                state="FAILED",
                created_by=sponsor_user_id,
                started_at=started_at,
                completed_at=utc_now_iso(),
                return_code=1,
                error=error_message,
                output_summary=error_message,
            )
        except Exception:
            LOGGER.exception("Failed to persist terminal cluster job state for %s", job_euid)


def run_cluster_create_job(
    *,
    resource_store: ResourceStore,
    cluster_service: ClusterService,
    workspace_root: Path,
    job_euid: str,
) -> None:
    job = resource_store.get_cluster_job(job_euid)
    if job is None:
        raise KeyError(f"cluster job not found: {job_euid}")

    request = dict(job.request or {})
    cluster_name = str(request.get("cluster_name") or job.cluster_name or "").strip()
    region = str(request.get("region") or job.region or "").strip()
    region_az = str(request.get("region_az") or job.region_az or "").strip()
    ssh_key_name = str(request.get("ssh_key_name") or "").strip()
    reference_s3_uri = str(request.get("reference_s3_uri") or "").strip()
    control_data_s3_uri = str(request.get("control_data_s3_uri") or "").strip()
    stage_s3_uri = str(request.get("stage_s3_uri") or "").strip()
    export_destination_s3_uri = str(request.get("export_destination_s3_uri") or "").strip()
    aws_profile = str(request.get("aws_profile") or "").strip() or None
    contact_email = str(request.get("contact_email") or "").strip() or None
    pass_on_warn = bool(request.get("pass_on_warn"))
    debug = bool(request.get("debug"))
    config_path = str(request.get("config_path") or "").strip()
    cluster_config_values = dict(request.get("cluster_config_values") or {})
    repo_overrides = [
        str(item).strip() for item in list(request.get("repo_overrides") or []) if str(item).strip()
    ]
    sponsor_user_id = str(job.sponsor_user_id or job.owner_user_id or "").strip()

    started_at = utc_now_iso()
    try:
        resource_store.update_cluster_job_status(
            job_euid=job_euid,
            state="RUNNING",
            created_by=sponsor_user_id,
            started_at=started_at,
        )
        resource_store.add_cluster_job_event(
            job_euid=job_euid,
            event_type="runner",
            status="RUNNING",
            summary=f"Started cluster creation for {cluster_name}",
            details={"region": region, "region_az": region_az},
            created_by=sponsor_user_id,
        )

        with TemporaryDirectory(prefix="ursa-cluster-") as temp_dir:
            scratch_dir = Path(temp_dir)
            effective_config_path = (
                Path(config_path).expanduser()
                if config_path
                else write_dayec_cluster_config(
                    dest=scratch_dir / "cluster.yaml",
                    cluster_name=cluster_name,
                    ssh_key_name=ssh_key_name,
                    reference_s3_uri=reference_s3_uri,
                    control_data_s3_uri=control_data_s3_uri,
                    stage_s3_uri=stage_s3_uri,
                    export_destination_s3_uri=export_destination_s3_uri,
                    contact_email=contact_email,
                    config_values=cluster_config_values,
                )
            )

            preflight = run_preflight_sync(
                region_az=region_az,
                aws_profile=aws_profile,
                config_path=effective_config_path,
                pass_on_warn=pass_on_warn,
                debug=debug,
                contact_email=contact_email,
                cwd=workspace_root,
            )
            preflight_summary = _summarize_process_output(preflight)
            resource_store.add_cluster_job_event(
                job_euid=job_euid,
                event_type="preflight",
                status="COMPLETED" if preflight.returncode == 0 else "FAILED",
                summary=preflight_summary,
                details={
                    "return_code": int(preflight.returncode),
                    "stdout": (preflight.stdout or "")[-4000:],
                    "stderr": (preflight.stderr or "")[-4000:],
                },
                created_by=sponsor_user_id,
            )
            if preflight.returncode != 0:
                resource_store.update_cluster_job_status(
                    job_euid=job_euid,
                    state="FAILED",
                    created_by=sponsor_user_id,
                    started_at=started_at,
                    completed_at=utc_now_iso(),
                    return_code=int(preflight.returncode),
                    error=preflight_summary,
                    output_summary=preflight_summary,
                )
                return

            result = run_create_sync(
                region_az=region_az,
                aws_profile=aws_profile,
                config_path=str(effective_config_path),
                pass_on_warn=pass_on_warn,
                debug=debug,
                contact_email=contact_email,
                repo_overrides=repo_overrides,
                cwd=workspace_root,
            )
            result_summary = _summarize_process_output(result)
            result_status = "COMPLETED" if result.returncode == 0 else "FAILED"
            resource_store.add_cluster_job_event(
                job_euid=job_euid,
                event_type="create",
                status=result_status,
                summary=result_summary,
                details={
                    "return_code": int(result.returncode),
                    "stdout": (result.stdout or "")[-4000:],
                    "stderr": (result.stderr or "")[-4000:],
                },
                created_by=sponsor_user_id,
            )

            cluster_payload: dict[str, Any] = {}
            if result.returncode == 0:
                try:
                    cluster_service.clear_cache()
                    cluster_info = cluster_service.describe_cluster(cluster_name, region)
                    cluster_payload = cluster_info.to_dict(include_sensitive=True)
                except Exception:
                    LOGGER.exception("Failed to refresh cluster state for %s", cluster_name)

            resource_store.update_cluster_job_status(
                job_euid=job_euid,
                state=result_status,
                created_by=sponsor_user_id,
                started_at=started_at,
                completed_at=utc_now_iso(),
                return_code=int(result.returncode),
                error=None if result.returncode == 0 else result_summary,
                output_summary=result_summary,
                cluster=cluster_payload,
            )
    except Exception as exc:
        LOGGER.exception("Cluster create job %s failed", job_euid)
        error_message = f"{type(exc).__name__}: {exc}"
        try:
            resource_store.add_cluster_job_event(
                job_euid=job_euid,
                event_type="runner",
                status="FAILED",
                summary=error_message,
                details={},
                created_by=sponsor_user_id,
            )
            resource_store.update_cluster_job_status(
                job_euid=job_euid,
                state="FAILED",
                created_by=sponsor_user_id,
                started_at=started_at,
                completed_at=utc_now_iso(),
                return_code=1,
                error=error_message,
                output_summary=error_message,
            )
        except Exception:
            LOGGER.exception("Failed to persist terminal cluster job state for %s", job_euid)


class ClusterJobManager:
    """TapDB-backed cluster job launcher that delegates execution to a worker process."""

    def __init__(
        self,
        *,
        resource_store: ResourceStore,
        cluster_service: ClusterService,
        workspace_root: Path | None = None,
        worker_module: str = "daylib_ursa.cluster_job_worker",
        python_executable: str | None = None,
    ) -> None:
        self.resource_store = resource_store
        self.cluster_service = cluster_service
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.worker_module = worker_module
        self.python_executable = python_executable or sys.executable

    def _worker_command(self, *, job_euid: str) -> list[str]:
        return [
            self.python_executable,
            "-m",
            self.worker_module,
            "--job-euid",
            job_euid,
            "--workspace-root",
            str(self.workspace_root),
        ]

    def _spawn_worker(self, *, job_euid: str) -> subprocess.Popen[str]:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        return subprocess.Popen(
            self._worker_command(job_euid=job_euid),
            cwd=str(self.workspace_root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
        )

    def start_job(self, *, job_euid: str, actor_user_id: str) -> ClusterJobRecord:
        job = self.resource_store.get_cluster_job(job_euid)
        if job is None:
            raise KeyError(f"cluster job not found: {job_euid}")
        if job.state not in {"QUEUED", "DEFINED"}:
            raise ValueError(f"cluster job is not startable from state {job.state}")
        try:
            worker = self._spawn_worker(job_euid=job.job_euid)
        except Exception as exc:
            error_message = f"Failed to launch cluster worker: {type(exc).__name__}: {exc}"
            self.resource_store.add_cluster_job_event(
                job_euid=job.job_euid,
                event_type="worker-launch",
                status="FAILED",
                summary=error_message,
                details={"command": self._worker_command(job_euid=job.job_euid)},
                created_by=actor_user_id,
            )
            return self.resource_store.update_cluster_job_status(
                job_euid=job.job_euid,
                state="FAILED",
                created_by=actor_user_id,
                completed_at=utc_now_iso(),
                return_code=1,
                error=error_message,
                output_summary=error_message,
            )
        self.resource_store.add_cluster_job_event(
            job_euid=job.job_euid,
            event_type="worker-launch",
            status="QUEUED",
            summary=f"Spawned cluster worker pid {worker.pid}",
            details={
                "pid": int(worker.pid or 0),
                "command": self._worker_command(job_euid=job.job_euid),
            },
            created_by=actor_user_id,
        )
        return self.resource_store.get_cluster_job(job.job_euid) or job

    @staticmethod
    def _request_payload(
        *,
        cluster_name: str,
        region: str,
        region_az: str,
        ssh_key_name: str,
        reference_s3_uri: str,
        control_data_s3_uri: str,
        stage_s3_uri: str,
        export_destination_s3_uri: str,
        aws_profile: str | None,
        contact_email: str | None,
        pass_on_warn: bool,
        debug: bool,
        config_path: str | None,
        cluster_config_values: dict[str, Any] | None,
        repo_overrides: list[str] | None,
        dry_run: bool,
    ) -> dict[str, Any]:
        return {
            "cluster_name": cluster_name,
            "region": region,
            "region_az": region_az,
            "ssh_key_name": ssh_key_name,
            "reference_s3_uri": reference_s3_uri,
            "control_data_s3_uri": control_data_s3_uri,
            "stage_s3_uri": stage_s3_uri,
            "export_destination_s3_uri": export_destination_s3_uri,
            "aws_profile": aws_profile,
            "contact_email": contact_email,
            "pass_on_warn": bool(pass_on_warn),
            "debug": bool(debug),
            "config_path": str(config_path or "").strip() or None,
            "cluster_config_values": dict(cluster_config_values or {}),
            "repo_overrides": list(repo_overrides or []),
            "dry_run": bool(dry_run),
        }

    def record_create_dry_run(
        self,
        *,
        cluster_name: str,
        region_az: str,
        ssh_key_name: str,
        reference_s3_uri: str,
        control_data_s3_uri: str,
        stage_s3_uri: str,
        export_destination_s3_uri: str,
        tenant_id: uuid.UUID,
        owner_user_id: str,
        sponsor_user_id: str,
        aws_profile: str | None,
        contact_email: str | None,
        pass_on_warn: bool,
        debug: bool,
        dry_run_result: dict[str, Any],
        config_path: str | None = None,
        cluster_config_values: dict[str, Any] | None = None,
        repo_overrides: list[str] | None = None,
    ) -> ClusterJobRecord:
        region = region_from_region_az(region_az)
        request_payload = self._request_payload(
            cluster_name=cluster_name,
            region=region,
            region_az=region_az,
            ssh_key_name=ssh_key_name,
            reference_s3_uri=reference_s3_uri,
            control_data_s3_uri=control_data_s3_uri,
            stage_s3_uri=stage_s3_uri,
            export_destination_s3_uri=export_destination_s3_uri,
            aws_profile=aws_profile,
            contact_email=contact_email,
            pass_on_warn=pass_on_warn,
            debug=debug,
            config_path=config_path,
            cluster_config_values=cluster_config_values,
            repo_overrides=repo_overrides,
            dry_run=True,
        )
        job = self.resource_store.create_cluster_job(
            cluster_name=cluster_name,
            region=region,
            region_az=region_az,
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            sponsor_user_id=sponsor_user_id,
            request=request_payload,
        )
        return_code = int(dry_run_result.get("return_code") or 0)
        summary = str(dry_run_result.get("summary") or "Cluster create dry-run completed")
        self.resource_store.add_cluster_job_event(
            job_euid=job.job_euid,
            event_type="create-dry-run",
            status="COMPLETED" if return_code == 0 else "FAILED",
            summary=summary,
            details={
                "return_code": return_code,
                "stdout": str(dry_run_result.get("stdout") or "")[-4000:],
                "stderr": str(dry_run_result.get("stderr") or "")[-4000:],
            },
            created_by=sponsor_user_id,
        )
        now = utc_now_iso()
        return self.resource_store.update_cluster_job_status(
            job_euid=job.job_euid,
            state="COMPLETED" if return_code == 0 else "FAILED",
            created_by=sponsor_user_id,
            started_at=now,
            completed_at=now,
            return_code=return_code,
            error=None if return_code == 0 else summary,
            output_summary=summary,
            cluster={"dry_run": True},
        )

    def start_create_job(
        self,
        *,
        cluster_name: str,
        region_az: str,
        ssh_key_name: str,
        reference_s3_uri: str,
        control_data_s3_uri: str,
        stage_s3_uri: str,
        export_destination_s3_uri: str,
        tenant_id: uuid.UUID,
        owner_user_id: str,
        sponsor_user_id: str,
        aws_profile: str | None,
        contact_email: str | None,
        pass_on_warn: bool,
        debug: bool,
        config_path: str | None = None,
        cluster_config_values: dict[str, Any] | None = None,
        repo_overrides: list[str] | None = None,
    ) -> ClusterJobRecord:
        region = region_from_region_az(region_az)
        request_payload = self._request_payload(
            cluster_name=cluster_name,
            region=region,
            region_az=region_az,
            ssh_key_name=ssh_key_name,
            reference_s3_uri=reference_s3_uri,
            control_data_s3_uri=control_data_s3_uri,
            stage_s3_uri=stage_s3_uri,
            export_destination_s3_uri=export_destination_s3_uri,
            aws_profile=aws_profile,
            contact_email=contact_email,
            pass_on_warn=pass_on_warn,
            debug=debug,
            config_path=config_path,
            cluster_config_values=cluster_config_values,
            repo_overrides=repo_overrides,
            dry_run=False,
        )
        job = self.resource_store.create_cluster_job(
            cluster_name=cluster_name,
            region=region,
            region_az=region_az,
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            sponsor_user_id=sponsor_user_id,
            request=request_payload,
        )
        self.resource_store.add_cluster_job_event(
            job_euid=job.job_euid,
            event_type="queued",
            status="QUEUED",
            summary=f"Queued cluster creation for {cluster_name} in {region_az}",
            details=request_payload,
            created_by=sponsor_user_id,
        )

        try:
            worker = self._spawn_worker(job_euid=job.job_euid)
        except Exception as exc:
            error_message = f"Failed to launch cluster worker: {type(exc).__name__}: {exc}"
            self.resource_store.add_cluster_job_event(
                job_euid=job.job_euid,
                event_type="worker-launch",
                status="FAILED",
                summary=error_message,
                details={"command": self._worker_command(job_euid=job.job_euid)},
                created_by=sponsor_user_id,
            )
            return self.resource_store.update_cluster_job_status(
                job_euid=job.job_euid,
                state="FAILED",
                created_by=sponsor_user_id,
                completed_at=utc_now_iso(),
                return_code=1,
                error=error_message,
                output_summary=error_message,
            )

        self.resource_store.add_cluster_job_event(
            job_euid=job.job_euid,
            event_type="worker-launch",
            status="QUEUED",
            summary=f"Spawned cluster worker pid {worker.pid}",
            details={
                "pid": int(worker.pid or 0),
                "command": self._worker_command(job_euid=job.job_euid),
            },
            created_by=sponsor_user_id,
        )
        return self.resource_store.get_cluster_job(job.job_euid) or job


__all__ = [
    "ClusterJobManager",
    "region_from_region_az",
    "run_cluster_create_job",
    "run_dayoa_dyr_help_job",
]
