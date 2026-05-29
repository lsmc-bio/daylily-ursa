from __future__ import annotations

import subprocess
import uuid
from dataclasses import replace
from types import SimpleNamespace
from pathlib import Path

from daylib_ursa.cluster_jobs import (
    ClusterJobManager,
    run_cluster_create_job,
    run_dayoa_dyr_help_job,
)
from daylib_ursa.cluster_service import ClusterService, HeadnodeProbeResult
from daylib_ursa.resource_store import ClusterJobEventRecord, ClusterJobRecord

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class MemoryResourceStore:
    def __init__(self) -> None:
        self.jobs: dict[str, ClusterJobRecord] = {}
        self._job_seq = 0
        self._event_seq = 0

    def create_cluster_job(
        self,
        *,
        cluster_name: str,
        region: str,
        region_az: str,
        tenant_id: uuid.UUID,
        owner_user_id: str,
        sponsor_user_id: str,
        request: dict | None = None,
    ) -> ClusterJobRecord:
        self._job_seq += 1
        record = ClusterJobRecord(
            job_euid=f"CJ-{self._job_seq}",
            job_name=cluster_name,
            cluster_name=cluster_name,
            region=region,
            region_az=region_az,
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            sponsor_user_id=sponsor_user_id,
            state="QUEUED",
            created_at="2026-03-25T00:00:00Z",
            updated_at="2026-03-25T00:00:00Z",
            started_at=None,
            completed_at=None,
            return_code=None,
            error=None,
            output_summary=None,
            request=dict(request or {}),
            cluster={},
            events=[],
        )
        self.jobs[record.job_euid] = record
        return record

    def add_cluster_job_event(
        self,
        *,
        job_euid: str,
        event_type: str,
        status: str,
        summary: str,
        details: dict | None = None,
        created_by: str | None = None,
    ) -> ClusterJobEventRecord:
        self._event_seq += 1
        job = self.jobs[job_euid]
        event = ClusterJobEventRecord(
            event_euid=f"CE-{self._event_seq}",
            job_euid=job_euid,
            event_type=event_type,
            status=status,
            summary=summary,
            details=dict(details or {}),
            created_by=created_by,
            created_at=f"2026-03-25T00:00:{self._event_seq:02d}Z",
        )
        self.jobs[job_euid] = replace(job, events=[*job.events, event], updated_at=event.created_at)
        return event

    def update_cluster_job_status(
        self,
        *,
        job_euid: str,
        state: str,
        created_by: str,
        started_at: str | None = None,
        completed_at: str | None = None,
        return_code: int | None = None,
        error: str | None = None,
        output_summary: str | None = None,
        cluster: dict | None = None,
    ) -> ClusterJobRecord:
        _ = created_by
        job = self.jobs[job_euid]
        updated = replace(
            job,
            state=state,
            updated_at=completed_at or started_at or "2026-03-25T00:10:00Z",
            started_at=started_at if started_at is not None else job.started_at,
            completed_at=completed_at if completed_at is not None else job.completed_at,
            return_code=return_code if return_code is not None else job.return_code,
            error=error if error is not None else job.error,
            output_summary=output_summary if output_summary is not None else job.output_summary,
            cluster=dict(cluster or job.cluster),
        )
        self.jobs[job_euid] = updated
        return updated

    def get_cluster_job(self, job_euid: str) -> ClusterJobRecord | None:
        return self.jobs.get(job_euid)


class FakeDaylilyEcClient:
    def cluster_describe(self, *, cluster_name: str, region: str):
        _ = region
        return {
            "clusterName": cluster_name,
            "clusterStatus": "CREATE_COMPLETE",
            "computeFleetStatus": "RUNNING",
            "headNode": {
                "instanceType": "c7i.large",
                "state": "running",
            },
            "scheduler": {"type": "slurm"},
            "tags": [
                {
                    "key": "aws-parallelcluster-monitor-bucket",
                    "value": "s3://ursa-bucket",
                }
            ],
        }


def test_cluster_job_manager_spawns_dedicated_worker_process(monkeypatch, tmp_path: Path) -> None:
    store = MemoryResourceStore()
    captured: dict[str, object] = {}

    class _DummyPopen:
        pid = 43210

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return _DummyPopen()

    monkeypatch.setattr("daylib_ursa.cluster_jobs.subprocess.Popen", fake_popen)

    manager = ClusterJobManager(
        resource_store=store,
        cluster_service=ClusterService(regions=["us-west-2"], client=FakeDaylilyEcClient()),
        workspace_root=tmp_path,
        python_executable="/usr/bin/python3",
    )

    job = manager.start_create_job(
        cluster_name="cluster-1",
        region_az="us-west-2d",
        ssh_key_name="omics-key",
        reference_s3_uri="s3://refs",
        control_data_s3_uri="s3://control",
        stage_s3_uri="s3://stage",
        export_destination_s3_uri="s3://export",
        tenant_id=TENANT_ID,
        owner_user_id="user-1",
        sponsor_user_id="user-2",
        aws_profile="ursa",
        contact_email="ops@example.com",
        pass_on_warn=False,
        debug=False,
    )

    assert captured["cmd"] == [
        "/usr/bin/python3",
        "-m",
        "daylib_ursa.cluster_job_worker",
        "--job-euid",
        job.job_euid,
        "--workspace-root",
        str(tmp_path.resolve()),
    ]
    assert captured["kwargs"]["cwd"] == str(tmp_path.resolve())
    assert any(event.event_type == "worker-launch" for event in job.events)


def test_run_cluster_create_job_uses_fake_tools_and_leaves_no_home_state(
    monkeypatch,
    tmp_path: Path,
) -> None:
    home_dir = tmp_path / "home"
    home_dir.mkdir()
    monkeypatch.setenv("HOME", str(home_dir))
    monkeypatch.setattr(
        "daylib_ursa.cluster_jobs.run_preflight_sync",
        lambda **_kwargs: subprocess.CompletedProcess(
            ["daylily-ec", "preflight"], 0, "preflight ok\n", ""
        ),
    )
    monkeypatch.setattr(
        "daylib_ursa.cluster_jobs.run_create_sync",
        lambda **_kwargs: subprocess.CompletedProcess(
            ["daylily-ec", "create"], 0, "create ok\n", ""
        ),
    )

    def fake_write_dayec_cluster_config(*, dest, **_kwargs):
        path = Path(dest)
        path.write_text("ephemeral_cluster:\n  config: {}\n", encoding="utf-8")
        return path

    monkeypatch.setattr(
        "daylib_ursa.cluster_jobs.write_dayec_cluster_config",
        fake_write_dayec_cluster_config,
    )

    store = MemoryResourceStore()
    job = store.create_cluster_job(
        cluster_name="cluster-1",
        region="us-west-2",
        region_az="us-west-2d",
        tenant_id=TENANT_ID,
        owner_user_id="user-1",
        sponsor_user_id="user-2",
        request={
            "cluster_name": "cluster-1",
            "region": "us-west-2",
            "region_az": "us-west-2d",
            "ssh_key_name": "omics-key",
            "reference_s3_uri": "s3://refs",
            "control_data_s3_uri": "s3://control",
            "stage_s3_uri": "s3://stage",
            "export_destination_s3_uri": "s3://export",
            "aws_profile": None,
            "contact_email": "ops@example.com",
            "pass_on_warn": False,
            "debug": False,
        },
    )

    run_cluster_create_job(
        resource_store=store,
        cluster_service=ClusterService(regions=["us-west-2"], client=FakeDaylilyEcClient()),
        workspace_root=tmp_path,
        job_euid=job.job_euid,
    )

    updated = store.get_cluster_job(job.job_euid)
    assert updated is not None
    assert updated.state == "COMPLETED"
    assert updated.return_code == 0
    assert updated.cluster["cluster_name"] == "cluster-1"
    assert updated.cluster["cluster_status"] == "CREATE_COMPLETE"
    assert [event.event_type for event in updated.events] == ["runner", "preflight", "create"]
    assert not (home_dir / ".ursa" / "cluster-create").exists()


def test_run_dayoa_dyr_help_job_uses_headnode_tmux_script() -> None:
    store = MemoryResourceStore()
    captured: dict[str, object] = {}

    class FakeHeadnodeService:
        def _run_headnode_script(self, **kwargs):
            captured.update(kwargs)
            return (
                object(),
                SimpleNamespace(
                    stdout="Usage: dy-r [OPTIONS]\n__URSA_CLUSTER_JOB_RC__=0\n",
                    stderr="",
                    response_code=0,
                    status="Success",
                ),
                None,
            )

    job = store.create_cluster_job(
        cluster_name="majors-cluster",
        region="us-west-2",
        region_az="us-west-2d",
        tenant_id=TENANT_ID,
        owner_user_id="user-1",
        sponsor_user_id="user-2",
        request={
            "command": "dy-r help",
            "analysis_dir": "/fsx/analysis_results/ubuntu/smoke/daylily-omics-analysis",
            "executor": "local",
            "genome_build": "hg38",
            "tmux_session": "ursa-dyr-help-smoke",
            "timeout_seconds": 120,
            "aws_profile": "lsmc",
            "environment": {
                "PUPPETEER_EXECUTABLE_PATH": (
                    "/home/ubuntu/.cache/puppeteer/chrome-headless-shell/"
                    "linux-149/chrome-headless-shell"
                )
            },
        },
    )

    run_dayoa_dyr_help_job(
        resource_store=store,
        cluster_service=FakeHeadnodeService(),
        job_euid=job.job_euid,
    )

    updated = store.get_cluster_job(job.job_euid)
    assert updated is not None
    assert updated.state == "COMPLETED"
    assert updated.return_code == 0
    assert updated.output_summary == "DayOA dy-r help completed"
    assert updated.cluster["tmux_session"] == "ursa-dyr-help-smoke"
    script = str(captured["script"])
    assert "sudo -u ubuntu" in script
    assert "source dyoainit" in script
    assert "export PUPPETEER_EXECUTABLE_PATH=" in script
    assert "dy-a local hg38" in script
    assert "dy-r help" in script


def test_run_dayoa_dyr_help_job_honors_success_marker_from_failed_transport() -> None:
    store = MemoryResourceStore()

    class FakeHeadnodeService:
        def _run_headnode_script(self, **_kwargs):
            return (
                None,
                None,
                HeadnodeProbeResult(
                    probe_type="cluster-job",
                    cluster_name="majors-cluster",
                    region="us-west-2",
                    instance_id="i-123",
                    captured_at="2026-03-25T00:00:00Z",
                    cache_expires_at="2026-03-25T00:00:00Z",
                    ttl_seconds=0,
                    data={
                        "stdout": (
                            "WORKFLOW SUCCESS\n"
                            "RETURN CODE: 0\n"
                            "__URSA_CLUSTER_JOB_RC__=0\n"
                        ),
                        "stderr": "failed to run commands: exit status 1",
                        "response_code": 1,
                        "status": "Failed",
                    },
                    error="failed to run commands: exit status 1",
                ),
            )

    job = store.create_cluster_job(
        cluster_name="majors-cluster",
        region="us-west-2",
        region_az="us-west-2d",
        tenant_id=TENANT_ID,
        owner_user_id="user-1",
        sponsor_user_id="user-2",
        request={
            "command": "dy-r help",
            "analysis_dir": "/fsx/analysis_results/ubuntu/smoke/daylily-omics-analysis",
            "executor": "local",
            "genome_build": "hg38",
            "tmux_session": "ursa-dyr-help-smoke",
            "timeout_seconds": 120,
            "aws_profile": "lsmc",
            "environment": {},
        },
    )

    run_dayoa_dyr_help_job(
        resource_store=store,
        cluster_service=FakeHeadnodeService(),
        job_euid=job.job_euid,
    )

    updated = store.get_cluster_job(job.job_euid)
    assert updated is not None
    assert updated.state == "COMPLETED"
    assert updated.return_code == 0
    assert updated.error is None
    assert updated.cluster["transport_error"] == "failed to run commands: exit status 1"
    assert updated.events[-1].status == "COMPLETED"


def test_run_dayoa_dyr_help_job_fails_hard_on_missing_request_fields() -> None:
    store = MemoryResourceStore()
    job = store.create_cluster_job(
        cluster_name="majors-cluster",
        region="us-west-2",
        region_az="us-west-2d",
        tenant_id=TENANT_ID,
        owner_user_id="user-1",
        sponsor_user_id="user-2",
        request={"command": "dy-r help"},
    )

    run_dayoa_dyr_help_job(
        resource_store=store,
        cluster_service=object(),
        job_euid=job.job_euid,
    )

    updated = store.get_cluster_job(job.job_euid)
    assert updated is not None
    assert updated.state == "FAILED"
    assert "analysis_dir is required" in str(updated.error)


def test_cluster_job_manager_records_create_dry_run_without_spawning_worker(
    monkeypatch, tmp_path: Path
) -> None:
    store = MemoryResourceStore()

    def fail_popen(*_args, **_kwargs):
        raise AssertionError("dry-run cluster create must not spawn a worker")

    monkeypatch.setattr("daylib_ursa.cluster_jobs.subprocess.Popen", fail_popen)
    manager = ClusterJobManager(
        resource_store=store,
        cluster_service=ClusterService(regions=["us-west-2"], client=FakeDaylilyEcClient()),
        workspace_root=tmp_path,
        python_executable="/usr/bin/python3",
    )

    job = manager.record_create_dry_run(
        cluster_name="cluster-1",
        region_az="us-west-2d",
        ssh_key_name="omics-key",
        reference_s3_uri="s3://refs",
        control_data_s3_uri="s3://control",
        stage_s3_uri="s3://stage",
        export_destination_s3_uri="s3://export",
        tenant_id=TENANT_ID,
        owner_user_id="user-1",
        sponsor_user_id="user-2",
        aws_profile="ursa",
        contact_email="ops@example.com",
        pass_on_warn=False,
        debug=False,
        dry_run_result={
            "return_code": 0,
            "summary": "Dry-run passed",
            "stdout": "ok",
            "stderr": "",
        },
    )

    assert job.state == "COMPLETED"
    assert job.return_code == 0
    assert job.request["dry_run"] is True
    assert job.cluster == {"dry_run": True}
    assert any(event.event_type == "create-dry-run" for event in job.events)
