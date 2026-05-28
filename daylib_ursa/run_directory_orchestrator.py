from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import urlparse

from daylib_ursa.analysis_jobs import AnalysisJobManager
from daylib_ursa.ephemeral_cluster.runner import DaylilyEcClient, _summarize_process_output
from daylib_ursa.resource_store import AnalysisJobRecord, ResourceStore
from daylib_ursa.tapdb_graph import utc_now_iso


_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class RunDirectoryPolicy:
    tenant_id: str
    owner_user_id: str
    regions: tuple[str, ...]
    reference_s3_uri: str
    stage_target: str
    destination_s3_uri: str
    project: str | None
    aws_profile: str
    dewey_url: str
    dewey_token_env: str
    cluster_create_name: str
    cluster_create_region_az: str
    cluster_create_config_path: str
    cluster_create_timeout_seconds: int
    cluster_create_poll_interval_seconds: int


@dataclass(frozen=True)
class SelectedCluster:
    name: str
    region: str


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _normalize_s3_prefix_uri(value: str) -> str:
    parsed = urlparse(_clean(value))
    if parsed.scheme != "s3" or not parsed.netloc:
        raise ValueError("S3 URI must be an absolute s3:// URI")
    if parsed.query or parsed.fragment:
        raise ValueError("S3 URI must not include query strings or fragments")
    prefix = parsed.path.strip("/")
    return f"s3://{parsed.netloc}/{prefix}/" if prefix else f"s3://{parsed.netloc}/"


def _sidecar_uri(*, run_storage_uri: str, run_folder_name: str, analysis_id: str, state: str) -> str:
    run_root = _normalize_s3_prefix_uri(run_storage_uri)
    filename = f"{run_folder_name}.ursa.{analysis_id}.{state}"
    return run_root + filename


def _retry_safe_session_name(*, analysis_id: str, command_id: str) -> str:
    raw = f"ursa-{analysis_id}-{command_id}"
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", raw).strip("-")
    if not cleaned:
        raise ValueError("Could not derive a path-safe workflow session name")
    return cleaned[:80]


def _destination_for_run(
    *,
    destination_root: str,
    run_storage_uri: str,
    cluster_name: str,
    analysis_id: str,
) -> str:
    if not _SAFE_ID_RE.fullmatch(str(cluster_name or "")):
        raise ValueError("Selected cluster name is not path-safe for DAY-EC export identity")
    if not _SAFE_ID_RE.fullmatch(str(analysis_id or "")):
        raise ValueError("Analysis EUID is not path-safe for DAY-EC export identity")
    destination = urlparse(_normalize_s3_prefix_uri(destination_root))
    source = urlparse(_normalize_s3_prefix_uri(run_storage_uri))
    if destination.netloc != source.netloc:
        raise ValueError("destination_s3_uri bucket must match run_storage_uri bucket")
    destination_parts = [part for part in destination.path.strip("/").split("/") if part]
    if destination_parts != ["derived"]:
        raise ValueError("destination_s3_uri must be the explicit s3://<sequencing-bucket>/derived/ root")
    source_parts = [part for part in source.path.strip("/").split("/") if part]
    if len(source_parts) < 2:
        raise ValueError("run_storage_uri must include a collection prefix and run-relative path")
    return (
        f"s3://{destination.netloc}/"
        + "/".join(["derived", *source_parts[1:], "analysis_results", cluster_name, analysis_id])
        + "/"
    )


def _dayoa_root_for_destination(destination: str) -> str:
    return _normalize_s3_prefix_uri(destination) + "daylily-omics-analysis/"


def _write_sidecar_cli(
    *,
    uri: str,
    payload: dict[str, Any],
    profile: str,
    region: str,
    workspace_root: Path,
) -> None:
    env = os.environ.copy()
    if profile:
        env["AWS_PROFILE"] = profile
    if region:
        env["AWS_REGION"] = region
        env["AWS_DEFAULT_REGION"] = region
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        prefix="ursa-sidecar-",
        suffix=".json",
        dir=str(workspace_root),
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")
    try:
        result = subprocess.run(
            ["aws", "s3", "cp", str(temp_path), uri, "--only-show-errors"],
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )
    finally:
        temp_path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(_summarize_process_output(result))


def _policy_from_settings(settings: Any) -> RunDirectoryPolicy:
    required = {
        "tenant_id": "ursa_run_directory_analysis_tenant_id",
        "owner_user_id": "ursa_run_directory_analysis_owner_user_id",
        "region": "ursa_run_directory_analysis_region",
        "reference_s3_uri": "ursa_run_directory_analysis_reference_s3_uri",
        "stage_target": "ursa_run_directory_analysis_stage_target",
        "destination_s3_uri": "ursa_run_directory_analysis_destination_s3_uri",
        "aws_profile": "ursa_run_directory_analysis_aws_profile",
    }
    values = {key: _clean(getattr(settings, attr, "")) for key, attr in required.items()}
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise ValueError("Ursa run-directory analysis policy is incomplete: " + ", ".join(sorted(missing)))
    dewey_url = _clean(getattr(settings, "dewey_base_url", ""))
    dewey_token_env = _clean(getattr(settings, "ursa_run_directory_analysis_dewey_token_env", ""))
    missing_dewey = [
        name
        for name, value in {
            "dewey_url": dewey_url,
            "dewey_token_env": dewey_token_env,
        }.items()
        if not value
    ]
    if missing_dewey:
        raise ValueError(
            "Ursa run-directory analysis Dewey export-link policy is incomplete: "
            + ", ".join(missing_dewey)
        )
    return RunDirectoryPolicy(
        tenant_id=values["tenant_id"],
        owner_user_id=values["owner_user_id"],
        regions=tuple(part.strip() for part in values["region"].split(",") if part.strip()),
        reference_s3_uri=_normalize_s3_prefix_uri(values["reference_s3_uri"]),
        stage_target=values["stage_target"],
        destination_s3_uri=_normalize_s3_prefix_uri(values["destination_s3_uri"]),
        project=_clean(getattr(settings, "ursa_run_directory_analysis_project", "")) or None,
        aws_profile=values["aws_profile"],
        dewey_url=dewey_url,
        dewey_token_env=dewey_token_env,
        cluster_create_name=_clean(
            getattr(settings, "ursa_run_directory_analysis_cluster_create_name", "")
        ),
        cluster_create_region_az=_clean(
            getattr(settings, "ursa_run_directory_analysis_cluster_create_region_az", "")
        ),
        cluster_create_config_path=_clean(
            getattr(settings, "ursa_run_directory_analysis_cluster_create_config_path", "")
        ),
        cluster_create_timeout_seconds=int(
            getattr(settings, "ursa_run_directory_analysis_cluster_create_timeout_seconds", 3600)
            or 3600
        ),
        cluster_create_poll_interval_seconds=int(
            getattr(settings, "ursa_run_directory_analysis_cluster_create_poll_interval_seconds", 30)
            or 30
        ),
    )


def _cluster_is_suitable(row: dict[str, Any]) -> bool:
    if _clean(row.get("status")).upper() != "CREATE_COMPLETE":
        return False
    details = row.get("details")
    if isinstance(details, dict):
        fleet = _clean(details.get("computeFleetStatus")).upper()
        if fleet and fleet != "RUNNING":
            return False
    configured = row.get("headnode_configured")
    if configured is False:
        return False
    return bool(_clean(row.get("name")) and _clean(row.get("region")))


class RunDirectoryOrchestrator:
    def __init__(
        self,
        *,
        resource_store: ResourceStore,
        client: DaylilyEcClient,
        settings: Any,
        workspace_root: Path | None = None,
        python_executable: str | None = None,
        worker_module: str = "daylib_ursa.run_directory_worker",
    ) -> None:
        self.resource_store = resource_store
        self.client = client
        self.settings = settings
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.python_executable = python_executable or sys.executable
        self.worker_module = worker_module

    def _worker_command(self, *, trigger_euid: str) -> list[str]:
        return [
            self.python_executable,
            "-m",
            self.worker_module,
            "--trigger-euid",
            trigger_euid,
            "--workspace-root",
            str(self.workspace_root),
        ]

    def start_trigger(self, trigger_euid: str) -> dict[str, Any]:
        command = self._worker_command(trigger_euid=trigger_euid)
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"
        worker = subprocess.Popen(
            command,
            cwd=str(self.workspace_root),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
        )
        return {"pid": int(worker.pid or 0), "command": command}

    def select_cluster(self, policy: RunDirectoryPolicy) -> SelectedCluster | None:
        for region in policy.regions:
            payload = self.client.cluster_list(region=region, details=True)
            for row in list(payload.get("clusters") or []):
                if isinstance(row, dict) and _cluster_is_suitable(row):
                    return SelectedCluster(name=_clean(row["name"]), region=_clean(row["region"]))
        return None

    def create_and_wait_cluster(self, policy: RunDirectoryPolicy) -> SelectedCluster:
        missing = [
            name
            for name, value in {
                "cluster_create_name": policy.cluster_create_name,
                "cluster_create_region_az": policy.cluster_create_region_az,
                "cluster_create_config_path": policy.cluster_create_config_path,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(
                "No suitable cluster exists and cluster creation policy is incomplete: "
                + ", ".join(missing)
            )
        preflight = self.client.run(
            [
                "preflight",
                "--region-az",
                policy.cluster_create_region_az,
                "--config",
                policy.cluster_create_config_path,
                "--non-interactive",
                "--profile",
                policy.aws_profile,
            ],
            cwd=self.workspace_root,
        )
        if preflight.returncode != 0:
            raise RuntimeError(_summarize_process_output(preflight))
        create = self.client.run(
            [
                "create",
                "--region-az",
                policy.cluster_create_region_az,
                "--config",
                policy.cluster_create_config_path,
                "--non-interactive",
                "--profile",
                policy.aws_profile,
            ],
            cwd=self.workspace_root,
        )
        if create.returncode != 0:
            raise RuntimeError(_summarize_process_output(create))
        region = policy.cluster_create_region_az[:-1]
        self.client.cluster_wait(
            cluster_name=policy.cluster_create_name,
            region=region,
            timeout=policy.cluster_create_timeout_seconds,
            poll_interval=policy.cluster_create_poll_interval_seconds,
        )
        return SelectedCluster(name=policy.cluster_create_name, region=region)

    def ensure_run_mount(
        self,
        *,
        source_s3_uri: str,
        selected: SelectedCluster,
        mount_id: str,
        run_id: str,
        platform: str,
    ) -> dict[str, Any]:
        try:
            existing = self.client.mounts_describe(
                cluster_name=selected.name,
                region=selected.region,
                mount_id=mount_id,
            )
        except RuntimeError as exc:
            if "Run mount not found" not in str(exc):
                raise
        else:
            expected_source = _normalize_s3_prefix_uri(source_s3_uri)
            observed_source = _normalize_s3_prefix_uri(
                _clean(existing.get("source_s3_uri") or existing.get("data_repository_path"))
            )
            if (
                _clean(existing.get("cluster_name")) == selected.name
                and _clean(existing.get("region")) == selected.region
                and _clean(existing.get("mount_id")) == mount_id
                and _clean(existing.get("lifecycle")).upper() == "AVAILABLE"
                and observed_source == expected_source
            ):
                return existing
            raise RuntimeError(
                "Existing run-directory mount does not match requested run input: "
                f"mount_id={mount_id}"
            )
        return self.client.mounts_create(
            source_s3_uri=source_s3_uri,
            cluster_name=selected.name,
            region=selected.region,
            mount_id=mount_id,
            run_id=run_id,
            platform=platform,
        )

    def run_trigger(self, trigger_euid: str, *, poll_interval_seconds: int = 60) -> None:
        policy = _policy_from_settings(self.settings)
        trigger = self.resource_store.get_dewey_run_trigger(trigger_euid)
        if trigger is None:
            raise RuntimeError(f"Dewey run-directory trigger not found: {trigger_euid}")
        request = dict(trigger.request or {})
        run_storage_uri = _normalize_s3_prefix_uri(_clean(request.get("run_storage_uri")))
        run_folder_name = _clean(request.get("run_folder_name"))
        platform = _clean(request.get("platform")) or "OTHER"
        response = dict(trigger.response or {})
        job_ids = [
            _clean(item)
            for item in list(response.get("analysis_job_euids") or [])
            if _clean(item)
        ]
        if not job_ids and trigger.analysis_job_euid:
            job_ids = [trigger.analysis_job_euid]
        if not job_ids:
            raise RuntimeError(f"Trigger {trigger_euid} has no analysis jobs")
        first_job = self.resource_store.get_analysis_job(job_ids[0])
        if first_job is None:
            raise RuntimeError(f"Analysis job not found: {job_ids[0]}")
        analysis_id = first_job.job_euid
        inprog_uri = _sidecar_uri(
            run_storage_uri=run_storage_uri,
            run_folder_name=run_folder_name,
            analysis_id=analysis_id,
            state="inprog",
        )
        _write_sidecar_cli(
            uri=inprog_uri,
            payload={
                "schema_version": "ursa.run_directory_sidecar.v1",
                "state": "inprog",
                "trigger_euid": trigger_euid,
                "analysis_id": analysis_id,
                "written_at": utc_now_iso(),
            },
            profile=policy.aws_profile,
            region=first_job.region or policy.regions[0],
            workspace_root=self.workspace_root,
        )
        selected = self.select_cluster(policy) or self.create_and_wait_cluster(policy)
        mount_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", run_folder_name).strip("-")[:80]
        if not mount_id:
            raise RuntimeError("run_folder_name did not produce a safe mount id")
        self.ensure_run_mount(
            source_s3_uri=run_storage_uri,
            selected=selected,
            mount_id=mount_id,
            run_id=run_folder_name,
            platform=platform,
        )
        self.client.mounts_verify(
            cluster_name=selected.name,
            region=selected.region,
            mount_id=mount_id,
            platform=platform,
        )
        manager = AnalysisJobManager(
            resource_store=self.resource_store,
            client=self.client,
            workspace_root=self.workspace_root,
        )
        terminal_jobs: list[AnalysisJobRecord] = []
        mount_deleted = False
        failure_seen = False
        try:
            for job_id in job_ids:
                job = self.resource_store.get_analysis_job(job_id)
                if job is None:
                    raise RuntimeError(f"Analysis job not found: {job_id}")
                destination = _destination_for_run(
                    destination_root=policy.destination_s3_uri,
                    run_storage_uri=run_storage_uri,
                    cluster_name=selected.name,
                    analysis_id=job.job_euid,
                )
                request_payload = {
                    **dict(job.request or {}),
                    "analysis_id": job.job_euid,
                    "executing_entity": selected.name,
                    "destination": destination,
                    "session_name": _retry_safe_session_name(
                        analysis_id=job.job_euid,
                        command_id=str(job.request.get("analysis_command_id") or job.job_name),
                    ),
                    "delete_on_export_success": True,
                    "artifact_registration_command_id": job.request.get("analysis_command_id"),
                    "dewey_url": policy.dewey_url,
                    "dewey_token_env": policy.dewey_token_env,
                    "dewey_analysis_dir_external_object_id": _dayoa_root_for_destination(
                        destination
                    ),
                    "dewey_run_artifact_euid": request.get("dewey_run_artifact_euid"),
                    "dewey_ursa_analysis_euid": job.job_euid,
                    "run_directory_mount_id": mount_id,
                }
                job = self.resource_store.update_analysis_job_assignment(
                    job_euid=job.job_euid,
                    cluster_name=selected.name,
                    region=selected.region,
                    created_by=policy.owner_user_id,
                )
                job = self.resource_store.update_analysis_job_request(
                    job_euid=job.job_euid,
                    request=request_payload,
                    created_by=policy.owner_user_id,
                )
                if job.state == "DEFINED":
                    job = manager.launch_job(job.job_euid, actor_user_id=policy.owner_user_id)
                while job.state in {"PREPARING", "STAGING", "LAUNCHING", "RUNNING"}:
                    time.sleep(max(1, poll_interval_seconds))
                    job = manager.refresh_job(job.job_euid, actor_user_id=policy.owner_user_id)
                terminal_jobs.append(job)
                if job.state != "COMPLETED":
                    raise RuntimeError(job.error or f"Analysis job {job.job_euid} ended {job.state}")
            self.client.mounts_delete(
                cluster_name=selected.name,
                region=selected.region,
                mount_id=mount_id,
            )
            mount_deleted = True
            complete_uri = _sidecar_uri(
                run_storage_uri=run_storage_uri,
                run_folder_name=run_folder_name,
                analysis_id=analysis_id,
                state="complete",
            )
            _write_sidecar_cli(
                uri=complete_uri,
                payload={
                    "schema_version": "ursa.run_directory_sidecar.v1",
                    "state": "complete",
                    "trigger_euid": trigger_euid,
                    "analysis_id": analysis_id,
                    "cluster_name": selected.name,
                    "region": selected.region,
                    "jobs": [
                        {
                            "analysis_job_euid": item.job_euid,
                            "state": item.state,
                            "destination": item.request.get("destination"),
                        }
                        for item in terminal_jobs
                    ],
                    "written_at": utc_now_iso(),
                },
                profile=policy.aws_profile,
                region=selected.region,
                workspace_root=self.workspace_root,
            )
            response["analysis_jobs"] = [
                {
                    "analysis_job_euid": item.job_euid,
                    "command_id": item.request.get("analysis_command_id"),
                    "status": item.state,
                    "pipeline_order": item.request.get("run_directory_trigger", {}).get(
                        "pipeline_order"
                    ),
                }
                for item in terminal_jobs
            ]
            self.resource_store.update_dewey_run_trigger(
                trigger_euid=trigger_euid,
                status="COMPLETED",
                response={**response, "status": "COMPLETED", "updated_at": utc_now_iso()},
                analysis_job_euid=analysis_id,
                staging_job_euid=trigger.staging_job_euid,
                error=None,
            )
        except Exception as exc:
            failure_seen = True
            fail_uri = _sidecar_uri(
                run_storage_uri=run_storage_uri,
                run_folder_name=run_folder_name,
                analysis_id=analysis_id,
                state="fail",
            )
            _write_sidecar_cli(
                uri=fail_uri,
                payload={
                    "schema_version": "ursa.run_directory_sidecar.v1",
                    "state": "fail",
                    "trigger_euid": trigger_euid,
                    "analysis_id": analysis_id,
                    "error": f"{type(exc).__name__}: {exc}",
                    "written_at": utc_now_iso(),
                },
                profile=policy.aws_profile,
                region=selected.region if "selected" in locals() else policy.regions[0],
                workspace_root=self.workspace_root,
            )
            self.resource_store.update_dewey_run_trigger(
                trigger_euid=trigger_euid,
                status="FAILED",
                response={**response, "status": "FAILED", "updated_at": utc_now_iso()},
                analysis_job_euid=analysis_id,
                staging_job_euid=trigger.staging_job_euid,
                error=f"{type(exc).__name__}: {exc}",
            )
            raise
        finally:
            if "selected" in locals() and "mount_id" in locals() and not mount_deleted:
                try:
                    self.client.mounts_delete(
                        cluster_name=selected.name,
                        region=selected.region,
                        mount_id=mount_id,
                    )
                except Exception:
                    if not failure_seen:
                        raise


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run one Ursa run-directory trigger worker")
    parser.add_argument("--trigger-euid", required=True)
    parser.add_argument("--workspace-root", default=str(Path.cwd()))
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    from daylib_ursa.config import get_settings

    settings = get_settings()
    resource_store = ResourceStore()
    client = DaylilyEcClient(
        aws_profile=_clean(getattr(settings, "ursa_run_directory_analysis_aws_profile", ""))
        or _clean(getattr(settings, "aws_profile", ""))
        or None
    )
    orchestrator = RunDirectoryOrchestrator(
        resource_store=resource_store,
        client=client,
        settings=settings,
        workspace_root=Path(args.workspace_root).resolve(),
    )
    orchestrator.run_trigger(args.trigger_euid)
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
