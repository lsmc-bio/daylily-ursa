from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess
import uuid

from daylib_ursa.analysis_jobs import AnalysisJobManager
from daylib_ursa.resource_store import AnalysisJobRecord


def _job(**overrides) -> AnalysisJobRecord:
    base = AnalysisJobRecord(
        job_euid="Z-RGX-JOB",
        job_name="Analysis job",
        workset_euid="Z-RGX-WKS",
        manifest_euid="Z-RGX-MNF",
        cluster_name="fk-test",
        region="us-west-2",
        tenant_id=uuid.UUID("5777799a-919b-4ab1-8ff1-d49473a55444"),
        owner_user_id="user-1",
        state="RUNNING",
        created_at="2026-05-12T00:00:00+00:00",
        updated_at="2026-05-12T00:00:00+00:00",
        started_at="2026-05-12T00:00:00+00:00",
        completed_at=None,
        return_code=None,
        error=None,
        output_summary="Workflow session full-gui-test launched",
        request={},
        launch={"session_name": "full-gui-test"},
        events=[],
    )
    return replace(base, **overrides)


class DummyStore:
    def __init__(self) -> None:
        self.record = _job()
        self.status_updates: list[dict] = []
        self.events: list[dict] = []

    def get_analysis_job(self, job_euid: str) -> AnalysisJobRecord | None:
        return self.record if job_euid == self.record.job_euid else None

    def update_analysis_job_status(self, **kwargs) -> AnalysisJobRecord:
        self.status_updates.append(kwargs)
        self.record = replace(
            self.record,
            state=kwargs["state"],
            completed_at=kwargs.get("completed_at"),
            return_code=kwargs.get("return_code"),
            error=kwargs.get("error"),
            output_summary=kwargs.get("output_summary"),
            launch=kwargs.get("launch") or self.record.launch,
        )
        return self.record

    def add_analysis_job_event(self, **kwargs):
        self.events.append(kwargs)
        return None


class DummyClient:
    aws_profile = "lsmc"

    def workflow_status(self, **_kwargs):
        return {
            "session_name": "full-gui-test",
            "repo_path": "/fsx/analysis_results/full-gui-test/daylily-omics-analysis",
            "exit_code": None,
            "completed_at": None,
        }

    def workflow_logs(self, **_kwargs):
        return subprocess.CompletedProcess(
            args=["daylily-ec", "workflow", "logs"],
            returncode=0,
            stdout="Finished job 0.\n21 of 21 steps (100%) done\n",
            stderr="",
        )


def test_refresh_job_marks_completed_when_status_lacks_exit_marker_but_logs_complete():
    store = DummyStore()
    manager = AnalysisJobManager(
        resource_store=store,
        client=DummyClient(),
        workspace_root=Path("/tmp"),
    )

    record = manager.refresh_job("Z-RGX-JOB", actor_user_id="user-1")

    assert record.state == "COMPLETED"
    assert record.return_code == 0
    assert record.completed_at
    assert record.launch["status"]["completion_source"] == "snakemake_log"
    assert store.events[-1]["details"]["completion_source"] == "snakemake_log"
