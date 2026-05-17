from __future__ import annotations

import csv
import io
import re
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from daylib_ursa.analysis_commands import get_analysis_command
from daylib_ursa.ephemeral_cluster.runner import DaylilyEcClient, _summarize_process_output
from daylib_ursa.resource_store import ResourceStore, RunAnalysisJobRecord
from daylib_ursa.tapdb_graph import utc_now_iso


_MARKER_RE = re.compile(r"^__(?P<name>DAYLILY_[A-Z_]+)__=(?P<value>.*)$", re.MULTILINE)
_SNAKEMAKE_COMPLETE_RE = re.compile(r"\b(?P<done>\d+) of (?P<total>\d+) steps \(100%\) done\b")
RUNS_TSV_COLUMNS = [
    "RUNID",
    "PLATFORM",
    "RUN_DIR",
    "SOURCE_S3_URI",
    "MOUNT_ID",
    "SAMPLE_SHEET",
    "BASECALLING_STATE",
    "RUN_STATUS",
    "OUTPUT_ROOT",
    "REGION",
    "PROFILE",
]


def _safe_session_name(job_euid: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(job_euid or "").strip()).strip("-")
    if not cleaned:
        raise ValueError("job_euid is required")
    return f"ursa-run-{cleaned}"[:80]


def _parse_launch_markers(stdout: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for match in _MARKER_RE.finditer(stdout or ""):
        values[match.group("name")] = match.group("value").strip()
    session_name = values.get("DAYLILY_SESSION")
    run_dir = values.get("DAYLILY_RUN_DIR")
    repo_path = values.get("DAYLILY_REPO_PATH")
    if not session_name or not run_dir or not repo_path:
        raise RuntimeError("daylily-ec workflow launch did not report launch markers")
    return {
        "session_name": session_name,
        "run_dir": run_dir,
        "repo_path": repo_path,
    }


def _snakemake_log_reports_success(text: str) -> bool:
    if not text:
        return False
    for match in _SNAKEMAKE_COMPLETE_RE.finditer(text):
        if match.group("done") == match.group("total"):
            return True
    if re.search(r"\b(error|failed|traceback)\b", text, re.IGNORECASE):
        return False
    return False


def _runs_tsv_content(job: RunAnalysisJobRecord, *, aws_profile: str | None) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=RUNS_TSV_COLUMNS, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    writer.writerow(
        {
            "RUNID": job.run_id,
            "PLATFORM": job.platform,
            "RUN_DIR": job.run_dir,
            "SOURCE_S3_URI": job.source_s3_uri,
            "MOUNT_ID": job.mount_id,
            "SAMPLE_SHEET": job.sample_sheet or "",
            "BASECALLING_STATE": job.basecalling_state,
            "RUN_STATUS": job.run_status,
            "OUTPUT_ROOT": job.output_root,
            "REGION": job.region,
            "PROFILE": aws_profile or "",
        }
    )
    return buffer.getvalue()


def _require_run_analysis_command(command: Any, command_id: str) -> Any:
    if getattr(command, "command_class", "") != "run_analysis":
        raise ValueError(f"{command_id} is not a run_analysis command")
    if getattr(command, "input_contract", "") != "run_context":
        raise ValueError(f"{command_id} does not use the run_context input contract")
    if not bool(getattr(command, "requires_run_mount", False)):
        raise ValueError(f"{command_id} does not require a run mount")
    return command


class RunAnalysisJobManager:
    """Launch manager for run-directory analysis jobs through daylily-ec 3.0.0."""

    def __init__(
        self,
        *,
        resource_store: ResourceStore,
        client: DaylilyEcClient,
        workspace_root: Path | None = None,
    ) -> None:
        self.resource_store = resource_store
        self.client = client
        self.workspace_root = (workspace_root or Path.cwd()).resolve()

    def _launch_workflow(
        self,
        *,
        job: RunAnalysisJobRecord,
        request: dict[str, Any],
        run_context_file: Path,
        aws_profile: str | None,
    ) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
        command_id = str(
            request.get("analysis_command_id") or request.get("command_id") or ""
        ).strip()
        optional_features = [
            str(item or "").strip()
            for item in list(request.get("optional_features") or [])
            if str(item or "").strip()
        ]
        command = _require_run_analysis_command(
            get_analysis_command(command_id, optional_features=optional_features),
            command_id,
        )
        session_name = str(request.get("session_name") or "").strip() or _safe_session_name(
            job.job_euid
        )
        argv = command.launch_argv(
            destination=str(request.get("destination") or "").strip() or None,
            profile=aws_profile,
            region=job.region,
            cluster=job.cluster_name,
            run_context_file=str(run_context_file),
            session_name=session_name,
            project=str(request.get("project") or "").strip() or None,
            dry_run=bool(request.get("dry_run")),
        )
        result = self.client.workflow_launch(argv, cwd=self.workspace_root)
        if result.returncode != 0:
            raise RuntimeError(_summarize_process_output(result))
        markers = _parse_launch_markers(result.stdout or "")
        launch = {
            "command_id": command.command_id,
            "optional_features": optional_features,
            "argv": list(argv),
            "run_context_file": str(run_context_file),
            "run_id": job.run_id,
            "mount_euid": job.mount_euid,
            "mount_id": job.mount_id,
            "stdout": (result.stdout or "")[-8000:],
            "stderr": (result.stderr or "")[-8000:],
            **markers,
        }
        return result, launch

    def launch_job(self, job_euid: str, *, actor_user_id: str) -> RunAnalysisJobRecord:
        job = self.resource_store.get_run_analysis_job(job_euid)
        if job is None:
            raise KeyError(f"run analysis job not found: {job_euid}")
        request = dict(job.request or {})
        aws_profile = (
            str(request.get("aws_profile") or self.client.aws_profile or "").strip() or None
        )
        started_at = utc_now_iso()
        try:
            self.resource_store.update_run_analysis_job_status(
                job_euid=job_euid,
                state="LAUNCHING",
                created_by=actor_user_id,
                started_at=started_at,
            )
            self.resource_store.add_run_analysis_job_event(
                job_euid=job_euid,
                event_type="launch",
                status="RUNNING",
                summary="Preparing run analysis context",
                details={"run_id": job.run_id, "mount_euid": job.mount_euid},
                created_by=actor_user_id,
            )
            with TemporaryDirectory(prefix="ursa-run-analysis-") as temp_dir_name:
                run_context_path = Path(temp_dir_name) / "runs.tsv"
                run_context_path.write_text(
                    _runs_tsv_content(job, aws_profile=aws_profile),
                    encoding="utf-8",
                    newline="\n",
                )
                launch_result, launch = self._launch_workflow(
                    job=job,
                    request=request,
                    run_context_file=run_context_path,
                    aws_profile=aws_profile,
                )
            self.resource_store.add_run_analysis_job_event(
                job_euid=job_euid,
                event_type="launch",
                status="RUNNING",
                summary=f"Workflow session {launch['session_name']} launched",
                details={
                    "session_name": launch["session_name"],
                    "run_dir": launch["run_dir"],
                    "return_code": int(launch_result.returncode),
                    "mount_euid": job.mount_euid,
                },
                created_by=actor_user_id,
            )
            return self.resource_store.update_run_analysis_job_status(
                job_euid=job_euid,
                state="RUNNING",
                created_by=actor_user_id,
                started_at=started_at,
                return_code=int(launch_result.returncode),
                output_summary=f"Workflow session {launch['session_name']} launched",
                launch=launch,
            )
        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"
            self.resource_store.add_run_analysis_job_event(
                job_euid=job_euid,
                event_type="runner",
                status="FAILED",
                summary=error_message,
                details={},
                created_by=actor_user_id,
            )
            return self.resource_store.update_run_analysis_job_status(
                job_euid=job_euid,
                state="FAILED",
                created_by=actor_user_id,
                started_at=started_at,
                completed_at=utc_now_iso(),
                return_code=1,
                error=error_message,
                output_summary=error_message,
            )

    def refresh_job(self, job_euid: str, *, actor_user_id: str) -> RunAnalysisJobRecord:
        job = self.resource_store.get_run_analysis_job(job_euid)
        if job is None:
            raise KeyError(f"run analysis job not found: {job_euid}")
        session_name = str(job.launch.get("session_name") or "").strip()
        if not session_name:
            raise ValueError("Run analysis job has not been launched")
        status_payload = self.client.workflow_status(
            session_name=session_name,
            region=job.region,
            cluster_name=job.cluster_name,
        )
        launch = dict(job.launch or {})
        launch["status"] = status_payload
        exit_code = status_payload.get("exit_code")
        completed_at = str(status_payload.get("completed_at") or "").strip() or None
        completion_source = "workflow_status"
        if exit_code is None:
            logs = self.client.workflow_logs(
                session_name=session_name,
                region=job.region,
                cluster_name=job.cluster_name,
                lines=500,
            )
            log_text = "\n".join(item for item in (logs.stdout or "", logs.stderr or "") if item)
            if logs.returncode == 0 and _snakemake_log_reports_success(log_text):
                exit_code = 0
                completed_at = completed_at or utc_now_iso()
                status_payload = {
                    **status_payload,
                    "exit_code": 0,
                    "completed_at": completed_at,
                    "completion_source": "snakemake_log",
                }
                launch["status"] = status_payload
                completion_source = "snakemake_log"
        if exit_code is None:
            state = "RUNNING"
            return_code = job.return_code
            error = None
        else:
            return_code = int(exit_code) if isinstance(exit_code, int) else 1
            state = "COMPLETED" if return_code == 0 else "FAILED"
            error = None if return_code == 0 else f"Workflow exited with status {return_code}"
        record = self.resource_store.update_run_analysis_job_status(
            job_euid=job_euid,
            state=state,
            created_by=actor_user_id,
            completed_at=completed_at,
            return_code=return_code,
            error=error,
            output_summary=f"Workflow status: {state}",
            launch=launch,
        )
        self.resource_store.add_run_analysis_job_event(
            job_euid=job_euid,
            event_type="refresh",
            status=state,
            summary=f"Workflow status refreshed: {state}",
            details={**status_payload, "completion_source": completion_source},
            created_by=actor_user_id,
        )
        return record

    def logs(self, job_euid: str, *, lines: int = 200) -> dict[str, Any]:
        job = self.resource_store.get_run_analysis_job(job_euid)
        if job is None:
            raise KeyError(f"run analysis job not found: {job_euid}")
        session_name = str(job.launch.get("session_name") or "").strip()
        if not session_name:
            raise ValueError("Run analysis job has not been launched")
        result = self.client.workflow_logs(
            session_name=session_name,
            region=job.region,
            cluster_name=job.cluster_name,
            lines=lines,
        )
        if result.returncode != 0:
            raise RuntimeError(_summarize_process_output(result))
        return {
            "job_euid": job.job_euid,
            "session_name": session_name,
            "lines": lines,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
        }
