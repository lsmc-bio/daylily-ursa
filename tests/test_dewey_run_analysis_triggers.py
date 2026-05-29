from __future__ import annotations

from dataclasses import dataclass, field, replace
import os
import subprocess
import uuid

import httpx
from fastapi.testclient import TestClient

from daylib_ursa.config import Settings
from daylib_ursa.analysis_jobs import AnalysisJobManager
from daylib_ursa.integrations.dewey_client import DeweyClient
from daylib_ursa.run_directory_orchestrator import (
    RunDirectoryOrchestrator,
    RunDirectoryPolicy,
    SelectedCluster,
)
from daylib_ursa.resource_store import (
    AnalysisJobEventRecord,
    AnalysisJobRecord,
    DeweyRunTriggerRecord,
    ManifestRecord,
    WorksetRecord,
)
from daylib_ursa.workset_api import create_app

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
OWNER_USER_ID = "00000000-0000-0000-0000-000000000101"


class _DummyBloomClient:
    def __init__(self) -> None:
        self.run_directory_calls: list[dict] = []

    def create_or_reuse_run_directory_run(self, **kwargs):
        self.run_directory_calls.append(dict(kwargs))
        return {
            "run_euid": "BLOOM-RUN-1",
            "status": "created",
            "run_folder_name": kwargs["run_folder_name"],
        }


class _DummyClusterService:
    client = object()


@dataclass
class _DummyStore:
    calls: list[dict] = field(default_factory=list)


class _MemoryResourceStore:
    def __init__(self) -> None:
        self.worksets: dict[str, WorksetRecord] = {}
        self.manifests: dict[str, ManifestRecord] = {}
        self.analysis_jobs: dict[str, AnalysisJobRecord] = {}
        self.analysis_events: dict[str, list[AnalysisJobEventRecord]] = {}
        self.triggers_by_euid: dict[str, DeweyRunTriggerRecord] = {}
        self.triggers_by_idempotency: dict[str, DeweyRunTriggerRecord] = {}
        self.external_objects: list[dict] = []
        self.external_object_parent_lookups: list[dict] = []
        self._workset_seq = 0
        self._manifest_seq = 0
        self._analysis_job_seq = 0
        self._analysis_event_seq = 0

    def create_workset(
        self,
        *,
        name: str,
        tenant_id: uuid.UUID,
        owner_user_id: str,
        artifact_set_euids,
        metadata,
    ):
        self._workset_seq += 1
        record = WorksetRecord(
            workset_euid=f"WS-{self._workset_seq}",
            name=name,
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            state="ACTIVE",
            artifact_set_euids=list(artifact_set_euids or []),
            metadata=dict(metadata or {}),
            created_at="2026-05-27T00:00:00Z",
            updated_at="2026-05-27T00:00:00Z",
            manifests=[],
            analysis_euids=[],
        )
        self.worksets[record.workset_euid] = record
        return record

    def get_workset(self, workset_euid: str):
        return self.worksets.get(workset_euid)

    def create_manifest(
        self,
        *,
        workset_euid: str,
        name: str,
        artifact_set_euid: str | None,
        artifact_euids,
        input_references,
        metadata,
    ):
        workset = self.worksets[workset_euid]
        self._manifest_seq += 1
        manifest = ManifestRecord(
            manifest_euid=f"MF-{self._manifest_seq}",
            name=name,
            workset_euid=workset_euid,
            tenant_id=workset.tenant_id,
            owner_user_id=workset.owner_user_id,
            artifact_set_euid=artifact_set_euid,
            artifact_euids=list(artifact_euids or []),
            input_references=list(input_references or []),
            metadata=dict(metadata or {}),
            created_at="2026-05-27T00:01:00Z",
            updated_at="2026-05-27T00:01:00Z",
            state="ACTIVE",
        )
        self.manifests[manifest.manifest_euid] = manifest
        self.worksets[workset_euid] = replace(
            workset,
            manifests=[*workset.manifests, manifest],
            updated_at="2026-05-27T00:01:00Z",
        )
        return manifest

    def get_manifest(self, manifest_euid: str):
        return self.manifests.get(manifest_euid)

    def create_analysis_job(
        self,
        *,
        job_name: str,
        workset_euid: str,
        manifest_euid: str,
        cluster_name: str,
        region: str,
        tenant_id: uuid.UUID,
        owner_user_id: str,
        request,
    ):
        self._analysis_job_seq += 1
        record = AnalysisJobRecord(
            job_euid=f"AJ-{self._analysis_job_seq}",
            job_name=job_name,
            workset_euid=workset_euid,
            manifest_euid=manifest_euid,
            cluster_name=cluster_name,
            region=region,
            tenant_id=tenant_id,
            owner_user_id=owner_user_id,
            state="DEFINED",
            created_at="2026-05-27T00:02:00Z",
            updated_at="2026-05-27T00:02:00Z",
            started_at=None,
            completed_at=None,
            return_code=None,
            error=None,
            output_summary=None,
            request=dict(request or {}),
            launch={},
            events=[],
            analysis_experiment_euid=str(
                dict(request or {}).get("analysis_experiment_euid") or ""
            ).strip()
            or None,
        )
        self.analysis_jobs[record.job_euid] = record
        return record

    def add_analysis_job_event(
        self,
        *,
        job_euid: str,
        event_type: str,
        status: str,
        summary: str,
        details=None,
        created_by=None,
    ):
        self._analysis_event_seq += 1
        event = AnalysisJobEventRecord(
            event_euid=f"AJE-{self._analysis_event_seq}",
            job_euid=job_euid,
            event_type=event_type,
            status=status,
            summary=summary,
            details=dict(details or {}),
            created_by=created_by,
            created_at="2026-05-27T00:02:30Z",
        )
        record = self.analysis_jobs[job_euid]
        updated = replace(
            record,
            events=[event, *record.events],
            updated_at=event.created_at,
        )
        self.analysis_jobs[job_euid] = updated
        self.analysis_events.setdefault(job_euid, []).append(event)
        return event

    def update_analysis_job_status(self, *, job_euid: str, state: str, created_by: str, **updates):
        _ = created_by
        record = self.analysis_jobs[job_euid]
        updated = replace(
            record,
            state=state,
            updated_at="2026-05-27T00:03:00Z",
            started_at=updates.get("started_at", record.started_at),
            completed_at=updates.get("completed_at", record.completed_at),
            return_code=updates.get("return_code", record.return_code),
            error=updates.get("error", record.error),
            output_summary=updates.get("output_summary", record.output_summary),
            launch=updates.get("launch", record.launch),
        )
        self.analysis_jobs[job_euid] = updated
        return updated

    def update_analysis_job_request(self, *, job_euid: str, request: dict, created_by: str):
        _ = created_by
        record = self.analysis_jobs[job_euid]
        updated = replace(
            record,
            request=dict(request or {}),
            updated_at="2026-05-27T00:03:30Z",
        )
        self.analysis_jobs[job_euid] = updated
        return updated

    def update_analysis_job_assignment(
        self,
        *,
        job_euid: str,
        cluster_name: str,
        region: str,
        created_by: str,
    ):
        _ = created_by
        record = self.analysis_jobs[job_euid]
        updated = replace(
            record,
            cluster_name=cluster_name,
            region=region,
            updated_at="2026-05-27T00:03:45Z",
        )
        self.analysis_jobs[job_euid] = updated
        return updated

    def get_analysis_job(self, job_euid: str):
        return self.analysis_jobs.get(job_euid)

    def list_analysis_jobs(self, *, tenant_id: uuid.UUID | None = None, limit: int = 200):
        _ = limit
        return [
            job
            for job in self.analysis_jobs.values()
            if tenant_id is None or job.tenant_id == tenant_id
        ]

    def get_staging_job(self, staging_job_euid: str):
        _ = staging_job_euid
        return None

    def create_dewey_run_trigger(
        self,
        *,
        trigger_euid: str,
        idempotency_key: str,
        fingerprint: str,
        status: str,
        command_id: str,
        request: dict,
        response: dict,
        analysis_job_euid: str | None = None,
        staging_job_euid: str | None = None,
        error: str | None = None,
    ):
        record = DeweyRunTriggerRecord(
            trigger_euid=trigger_euid,
            idempotency_key=idempotency_key,
            fingerprint=fingerprint,
            status=status,
            command_id=command_id,
            request=dict(request or {}),
            response=dict(response or {}),
            analysis_job_euid=analysis_job_euid,
            staging_job_euid=staging_job_euid,
            error=error,
            created_at="2026-05-27T00:04:00Z",
            updated_at="2026-05-27T00:04:00Z",
        )
        self.triggers_by_euid[trigger_euid] = record
        self.triggers_by_idempotency[idempotency_key] = record
        return record

    def update_dewey_run_trigger(
        self,
        *,
        trigger_euid: str,
        status: str,
        response: dict,
        analysis_job_euid: str | None = None,
        staging_job_euid: str | None = None,
        error: str | None = None,
    ):
        record = self.triggers_by_euid[trigger_euid]
        updated = replace(
            record,
            status=status,
            response=dict(response or {}),
            analysis_job_euid=analysis_job_euid,
            staging_job_euid=staging_job_euid,
            error=error,
            updated_at="2026-05-27T00:05:00Z",
        )
        self.triggers_by_euid[trigger_euid] = updated
        self.triggers_by_idempotency[updated.idempotency_key] = updated
        return updated

    def create_external_object_child(
        self,
        *,
        parent_template_code: str,
        parent_euid: str,
        parent_external_id_key: str | None = None,
        external_system: str,
        external_object_type: str,
        external_object_id: str,
        relation_type: str = "external_object",
        metadata=None,
    ):
        _ = parent_template_code
        self.external_object_parent_lookups.append(
            {
                "parent_euid": parent_euid,
                "parent_external_id_key": parent_external_id_key,
            }
        )
        row = {
            "external_object_euid": f"URXO-{len(self.external_objects) + 1}",
            "parent_euid": parent_euid,
            "external_system": external_system,
            "external_object_type": external_object_type,
            "external_object_id": external_object_id,
            "relation_type": relation_type,
            "metadata": dict(metadata or {}),
            "created_at": "2026-05-27T00:05:00Z",
            "updated_at": "2026-05-27T00:05:00Z",
            "state": "ACTIVE",
        }
        self.external_objects.append(row)
        return row

    def external_object_payload(self, record):
        return dict(record)

    def get_dewey_run_trigger(self, trigger_euid: str):
        return self.triggers_by_euid.get(trigger_euid)

    def get_dewey_run_trigger_by_idempotency(self, idempotency_key: str):
        return self.triggers_by_idempotency.get(idempotency_key)


class _MissingParentResourceStore(_MemoryResourceStore):
    def create_external_object_child(self, **_kwargs):
        raise KeyError("Parent instance not found: URDT-MISSING")


class _DummyAnalysisJobManager:
    def __init__(self, resources: _MemoryResourceStore, terminal_state: str = "RUNNING") -> None:
        self.resources = resources
        self.terminal_state = terminal_state
        self.launch_calls: list[dict] = []

    def launch_job(self, job_euid: str, *, actor_user_id: str, request_overrides=None):
        self.launch_calls.append(
            {
                "job_euid": job_euid,
                "actor_user_id": actor_user_id,
                "request_overrides": dict(request_overrides or {}),
            }
        )
        if self.terminal_state == "PRELAUNCH_FAILED":
            return self.resources.update_analysis_job_status(
                job_euid=job_euid,
                state="FAILED",
                created_by=actor_user_id,
                started_at="2026-05-27T00:03:00Z",
                completed_at="2026-05-27T00:04:00Z",
                return_code=1,
                error="AnalysisIdentityError: executing_entity must be path-safe",
                output_summary="AnalysisIdentityError: executing_entity must be path-safe",
                launch={"run_context_file": ".ursa-run-contexts/AJ-1/config/runs.tsv"},
            )
        if self.terminal_state == "COMPLETED":
            return self.resources.update_analysis_job_status(
                job_euid=job_euid,
                state="COMPLETED",
                created_by=actor_user_id,
                started_at="2026-05-27T00:03:00Z",
                completed_at="2026-05-27T00:04:00Z",
                return_code=0,
                output_summary="Workflow status: COMPLETED",
                launch={"session_name": "dewey-run-1", "exit_code": 0},
            )
        if self.terminal_state == "FAILED":
            return self.resources.update_analysis_job_status(
                job_euid=job_euid,
                state="FAILED",
                created_by=actor_user_id,
                started_at="2026-05-27T00:03:00Z",
                completed_at="2026-05-27T00:04:00Z",
                return_code=1,
                error="workflow failed",
                output_summary="Workflow status: FAILED",
                launch={"session_name": "dewey-run-1", "exit_code": 1},
            )
        return self.resources.update_analysis_job_status(
            job_euid=job_euid,
            state="RUNNING",
            created_by=actor_user_id,
            started_at="2026-05-27T00:03:00Z",
            return_code=0,
            output_summary="Workflow session launched",
            launch={"session_name": "dewey-run-1"},
        )


class _DummyRunDirectoryOrchestrator:
    def __init__(self) -> None:
        self.start_calls: list[str] = []

    def start_trigger(self, trigger_euid: str):
        self.start_calls.append(trigger_euid)
        return {"pid": os.getpid(), "command": ["fake-worker", trigger_euid]}


class _FakeRunAnalysisCommand:
    command_id = "illumina_run_qc"
    command_class = "run_analysis"
    input_contract = "run_context"

    def launch_argv(self, **kwargs):
        argv = [
            "workflow",
            "launch",
            "--analysis-id",
            kwargs["analysis_id"],
            "--executing-entity",
            kwargs["executing_entity"],
            "--run-context-file",
            kwargs["run_context_file"],
            "--session-name",
            kwargs["session_name"],
        ]
        for flag, key in (
            ("--export-destination-s3-uri", "export_destination_s3_uri"),
            ("--export-trigger", "export_trigger"),
            ("--artifact-registration-command-id", "artifact_registration_command_id"),
            ("--dewey-url", "dewey_url"),
            ("--dewey-token-env", "dewey_token_env"),
            (
                "--dewey-analysis-dir-external-object-id",
                "dewey_analysis_dir_external_object_id",
            ),
            ("--dewey-run-artifact-euid", "dewey_run_artifact_euid"),
            ("--dewey-ursa-analysis-euid", "dewey_ursa_analysis_euid"),
        ):
            value = kwargs.get(key)
            if value:
                argv.extend([flag, value])
        if kwargs.get("delete_on_export_success"):
            argv.append("--delete-on-export-success")
        if kwargs.get("replace_existing_analysis_dir"):
            argv.append("--replace-existing-analysis-dir")
        return argv


class _DummyDeweyClient:
    def __init__(
        self,
        *,
        artifact_type: str = "sequencing_run_dir",
        storage_uri: str = "s3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/",
    ) -> None:
        self.result_calls: list[dict] = []
        self.external_objects: list[dict] = []
        self.external_relations: list[dict] = []
        self.artifact_type = artifact_type
        self.storage_uri = storage_uri

    def resolve_artifact(self, artifact_euid: str):
        return {
            "artifact_euid": artifact_euid,
            "artifact_type": self.artifact_type,
            "storage_uri": self.storage_uri,
        }

    def register_analysis_results(self, *, payload, idempotency_key: str):
        self.result_calls.append({"payload": dict(payload), "idempotency_key": idempotency_key})
        return {
            "receipt": {"artifact_set_euid": "AS-RESULT-1"},
            "artifact_set": {"artifact_set_euid": "AS-RESULT-1"},
        }

    def create_external_object(self, **kwargs):
        row = {
            "external_object_euid": f"EXT-{len(self.external_objects) + 1}",
            **kwargs,
        }
        self.external_objects.append(row)
        return row

    def attach_external_object_relation(self, **kwargs):
        row = {
            "external_object_relation_euid": f"REL-{len(self.external_relations) + 1}",
            **kwargs,
        }
        self.external_relations.append(row)
        return row


def _settings() -> Settings:
    return Settings(
        cors_origins="*",
        ursa_observability_service_token="ursa-observability-token",
        ursa_write_service_token="ursa-write-token",
        ursa_tapdb_admin_service_token="ursa-tapdb-admin-token",
        session_secret_key="ursa-session-secret",
        cognito_domain="auth.example.test",
        cognito_app_client_id="client-123",
        cognito_app_client_secret="ursa-cognito-secret",
        cognito_callback_url="https://testserver/auth/callback",
        cognito_logout_url="https://testserver/auth/logout",
        bloom_base_url="https://bloom.example",
        atlas_base_url="https://atlas.example",
        ursa_internal_output_bucket="ursa-internal",
        deployment_name="unit",
        allowed_hosts="testserver,localhost",
        ursa_tapdb_mount_enabled=False,
        ursa_run_directory_analysis_tenant_id=str(TENANT_ID),
        ursa_run_directory_analysis_owner_user_id=OWNER_USER_ID,
        ursa_run_directory_analysis_region="us-west-2",
        ursa_run_directory_analysis_reference_s3_uri="s3://refs/hg38/",
        ursa_run_directory_analysis_stage_target="/staging/run-directories",
        ursa_run_directory_analysis_destination_s3_uri="s3://bucket/derived/",
        ursa_run_directory_analysis_project="daylily",
        ursa_run_directory_analysis_aws_profile="lsmc",
    )


def _app(
    monkeypatch,
    *,
    resource_store: _MemoryResourceStore | None = None,
    analysis_job_manager: _DummyAnalysisJobManager | None = None,
    dewey_client: _DummyDeweyClient | None = None,
    bloom_client: _DummyBloomClient | None = None,
    run_directory_orchestrator: _DummyRunDirectoryOrchestrator | None = None,
    settings: Settings | None = None,
):
    resources = resource_store or _MemoryResourceStore()
    manager = analysis_job_manager or _DummyAnalysisJobManager(resources)

    def fake_analysis_command_payload(command_id: str, optional_features=None):
        _ = optional_features
        run_analysis_commands = {
            "illumina_run_qc",
            "illumina_bclconvert",
            "illumina_run_qc_bclconvert",
            "ont_run_qc",
            "ultima_run_qc",
        }
        if command_id not in {
            "illumina_snv_alignstats_relatedness_vep_multiqc",
            *run_analysis_commands,
        }:
            raise ValueError(f"Unknown analysis command: {command_id}")
        return {
            "command_id": command_id,
            "workflow": "daylily-omics-analysis",
            "command_class": "run_analysis" if command_id in run_analysis_commands else "sample_analysis",
            "input_contract": "run_context",
        }

    monkeypatch.setattr(
        "daylib_ursa.workset_api.analysis_command_payload",
        fake_analysis_command_payload,
    )
    return create_app(
        _DummyStore(),
        bloom_client=bloom_client or _DummyBloomClient(),
        atlas_client=None,
        dewey_client=dewey_client,
        resource_store=resources,
        cluster_service=_DummyClusterService(),
        analysis_job_manager=manager,
        run_directory_orchestrator=run_directory_orchestrator
        or _DummyRunDirectoryOrchestrator(),
        settings=settings or _settings(),
    )


def _trigger_body() -> dict:
    return {
        "dewey_receipt_euid": "RCP-1",
        "run_artifact_set_euid": "AS-RUN-1",
        "platform": "ILMN",
        "command_id": "illumina_snv_alignstats_relatedness_vep_multiqc",
        "params": {"emit_multiqc": True},
        "sidecar_artifact_euid": "AT-SIDECAR-1",
        "sidecar_version_id": "v1",
        "run_context_refs": {"run_root_artifact_euid": "AT-RUN-1"},
        "sample_read_refs": [{"read_artifact_euid": "AT-FQ-1"}],
        "sample_identifiers": [{"sample_euid": "SAMPLE-1"}],
        "auto_launch": False,
    }


def _execution_context(*, result_registration: dict | None = None) -> dict:
    payload = {
        "tenant_id": str(TENANT_ID),
        "owner_user_id": OWNER_USER_ID,
        "workset": {
            "name": "Dewey run workset",
            "artifact_set_euids": ["AS-RUN-1"],
            "metadata": {"source": "dewey"},
        },
        "manifest": {
            "name": "Dewey run manifest",
            "artifact_set_euid": "AS-RUN-1",
            "artifact_euids": ["AT-FQ-1"],
            "input_references": [{"reference_type": "artifact_set_euid", "value": "AS-RUN-1"}],
            "metadata": {
                "analysis_samples_manifest": {
                    "filename": "analysis_samples.tsv",
                    "content": (
                        "sample_id\tILMN_R1_PATH\tILMN_R2_PATH\n"
                        "SAMPLE-1\ts3://reads/r1.fastq.gz\ts3://reads/r2.fastq.gz\n"
                    ),
                }
            },
        },
        "cluster_name": "cluster-1",
        "region": "us-west-2",
        "reference_s3_uri": "s3://refs/hg38/",
        "stage_target": "/staging/staged_external_sequencing_data",
        "destination": "s3://analysis-results/run-1/",
        "session_name": "dewey-run-1",
        "project": "daylily",
    }
    if result_registration is not None:
        payload["result_registration"] = result_registration
    return payload


def test_dewey_trigger_endpoint_requires_service_token_and_idempotency(monkeypatch) -> None:
    app = _app(monkeypatch)
    with TestClient(app) as client:
        unauthorized = client.post(
            "/api/v1/dewey/run-analysis-triggers",
            headers={"Idempotency-Key": "idem-1"},
            json=_trigger_body(),
        )
        assert unauthorized.status_code == 401

        missing_idempotency = client.post(
            "/api/v1/dewey/run-analysis-triggers",
            headers={"X-API-Key": "ursa-write-token"},
            json=_trigger_body(),
        )
        assert missing_idempotency.status_code == 400

        created = client.post(
            "/api/v1/dewey/run-analysis-triggers",
            headers={"X-API-Key": "ursa-write-token", "Idempotency-Key": "idem-1"},
            json=_trigger_body(),
        )
        assert created.status_code == 202, created.text
        payload = created.json()
        assert payload["status"] == "QUEUED"
        assert payload["command_id"] == "illumina_snv_alignstats_relatedness_vep_multiqc"
        assert payload["command_preview"]["catalog_command"]["input_contract"] == "run_context"
        assert "shell_preview" not in payload["command_preview"]

        replay = client.post(
            "/api/v1/dewey/run-analysis-triggers",
            headers={"X-API-Key": "ursa-write-token", "Idempotency-Key": "idem-1"},
            json=_trigger_body(),
        )
        assert replay.status_code == 202
        assert replay.json()["trigger_euid"] == payload["trigger_euid"]

        fetched = client.get(
            f"/api/v1/dewey/run-analysis-triggers/{payload['trigger_euid']}",
            headers={"X-API-Key": "ursa-write-token"},
        )
        assert fetched.status_code == 200
        assert fetched.json()["trigger_euid"] == payload["trigger_euid"]


def test_dewey_trigger_rejects_payload_change_and_unknown_command(monkeypatch) -> None:
    app = _app(monkeypatch)
    with TestClient(app) as client:
        created = client.post(
            "/api/v1/dewey/run-analysis-triggers",
            headers={"X-API-Key": "ursa-write-token", "Idempotency-Key": "idem-2"},
            json=_trigger_body(),
        )
        assert created.status_code == 202
        changed = _trigger_body()
        changed["params"] = {"emit_multiqc": False}
        conflict = client.post(
            "/api/v1/dewey/run-analysis-triggers",
            headers={"X-API-Key": "ursa-write-token", "Idempotency-Key": "idem-2"},
            json=changed,
        )
        assert conflict.status_code == 409

        unknown = _trigger_body()
        unknown["command_id"] = "bash -lc rm -rf /"
        rejected = client.post(
            "/api/v1/dewey/run-analysis-triggers",
            headers={"X-API-Key": "ursa-write-token", "Idempotency-Key": "idem-3"},
            json=unknown,
        )
        assert rejected.status_code == 400
        assert "Unknown analysis command" in rejected.text

        arbitrary_shell = _trigger_body()
        arbitrary_shell["command_string"] = "bash -lc whoami"
        invalid = client.post(
            "/api/v1/dewey/run-analysis-triggers",
            headers={"X-API-Key": "ursa-write-token", "Idempotency-Key": "idem-4"},
            json=arbitrary_shell,
        )
        assert invalid.status_code == 422


def test_dewey_trigger_auto_launch_creates_analysis_job_and_replays(monkeypatch) -> None:
    resources = _MemoryResourceStore()
    app = _app(monkeypatch, resource_store=resources)
    body = _trigger_body()
    body["auto_launch"] = True
    body["execution_context"] = _execution_context()

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/dewey/run-analysis-triggers",
            headers={"X-API-Key": "ursa-write-token", "Idempotency-Key": "idem-launch-1"},
            json=body,
        )
        assert created.status_code == 202, created.text
        payload = created.json()
        assert payload["status"] == "RUNNING"
        assert payload["analysis_job_euid"] == "AJ-1"
        assert len(resources.analysis_jobs) == 1
        assert resources.analysis_jobs["AJ-1"].request["analysis_command_id"] == (
            "illumina_snv_alignstats_relatedness_vep_multiqc"
        )

        replay = client.post(
            "/api/v1/dewey/run-analysis-triggers",
            headers={"X-API-Key": "ursa-write-token", "Idempotency-Key": "idem-launch-1"},
            json=body,
        )
        assert replay.status_code == 202, replay.text
        assert replay.json()["trigger_euid"] == payload["trigger_euid"]
        assert len(resources.analysis_jobs) == 1


def test_dewey_trigger_terminal_launch_registers_results(monkeypatch) -> None:
    resources = _MemoryResourceStore()
    manager = _DummyAnalysisJobManager(resources, terminal_state="COMPLETED")
    dewey = _DummyDeweyClient()
    app = _app(
        monkeypatch,
        resource_store=resources,
        analysis_job_manager=manager,
        dewey_client=dewey,
    )
    body = _trigger_body()
    body["auto_launch"] = True
    body["execution_context"] = _execution_context(
        result_registration={
            "idempotency_key": "dewey-result-1",
            "payload": {
                "analysis_euid": "AN-1",
                "result_root_uri": "s3://analysis-results/run-1/",
                "artifacts": [
                    {
                        "logical_name": "multiqc",
                        "artifact_role": "multiqc_html",
                        "relative_path": "multiqc_report.html",
                    }
                ],
            },
        }
    )

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/dewey/run-analysis-triggers",
            headers={"X-API-Key": "ursa-write-token", "Idempotency-Key": "idem-terminal-1"},
            json=body,
        )

    assert created.status_code == 202, created.text
    payload = created.json()
    assert payload["status"] == "COMPLETED"
    assert payload["dewey_result"]["receipt"]["artifact_set_euid"] == "AS-RESULT-1"
    assert len(dewey.result_calls) == 1
    call = dewey.result_calls[0]
    assert call["idempotency_key"] == "dewey-result-1"
    assert call["payload"]["result_status"] == "succeeded"
    assert call["payload"]["analysis_job_euid"] == "AJ-1"
    assert call["payload"]["sample_identifiers"] == [{"sample_euid": "SAMPLE-1"}]
    assert {"ref_type": "ursa_analysis_job_euid", "value": "AJ-1"} in call["payload"][
        "lineage_refs"
    ]


def test_run_directory_trigger_links_supplied_bloom_run_manifest_jobs_and_relations(monkeypatch) -> None:
    resources = _MemoryResourceStore()
    dewey = _DummyDeweyClient()
    bloom = _DummyBloomClient()
    orchestrator = _DummyRunDirectoryOrchestrator()
    app = _app(
        monkeypatch,
        resource_store=resources,
        dewey_client=dewey,
        bloom_client=bloom,
        run_directory_orchestrator=orchestrator,
    )
    body = {
        "dewey_run_artifact_euid": "AT-RUN-1",
        "run_storage_uri": "s3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/",
        "run_folder_name": "run-a",
        "platform": "ILMN",
        "command_ids": ["illumina_run_qc"],
        "producer_system": "offwithyou",
        "producer_object_euid": "exec-1:run-a",
        "owy_execution_id": "exec-1",
        "bloom_run_euid": "BLOOM-RUN-1",
        "run_metadata": {"instrument_id": "LH01106"},
    }

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/dewey/run-directory-analysis-triggers",
            headers={"X-API-Key": "ursa-write-token", "Idempotency-Key": "idem-run-dir-1"},
            json=body,
        )
        assert created.status_code == 202, created.text
        payload = created.json()
        assert payload["trigger_euid"].startswith("URDT-")
        assert payload["status"] == "QUEUED"
        assert payload["bloom_run_euid"] == "BLOOM-RUN-1"
        assert payload["analysis_job_euids"] == ["AJ-1"]
        assert payload["analysis_jobs"][0]["command_id"] == "illumina_run_qc"
        assert payload["analysis_jobs"][0]["status"] == "DEFINED"
        assert payload["command_ids"] == ["illumina_run_qc"]
        assert payload["ursa_external_objects"][0]["external_system"] == "bloom"
        assert payload["ursa_external_objects"][0]["external_object_id"] == "BLOOM-RUN-1"
        assert len(payload["dewey_external_relations"]) == 3

        replay = client.post(
            "/api/v1/dewey/run-directory-analysis-triggers",
            headers={"X-API-Key": "ursa-write-token", "Idempotency-Key": "idem-run-dir-1"},
            json=body,
        )
        assert replay.status_code == 202, replay.text
        assert replay.json()["trigger_euid"] == payload["trigger_euid"]
        assert replay.json()["ursa_external_objects"][0]["external_object_id"] == "BLOOM-RUN-1"

    assert bloom.run_directory_calls == []
    assert len(resources.worksets) == 1
    manifest = next(iter(resources.manifests.values()))
    run_context = manifest.metadata["run_context_manifest"]
    assert run_context["filename"] == "config/runs.tsv"
    assert "RUNID\tPLATFORM\tRUN_DIR" in run_context["content"]
    assert (
        "run-a\tILMN\ts3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/"
        in run_context["content"]
    )
    assert resources.analysis_jobs["AJ-1"].request["run_directory_trigger"]["bloom_run_euid"] == (
        "BLOOM-RUN-1"
    )
    assert resources.analysis_jobs["AJ-1"].request["executing_entity"] is None
    assert resources.analysis_jobs["AJ-1"].request["destination"] is None
    assert orchestrator.start_calls == [payload["trigger_euid"]]
    assert len(resources.external_objects) == 1
    assert len(dewey.external_objects) == 3
    assert len(dewey.external_relations) == 3


def test_run_directory_trigger_get_refreshes_job_status_and_generic_readback(monkeypatch) -> None:
    resources = _MemoryResourceStore()
    app = _app(
        monkeypatch,
        resource_store=resources,
        dewey_client=_DummyDeweyClient(),
        run_directory_orchestrator=_DummyRunDirectoryOrchestrator(),
    )
    body = {
        "dewey_run_artifact_euid": "AT-RUN-1",
        "run_storage_uri": "s3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/",
        "run_folder_name": "run-a",
        "platform": "ILMN",
        "command_ids": ["illumina_run_qc"],
        "producer_system": "offwithyou",
        "producer_object_euid": "exec-1:run-a",
        "owy_execution_id": "exec-1",
    }

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/dewey/run-directory-analysis-triggers",
            headers={
                "X-API-Key": "ursa-write-token",
                "Idempotency-Key": "idem-run-dir-readback",
            },
            json=body,
        )
        assert created.status_code == 202, created.text
        trigger_euid = created.json()["trigger_euid"]
        job_euid = created.json()["analysis_job_euids"][0]
        analysis_experiment_euid = created.json()["analysis_jobs"][0][
            "analysis_experiment_euid"
        ]

        resources.update_analysis_job_status(
            job_euid=job_euid,
            state="COMPLETED",
            created_by=OWNER_USER_ID,
            started_at="2026-05-27T00:03:00Z",
            completed_at="2026-05-27T00:04:00Z",
            return_code=0,
            output_summary="dy-r help completed",
            launch={"session_name": "run-a-help", "exit_code": 0},
        )

        direct = client.get(
            f"/api/v1/dewey/run-directory-analysis-triggers/{trigger_euid}",
            headers={"X-API-Key": "ursa-write-token"},
        )
        generic = client.get(
            f"/api/v1/dewey/run-analysis-triggers/{trigger_euid}",
            headers={"X-API-Key": "ursa-write-token"},
        )

    assert analysis_experiment_euid.startswith("URXP-")
    assert direct.status_code == 200, direct.text
    assert direct.json()["status"] == "COMPLETED"
    assert direct.json()["analysis_jobs"][0]["analysis_job_euid"] == job_euid
    assert direct.json()["analysis_jobs"][0]["status"] == "COMPLETED"
    assert direct.json()["analysis_jobs"][0]["analysis_experiment_euid"] == (
        analysis_experiment_euid
    )
    assert generic.status_code == 200, generic.text
    assert generic.json()["trigger_euid"] == trigger_euid
    assert generic.json()["status"] == "COMPLETED"


def test_run_directory_trigger_replay_allows_new_owy_attempt_fields(monkeypatch) -> None:
    resources = _MemoryResourceStore()
    dewey = _DummyDeweyClient()
    app = _app(monkeypatch, resource_store=resources, dewey_client=dewey)
    body = {
        "dewey_run_artifact_euid": "AT-RUN-1",
        "run_storage_uri": "s3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/",
        "run_folder_name": "run-a",
        "platform": "ILMN",
        "command_ids": ["illumina_run_qc"],
        "producer_system": "offwithyou",
        "producer_object_euid": "exec-1:run-a",
        "owy_execution_id": "exec-1",
        "bloom_run_euid": "BLOOM-RUN-1",
        "run_metadata": {"execution_id": "exec-1", "instrument_id": "LH01106"},
    }

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/dewey/run-directory-analysis-triggers",
            headers={
                "X-API-Key": "ursa-write-token",
                "Idempotency-Key": "idem-run-dir-attempt",
            },
            json=body,
        )
        assert created.status_code == 202, created.text
        original = created.json()

        record = resources.triggers_by_idempotency["idem-run-dir-attempt"]
        resources.triggers_by_idempotency["idem-run-dir-attempt"] = replace(
            record,
            fingerprint="stored-before-stable-owy-attempt-fingerprint",
        )

        replay_body = {
            **body,
            "producer_object_euid": "exec-2:run-a",
            "owy_execution_id": "exec-2",
            "run_metadata": {"execution_id": "exec-2", "instrument_id": "LH01106"},
        }
        replay = client.post(
            "/api/v1/dewey/run-directory-analysis-triggers",
            headers={
                "X-API-Key": "ursa-write-token",
                "Idempotency-Key": "idem-run-dir-attempt",
            },
            json=replay_body,
        )
        assert replay.status_code == 202, replay.text
        assert replay.json()["trigger_euid"] == original["trigger_euid"]

        changed = client.post(
            "/api/v1/dewey/run-directory-analysis-triggers",
            headers={
                "X-API-Key": "ursa-write-token",
                "Idempotency-Key": "idem-run-dir-attempt",
            },
            json={**replay_body, "command_ids": ["illumina_run_qc_bclconvert"]},
        )
        assert changed.status_code == 409
        assert "Idempotency-Key reuse with different request payload" in changed.text

    assert len(resources.worksets) == 1
    assert len(resources.analysis_jobs) == 1


def test_run_directory_trigger_replay_relaunches_prelaunch_failure(monkeypatch) -> None:
    resources = _MemoryResourceStore()
    manager = _DummyAnalysisJobManager(resources, terminal_state="PRELAUNCH_FAILED")
    dewey = _DummyDeweyClient()
    orchestrator = _DummyRunDirectoryOrchestrator()
    app = _app(
        monkeypatch,
        resource_store=resources,
        analysis_job_manager=manager,
        dewey_client=dewey,
        run_directory_orchestrator=orchestrator,
    )
    body = {
        "dewey_run_artifact_euid": "AT-RUN-1",
        "run_storage_uri": "s3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/",
        "run_folder_name": "run-a",
        "platform": "ILMN",
        "command_ids": ["illumina_run_qc"],
        "producer_system": "offwithyou",
        "producer_object_euid": "exec-1:run-a",
        "owy_execution_id": "exec-1",
        "bloom_run_euid": "BLOOM-RUN-1",
    }

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/dewey/run-directory-analysis-triggers",
            headers={
                "X-API-Key": "ursa-write-token",
                "Idempotency-Key": "idem-run-dir-prelaunch-failure",
            },
            json=body,
        )
        assert created.status_code == 202, created.text
        assert created.json()["status"] == "QUEUED"
        assert resources.analysis_jobs["AJ-1"].state == "DEFINED"
        assert resources.analysis_jobs["AJ-1"].request["destination"] is None

        stale_job = resources.analysis_jobs["AJ-1"]
        resources.analysis_jobs["AJ-1"] = replace(
            stale_job,
            state="FAILED",
            error="AnalysisIdentityError: executing_entity must be path-safe",
            launch={},
            request={
                **stale_job.request,
                "destination": (
                    "s3://bucket/derived/lsmc/ssf-hq/LH01106/2026/run-a/01-illumina_run_qc/"
                ),
            },
        )

        replay = client.post(
            "/api/v1/dewey/run-directory-analysis-triggers",
            headers={
                "X-API-Key": "ursa-write-token",
                "Idempotency-Key": "idem-run-dir-prelaunch-failure",
            },
            json={**body, "producer_object_euid": "exec-2:run-a", "owy_execution_id": "exec-2"},
        )

    assert replay.status_code == 202, replay.text
    payload = replay.json()
    assert payload["status"] == "QUEUED"
    assert payload["analysis_jobs"][0]["status"] == "DEFINED"
    assert payload["analysis_job_euids"] == ["AJ-1"]
    assert manager.launch_calls == []
    assert resources.triggers_by_idempotency["idem-run-dir-prelaunch-failure"].status == "QUEUED"
    assert resources.analysis_jobs["AJ-1"].state == "DEFINED"
    assert resources.analysis_jobs["AJ-1"].request["destination"] == (
        "s3://bucket/derived/lsmc/ssf-hq/LH01106/2026/run-a/01-illumina_run_qc/"
    )
    assert orchestrator.start_calls == [payload["trigger_euid"], payload["trigger_euid"]]
    assert len(resources.worksets) == 1
    assert len(resources.analysis_jobs) == 1


def test_run_directory_trigger_replay_relaunches_queued_defined_without_live_worker(
    monkeypatch,
) -> None:
    resources = _MemoryResourceStore()
    dewey = _DummyDeweyClient()
    orchestrator = _DummyRunDirectoryOrchestrator()
    app = _app(
        monkeypatch,
        resource_store=resources,
        dewey_client=dewey,
        run_directory_orchestrator=orchestrator,
    )
    body = {
        "dewey_run_artifact_euid": "AT-RUN-1",
        "run_storage_uri": "s3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/",
        "run_folder_name": "run-a",
        "platform": "ILMN",
        "command_ids": ["illumina_run_qc"],
        "producer_system": "offwithyou",
        "producer_object_euid": "exec-1:run-a",
        "owy_execution_id": "exec-1",
        "bloom_run_euid": "BLOOM-RUN-1",
    }

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/dewey/run-directory-analysis-triggers",
            headers={
                "X-API-Key": "ursa-write-token",
                "Idempotency-Key": "idem-run-dir-stale-queued",
            },
            json=body,
        )
        assert created.status_code == 202, created.text
        first_payload = created.json()
        record = resources.triggers_by_idempotency["idem-run-dir-stale-queued"]
        resources.triggers_by_idempotency["idem-run-dir-stale-queued"] = replace(
            record,
            response={key: value for key, value in record.response.items() if key != "worker"},
        )

        replay = client.post(
            "/api/v1/dewey/run-directory-analysis-triggers",
            headers={
                "X-API-Key": "ursa-write-token",
                "Idempotency-Key": "idem-run-dir-stale-queued",
            },
            json=body,
        )

    assert replay.status_code == 202, replay.text
    assert replay.json()["status"] == "QUEUED"
    assert replay.json()["trigger_euid"] == first_payload["trigger_euid"]
    assert orchestrator.start_calls == [first_payload["trigger_euid"], first_payload["trigger_euid"]]
    assert len(resources.worksets) == 1
    assert len(resources.analysis_jobs) == 1


def test_run_directory_trigger_replay_relaunches_failed_workflow_job(monkeypatch) -> None:
    resources = _MemoryResourceStore()
    dewey = _DummyDeweyClient()
    orchestrator = _DummyRunDirectoryOrchestrator()
    app = _app(
        monkeypatch,
        resource_store=resources,
        dewey_client=dewey,
        run_directory_orchestrator=orchestrator,
    )
    body = {
        "dewey_run_artifact_euid": "AT-RUN-1",
        "run_storage_uri": "s3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/",
        "run_folder_name": "run-a",
        "platform": "ILMN",
        "command_ids": ["illumina_run_qc"],
        "producer_system": "offwithyou",
        "producer_object_euid": "exec-1:run-a",
        "owy_execution_id": "exec-1",
        "bloom_run_euid": "BLOOM-RUN-1",
    }

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/dewey/run-directory-analysis-triggers",
            headers={
                "X-API-Key": "ursa-write-token",
                "Idempotency-Key": "idem-run-dir-failed-workflow",
            },
            json=body,
        )
        assert created.status_code == 202, created.text
        first_payload = created.json()
        record = resources.triggers_by_idempotency["idem-run-dir-failed-workflow"]
        job = resources.analysis_jobs[first_payload["analysis_job_euids"][0]]
        resources.analysis_jobs[job.job_euid] = replace(
            job,
            state="FAILED",
            error="Workflow status: FAILED",
            return_code=2,
            launch={
                "session_name": "run-a-illumina_run_qc",
                "run_dir": "/fsx/analysis/run-a",
                "repo_path": "/fsx/analysis/run-a/daylily-omics-analysis",
            },
        )
        resources.triggers_by_idempotency["idem-run-dir-failed-workflow"] = replace(
            record,
            status="FAILED",
            error="RuntimeError: Workflow status: FAILED",
            response={key: value for key, value in record.response.items() if key != "worker"},
        )

        replay = client.post(
            "/api/v1/dewey/run-directory-analysis-triggers",
            headers={
                "X-API-Key": "ursa-write-token",
                "Idempotency-Key": "idem-run-dir-failed-workflow",
            },
            json=body,
        )

    assert replay.status_code == 202, replay.text
    payload = replay.json()
    assert payload["status"] == "QUEUED"
    assert payload["trigger_euid"] == first_payload["trigger_euid"]
    assert payload["analysis_job_euids"] == first_payload["analysis_job_euids"]
    assert resources.analysis_jobs[job.job_euid].state == "DEFINED"
    assert resources.analysis_jobs[job.job_euid].request["replace_existing_analysis_dir"] is True
    assert resources.triggers_by_idempotency["idem-run-dir-failed-workflow"].status == "QUEUED"
    assert orchestrator.start_calls == [first_payload["trigger_euid"], first_payload["trigger_euid"]]
    assert len(resources.worksets) == 1
    assert len(resources.analysis_jobs) == 1


def test_run_directory_trigger_accepts_owy_bclconvert_command(monkeypatch) -> None:
    resources = _MemoryResourceStore()
    dewey = _DummyDeweyClient()
    app = _app(monkeypatch, resource_store=resources, dewey_client=dewey)
    body = {
        "dewey_run_artifact_euid": "AT-RUN-1",
        "run_storage_uri": "s3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/",
        "run_folder_name": "run-a",
        "platform": "ILMN",
        "command_ids": ["illumina_run_qc_bclconvert"],
        "producer_system": "offwithyou",
        "producer_object_euid": "exec-1:run-a",
        "owy_execution_id": "exec-1",
    }

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/dewey/run-directory-analysis-triggers",
            headers={"X-API-Key": "ursa-write-token", "Idempotency-Key": "idem-run-dir-bclconvert"},
            json=body,
        )

    assert created.status_code == 202, created.text
    payload = created.json()
    assert payload["command_ids"] == ["illumina_run_qc_bclconvert"]
    assert payload["analysis_jobs"][0]["command_id"] == "illumina_run_qc_bclconvert"
    assert resources.analysis_jobs["AJ-1"].request["analysis_command_id"] == "illumina_run_qc_bclconvert"
    assert resources.analysis_jobs["AJ-1"].request["executing_entity"] is None
    assert resources.analysis_jobs["AJ-1"].request["destination"] is None


def test_run_directory_trigger_does_not_require_default_cluster_name(monkeypatch) -> None:
    settings = _settings()
    app = _app(monkeypatch, dewey_client=_DummyDeweyClient(), settings=settings)
    body = {
        "dewey_run_artifact_euid": "AT-RUN-1",
        "run_storage_uri": "s3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/",
        "run_folder_name": "run-a",
        "platform": "ILMN",
        "command_ids": ["illumina_run_qc_bclconvert"],
        "producer_system": "offwithyou",
        "producer_object_euid": "exec-1:run-a",
        "owy_execution_id": "exec-1",
    }

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/dewey/run-directory-analysis-triggers",
            headers={
                "X-API-Key": "ursa-write-token",
                "Idempotency-Key": "idem-run-dir-no-default-cluster",
            },
            json=body,
        )

    assert created.status_code == 202, created.text
    assert created.json()["status"] == "QUEUED"


def test_run_directory_trigger_accepts_exact_owy_handoff_with_bloom_euid(monkeypatch) -> None:
    run_storage_uri = (
        "s3://lsmc-ssf-sequencing-data/basecalls/lsmc/ssf-hq/lh01121/2026/"
        "20260520_LH01121_0001_A23WW7FLT4/"
    )
    resources = _MemoryResourceStore()
    dewey = _DummyDeweyClient(storage_uri=run_storage_uri)
    settings = _settings()
    settings.ursa_run_directory_analysis_destination_s3_uri = (
        "s3://lsmc-ssf-sequencing-data/derived/"
    )
    app = _app(
        monkeypatch,
        resource_store=resources,
        dewey_client=dewey,
        settings=settings,
    )
    body = {
        "run_folder_name": "20260520_LH01121_0001_A23WW7FLT4",
        "platform": "ILMN",
        "run_storage_uri": run_storage_uri,
        "dewey_run_artifact_euid": "M-DGX-9SD7",
        "bloom_run_euid": "M-BRM-4Z",
        "command_ids": ["illumina_run_qc_bclconvert"],
        "producer_system": "offwithyou",
        "producer_object_euid": (
            "dc5f4e8c-9e0f-48dd-810b-e0b66a3f32b9:"
            "20260520_LH01121_0001_A23WW7FLT4"
        ),
        "owy_execution_id": "dc5f4e8c-9e0f-48dd-810b-e0b66a3f32b9",
        "dry_run": False,
    }

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/dewey/run-directory-analysis-triggers",
            headers={
                "X-API-Key": "ursa-write-token",
                "Idempotency-Key": "owy-dc5f4e8c-9e0f-48dd-810b-e0b66a3f32b9",
            },
            json=body,
        )

    assert created.status_code == 202, created.text
    payload = created.json()
    assert payload["run_folder_name"] == "20260520_LH01121_0001_A23WW7FLT4"
    assert payload["bloom_run_euid"] == "M-BRM-4Z"
    assert payload["dewey_run_artifact_euid"] == "M-DGX-9SD7"
    assert payload["command_ids"] == ["illumina_run_qc_bclconvert"]
    assert payload["analysis_jobs"][0]["command_id"] == "illumina_run_qc_bclconvert"
    assert payload["request"]["owy_execution_id"] == "dc5f4e8c-9e0f-48dd-810b-e0b66a3f32b9"
    assert resources.analysis_jobs["AJ-1"].request["executing_entity"] is None
    assert resources.analysis_jobs["AJ-1"].request["destination"] is None
    assert payload["ursa_external_objects"][0]["external_object_id"] == "M-BRM-4Z"
    assert resources.external_object_parent_lookups == [
        {
            "parent_euid": payload["trigger_euid"],
            "parent_external_id_key": "trigger_euid",
        }
    ]


def test_run_directory_trigger_rejects_bad_run_storage_uri_without_500(monkeypatch) -> None:
    app = _app(monkeypatch, dewey_client=_DummyDeweyClient())
    body = {
        "run_folder_name": "20260520_LH01121_0001_A23WW7FLT4",
        "platform": "ILMN",
        "run_storage_uri": "https://not-s3.example/run/",
        "dewey_run_artifact_euid": "M-DGX-9SD7",
        "bloom_run_euid": "M-BRM-4Z",
        "command_ids": ["illumina_run_qc_bclconvert"],
        "producer_system": "offwithyou",
        "producer_object_euid": "exec-1:20260520_LH01121_0001_A23WW7FLT4",
        "owy_execution_id": "exec-1",
    }

    with TestClient(app) as client:
        rejected = client.post(
            "/api/v1/dewey/run-directory-analysis-triggers",
            headers={"X-API-Key": "ursa-write-token", "Idempotency-Key": "idem-bad-s3"},
            json=body,
        )

    assert rejected.status_code == 400
    assert "S3 URI must be an absolute s3:// URI" in rejected.text
    assert "Internal server error" not in rejected.text


def test_run_directory_trigger_persistence_failure_is_explicit_503(monkeypatch) -> None:
    resources = _MissingParentResourceStore()
    dewey = _DummyDeweyClient()
    app = _app(monkeypatch, resource_store=resources, dewey_client=dewey)
    body = {
        "dewey_run_artifact_euid": "AT-RUN-1",
        "run_storage_uri": "s3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/",
        "run_folder_name": "run-a",
        "platform": "ILMN",
        "command_ids": ["illumina_run_qc_bclconvert"],
        "producer_system": "offwithyou",
        "producer_object_euid": "exec-1:run-a",
        "owy_execution_id": "exec-1",
        "bloom_run_euid": "BLOOM-RUN-1",
    }

    with TestClient(app) as client:
        rejected = client.post(
            "/api/v1/dewey/run-directory-analysis-triggers",
            headers={"X-API-Key": "ursa-write-token", "Idempotency-Key": "idem-parent-missing"},
            json=body,
        )

    assert rejected.status_code == 503
    assert "Ursa run-directory trigger persistence failed" in rejected.text
    assert "Internal server error" not in rejected.text


def test_run_directory_trigger_accepts_null_bloom_run(monkeypatch) -> None:
    resources = _MemoryResourceStore()
    dewey = _DummyDeweyClient()
    bloom = _DummyBloomClient()
    app = _app(monkeypatch, resource_store=resources, dewey_client=dewey, bloom_client=bloom)
    body = {
        "dewey_run_artifact_euid": "AT-RUN-1",
        "run_storage_uri": "s3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/",
        "run_folder_name": "run-a",
        "platform": "ILMN",
        "command_ids": ["illumina_run_qc"],
        "bloom_run_euid": None,
        "producer_system": "offwithyou",
        "producer_object_euid": "exec-1:run-a",
        "owy_execution_id": "exec-1",
    }

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/dewey/run-directory-analysis-triggers",
            headers={"X-API-Key": "ursa-write-token", "Idempotency-Key": "idem-run-dir-null-bloom"},
            json=body,
        )

    assert created.status_code == 202, created.text
    payload = created.json()
    assert payload["bloom_run_euid"] is None
    assert payload["ursa_external_objects"] == []
    assert len(payload["dewey_external_relations"]) == 2
    assert bloom.run_directory_calls == []
    assert resources.external_objects == []
    assert len(dewey.external_objects) == 2
    assert len(dewey.external_relations) == 2


def test_run_directory_trigger_rejects_non_run_analysis_command(monkeypatch) -> None:
    app = _app(monkeypatch, dewey_client=_DummyDeweyClient())
    body = {
        "dewey_run_artifact_euid": "AT-RUN-1",
        "run_storage_uri": "s3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/",
        "run_folder_name": "run-a",
        "platform": "ILMN",
        "command_ids": ["illumina_snv_alignstats_relatedness_vep_multiqc"],
        "producer_system": "offwithyou",
        "producer_object_euid": "exec-1:run-a",
        "owy_execution_id": "exec-1",
    }

    with TestClient(app) as client:
        rejected = client.post(
            "/api/v1/dewey/run-directory-analysis-triggers",
            headers={"X-API-Key": "ursa-write-token", "Idempotency-Key": "idem-run-dir-bad"},
            json=body,
        )
    assert rejected.status_code == 400
    assert "not a run_analysis command" in rejected.text


def test_run_directory_orchestrator_selects_cluster_launches_exports_and_writes_sidecars(
    tmp_path, monkeypatch
) -> None:
    import daylib_ursa.run_directory_orchestrator as orchestrator_module

    monkeypatch.setattr(
        "daylib_ursa.analysis_jobs.get_analysis_command",
        lambda _command_id, optional_features=None: _FakeRunAnalysisCommand(),
    )
    sidecars: list[dict] = []
    lifecycle_events: list[str] = []

    def fake_write_sidecar(**kwargs):
        sidecars.append(dict(kwargs))
        lifecycle_events.append(f"sidecar:{kwargs['payload']['state']}")

    monkeypatch.setattr(
        orchestrator_module,
        "_write_sidecar_cli",
        fake_write_sidecar,
    )
    monkeypatch.setenv("DEWEY_TOKEN", "token-1")
    resources = _MemoryResourceStore()
    workset = resources.create_workset(
        name="Run directory run-a",
        tenant_id=TENANT_ID,
        owner_user_id=OWNER_USER_ID,
        artifact_set_euids=[],
        metadata={},
    )
    manifest = resources.create_manifest(
        workset_euid=workset.workset_euid,
        name="Run directory run-a run context",
        artifact_set_euid=None,
        artifact_euids=["AT-RUN-1"],
        input_references=[],
        metadata={
            "run_context_manifest": {
                "filename": "config/runs.tsv",
                "content": (
                    "RUNID\tPLATFORM\tRUN_DIR\tOUTPUT_ROOT\n"
                    "run-a\tILMN\ts3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/"
                    "\ts3://old-output/\n"
                ),
            }
        },
    )
    job = resources.create_analysis_job(
        job_name="run-a:01:illumina_run_qc",
        workset_euid=workset.workset_euid,
        manifest_euid=manifest.manifest_euid,
        cluster_name="",
        region="us-west-2",
        tenant_id=TENANT_ID,
        owner_user_id=OWNER_USER_ID,
        request={
            "analysis_command_id": "illumina_run_qc",
            "destination": None,
            "export_trigger": "on-success",
            "executing_entity": None,
            "reference_s3_uri": "s3://refs/hg38/",
            "session_name": "run-a-illumina_run_qc",
            "project": "daylily",
            "aws_profile": "lsmc",
            "dry_run": False,
            "stage_target": "/staging/run-directories",
            "run_directory_trigger": {
                "trigger_euid": "URDT-1",
                "dewey_run_artifact_euid": "AT-RUN-1",
                "run_storage_uri": "s3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/",
                "bloom_run_euid": "BLOOM-RUN-1",
                "pipeline_order": 1,
                "predecessor_analysis_job_euid": None,
            },
        },
    )
    resources.create_dewey_run_trigger(
        trigger_euid="URDT-1",
        idempotency_key="idem-1",
        fingerprint="fp-1",
        status="QUEUED",
        command_id="illumina_run_qc",
        request={
            "dewey_run_artifact_euid": "AT-RUN-1",
            "run_storage_uri": "s3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/",
            "run_folder_name": "run-a",
            "platform": "ILMN",
            "command_ids": ["illumina_run_qc"],
            "bloom_run_euid": "BLOOM-RUN-1",
            "producer_system": "offwithyou",
            "producer_object_euid": "exec-1:run-a",
            "owy_execution_id": "exec-1",
        },
        response={
            "trigger_euid": "URDT-1",
            "status": "QUEUED",
            "idempotency_key": "idem-1",
            "dewey_run_artifact_euid": "AT-RUN-1",
            "run_storage_uri": "s3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/",
            "run_folder_name": "run-a",
            "platform": "ILMN",
            "command_ids": ["illumina_run_qc"],
            "bloom_run_euid": "BLOOM-RUN-1",
            "workset_euid": workset.workset_euid,
            "manifest_euid": manifest.manifest_euid,
            "analysis_job_euids": [job.job_euid],
            "analysis_jobs": [
                {
                    "analysis_job_euid": job.job_euid,
                    "command_id": "illumina_run_qc",
                    "status": "DEFINED",
                    "pipeline_order": 1,
                }
            ],
            "ursa_external_objects": [],
            "dewey_external_relations": [],
            "request": {},
            "created_at": "2026-05-27T00:00:00Z",
            "updated_at": "2026-05-27T00:00:00Z",
        },
        analysis_job_euid=job.job_euid,
    )
    captured: dict[str, object] = {"deleted_mounts": []}

    class FakeDayEcClient:
        aws_profile = "lsmc"

        def cluster_list(self, *, region, details):  # noqa: ANN001
            captured["cluster_list"] = {"region": region, "details": details}
            return {
                "clusters": [
                    {
                        "name": "cluster-a",
                        "region": "us-west-2",
                        "status": "CREATE_COMPLETE",
                        "headnode_configured": True,
                        "details": {"computeFleetStatus": "RUNNING"},
                    }
                ]
            }

        def mounts_describe(self, **kwargs):  # noqa: ANN001
            captured["mounts_describe"] = dict(kwargs)
            raise RuntimeError("Run mount not found: run-a")

        def mounts_create(self, **kwargs):  # noqa: ANN001
            captured["mounts_create"] = dict(kwargs)
            return {"status": "created"}

        def mounts_verify(self, **kwargs):  # noqa: ANN001
            captured["mounts_verify"] = dict(kwargs)
            return {"status": "verified"}

        def mounts_delete(self, **kwargs):  # noqa: ANN001
            captured["deleted_mounts"].append(dict(kwargs))
            lifecycle_events.append("mount_delete")
            return {"status": "deleted"}

        def workflow_launch(self, argv, *, cwd):  # noqa: ANN001
            captured["argv"] = list(argv)
            captured["cwd"] = cwd
            return subprocess.CompletedProcess(
                args=list(argv),
                returncode=0,
                stdout=(
                    "__DAYLILY_SESSION__=run-a-illumina-run-qc\n"
                    "__DAYLILY_RUN_DIR__=/fsx/analysis/run-a\n"
                    "__DAYLILY_REPO_PATH__=/fsx/repos/daylily-omics-analysis\n"
                ),
                stderr="",
            )

        def workflow_status(self, *, session_name, region, cluster_name):  # noqa: ANN001
            captured["workflow_status"] = {
                "session_name": session_name,
                "region": region,
                "cluster_name": cluster_name,
            }
            return {
                "session_name": session_name,
                "exit_code": 0,
                "completed_at": "2026-05-27T00:10:00Z",
            }

    settings = _settings()
    settings.dewey_base_url = "https://dewey.example"
    settings.ursa_run_directory_analysis_dewey_token_env = "DEWEY_TOKEN"
    orchestrator = RunDirectoryOrchestrator(
        resource_store=resources,
        client=FakeDayEcClient(),
        settings=settings,
        workspace_root=tmp_path,
    )

    orchestrator.run_trigger("URDT-1", poll_interval_seconds=1)

    updated = resources.analysis_jobs[job.job_euid]
    expected_destination = (
        "s3://bucket/derived/lsmc/ssf-hq/LH01106/2026/run-a/"
        "analysis_results/cluster-a/AJ-1/"
    )
    assert updated.cluster_name == "cluster-a"
    assert updated.region == "us-west-2"
    assert updated.request["analysis_id"] == "AJ-1"
    assert updated.request["executing_entity"] == "cluster-a"
    assert updated.request["destination"] == expected_destination
    assert updated.request["session_name"] == "ursa-AJ-1-illumina_run_qc"
    assert updated.request["delete_on_export_success"] is True
    assert updated.request["artifact_registration_command_id"] == "illumina_run_qc"
    assert updated.request["dewey_url"] == "https://dewey.example"
    assert updated.request["dewey_token_env"] == "DEWEY_TOKEN"
    assert updated.request["dewey_analysis_dir_external_object_id"] == (
        expected_destination + "daylily-omics-analysis/"
    )
    assert updated.request["dewey_run_artifact_euid"] == "AT-RUN-1"
    assert updated.request["dewey_ursa_analysis_euid"] == "AJ-1"
    argv = captured["argv"]
    assert "--analysis-id" in argv and "AJ-1" in argv
    assert "--executing-entity" in argv and "cluster-a" in argv
    assert "--session-name" in argv and "ursa-AJ-1-illumina_run_qc" in argv
    assert "--replace-existing-analysis-dir" not in argv
    assert "--delete-on-export-success" in argv
    assert "--dewey-analysis-dir-external-object-id" in argv
    assert expected_destination + "daylily-omics-analysis/" in argv
    assert "--dewey-run-artifact-euid" in argv and "AT-RUN-1" in argv
    assert "--dewey-ursa-analysis-euid" in argv and "AJ-1" in argv
    assert sidecars[0]["payload"]["state"] == "inprog"
    assert sidecars[-1]["payload"]["state"] == "complete"
    assert lifecycle_events == ["sidecar:inprog", "mount_delete", "sidecar:complete"]
    assert captured["mounts_describe"] == {
        "cluster_name": "cluster-a",
        "region": "us-west-2",
        "mount_id": "run-a",
    }
    assert resources.triggers_by_euid["URDT-1"].status == "COMPLETED"
    assert captured["deleted_mounts"] == [
        {"cluster_name": "cluster-a", "region": "us-west-2", "mount_id": "run-a"}
    ]


def test_run_directory_orchestrator_creates_cluster_when_no_match(tmp_path) -> None:
    calls: list[dict] = []

    class FakeDayEcClient:
        def run(self, args, *, cwd):  # noqa: ANN001
            calls.append({"method": "run", "args": list(args), "cwd": cwd})
            return subprocess.CompletedProcess(args=list(args), returncode=0, stdout="", stderr="")

        def cluster_wait(self, **kwargs):  # noqa: ANN001
            calls.append({"method": "cluster_wait", **dict(kwargs)})
            return {
                "cluster_name": kwargs["cluster_name"],
                "status": kwargs.get("status", "CREATE_COMPLETE"),
            }

    policy = RunDirectoryPolicy(
        tenant_id=str(TENANT_ID),
        owner_user_id=OWNER_USER_ID,
        regions=("us-west-2",),
        reference_s3_uri="s3://refs/hg38/",
        stage_target="/staging/run-directories",
        destination_s3_uri="s3://bucket/derived/",
        project="daylily",
        aws_profile="lsmc",
        dewey_url="https://dewey.example",
        dewey_token_env="DEWEY_TOKEN",
        cluster_create_name="owy-auto-1",
        cluster_create_region_az="us-west-2d",
        cluster_create_config_path="/tmp/owy-auto-1.yaml",
        cluster_create_timeout_seconds=1200,
        cluster_create_poll_interval_seconds=15,
    )
    orchestrator = RunDirectoryOrchestrator(
        resource_store=_MemoryResourceStore(),
        client=FakeDayEcClient(),
        settings=_settings(),
        workspace_root=tmp_path,
    )

    selected = orchestrator.create_and_wait_cluster(policy)

    assert selected.name == "owy-auto-1"
    assert selected.region == "us-west-2"
    assert calls[0]["args"] == [
        "preflight",
        "--region-az",
        "us-west-2d",
        "--config",
        "/tmp/owy-auto-1.yaml",
        "--non-interactive",
        "--profile",
        "lsmc",
    ]
    assert calls[1]["args"] == [
        "create",
        "--region-az",
        "us-west-2d",
        "--config",
        "/tmp/owy-auto-1.yaml",
        "--non-interactive",
        "--profile",
        "lsmc",
    ]
    assert calls[2] == {
        "method": "cluster_wait",
        "cluster_name": "owy-auto-1",
        "region": "us-west-2",
        "timeout": 1200,
        "poll_interval": 15,
    }


def test_run_directory_orchestrator_reuses_matching_available_mount(tmp_path) -> None:
    class FakeDayEcClient:
        def __init__(self) -> None:
            self.create_called = False

        def mounts_describe(self, **kwargs):  # noqa: ANN001
            assert kwargs == {
                "cluster_name": "cluster-a",
                "region": "us-west-2",
                "mount_id": "run-a",
            }
            return {
                "association_id": "dra-existing",
                "cluster_name": "cluster-a",
                "region": "us-west-2",
                "mount_id": "run-a",
                "lifecycle": "AVAILABLE",
                "source_s3_uri": "s3://bucket/basecalls/run-a/",
            }

        def mounts_create(self, **kwargs):  # noqa: ANN001
            self.create_called = True
            raise AssertionError("matching available mount must not be recreated")

    client = FakeDayEcClient()
    orchestrator = RunDirectoryOrchestrator(
        resource_store=_MemoryResourceStore(),
        client=client,
        settings=_settings(),
        workspace_root=tmp_path,
    )

    record = orchestrator.ensure_run_mount(
        source_s3_uri="s3://bucket/basecalls/run-a/",
        selected=SelectedCluster(name="cluster-a", region="us-west-2"),
        mount_id="run-a",
        run_id="run-a",
        platform="ILMN",
    )

    assert record["association_id"] == "dra-existing"
    assert client.create_called is False


def test_run_directory_analysis_job_launch_uses_run_context_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "daylib_ursa.analysis_jobs.get_analysis_command",
        lambda _command_id, optional_features=None: _FakeRunAnalysisCommand(),
    )
    resources = _MemoryResourceStore()
    workset = resources.create_workset(
        name="Run directory run-a",
        tenant_id=TENANT_ID,
        owner_user_id=OWNER_USER_ID,
        artifact_set_euids=[],
        metadata={},
    )
    manifest = resources.create_manifest(
        workset_euid=workset.workset_euid,
        name="Run directory run-a run context",
        artifact_set_euid=None,
        artifact_euids=["AT-RUN-1"],
        input_references=[],
        metadata={
            "run_context_manifest": {
                "filename": "config/runs.tsv",
                "content": (
                    "RUNID\tPLATFORM\tRUN_DIR\tOUTPUT_ROOT\n"
                    "run-a\tILMN\ts3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/"
                    "\ts3://old-output/\n"
                ),
            }
        },
    )
    job = resources.create_analysis_job(
        job_name="run-a:01:illumina_run_qc",
        workset_euid=workset.workset_euid,
        manifest_euid=manifest.manifest_euid,
        cluster_name="cluster-1",
        region="us-west-2",
        tenant_id=TENANT_ID,
        owner_user_id=OWNER_USER_ID,
        request={
            "analysis_command_id": "illumina_run_qc",
            "destination": "s3://analysis-results/run-a/01-illumina_run_qc/",
            "export_trigger": "on-success",
            "session_name": "run-a-illumina_run_qc",
            "project": "daylily",
            "aws_profile": "lsmc",
            "replace_existing_analysis_dir": True,
            "run_directory_trigger": {"trigger_euid": "URDT-1"},
        },
    )
    captured: dict[str, list[str]] = {}

    class FakeDayEcClient:
        aws_profile = "lsmc"

        def workflow_launch(self, argv, *, cwd):  # noqa: ANN001
            captured["argv"] = list(argv)
            return subprocess.CompletedProcess(
                args=list(argv),
                returncode=0,
                stdout=(
                    "__DAYLILY_SESSION__=run-a-illumina-run-qc\n"
                    "__DAYLILY_RUN_DIR__=/fsx/analysis/run-a\n"
                    "__DAYLILY_REPO_PATH__=/fsx/repos/daylily-omics-analysis\n"
                ),
                stderr="",
            )

    manager = AnalysisJobManager(
        resource_store=resources,
        client=FakeDayEcClient(),
        workspace_root=tmp_path,
    )

    launched = manager.launch_job(job.job_euid, actor_user_id=OWNER_USER_ID)

    assert launched.state == "RUNNING"
    argv = captured["argv"]
    assert "--run-context-file" in argv
    assert "--replace-existing-analysis-dir" in argv
    assert "--stage-dir" not in argv
    run_context_file = argv[argv.index("--run-context-file") + 1]
    assert run_context_file.endswith(".ursa-run-contexts/AJ-1/config/runs.tsv")
    run_context_content = (
        tmp_path / ".ursa-run-contexts" / "AJ-1" / "config" / "runs.tsv"
    ).read_text(encoding="utf-8")
    assert "run-a\tILMN\ts3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/" in (
        run_context_content
    )
    assert "s3://analysis-results/run-a/01-illumina_run_qc/" in run_context_content
    assert "s3://old-output/" not in run_context_content


def test_run_directory_analysis_refresh_launches_successor_job(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(
        "daylib_ursa.analysis_jobs.get_analysis_command",
        lambda _command_id, optional_features=None: _FakeRunAnalysisCommand(),
    )
    resources = _MemoryResourceStore()
    workset = resources.create_workset(
        name="Run directory run-a",
        tenant_id=TENANT_ID,
        owner_user_id=OWNER_USER_ID,
        artifact_set_euids=[],
        metadata={},
    )
    manifest = resources.create_manifest(
        workset_euid=workset.workset_euid,
        name="Run directory run-a run context",
        artifact_set_euid=None,
        artifact_euids=["AT-RUN-1"],
        input_references=[],
        metadata={
            "run_context_manifest": {
                "filename": "config/runs.tsv",
                "content": (
                    "RUNID\tPLATFORM\tRUN_DIR\n"
                    "run-a\tILMN\ts3://bucket/basecalls/lsmc/ssf-hq/LH01106/2026/run-a/\n"
                ),
            }
        },
    )
    first = resources.create_analysis_job(
        job_name="run-a:01:illumina_run_qc",
        workset_euid=workset.workset_euid,
        manifest_euid=manifest.manifest_euid,
        cluster_name="cluster-1",
        region="us-west-2",
        tenant_id=TENANT_ID,
        owner_user_id=OWNER_USER_ID,
        request={
            "analysis_command_id": "illumina_run_qc",
            "destination": "s3://analysis-results/run-a/01-illumina_run_qc/",
            "export_trigger": "on-success",
            "session_name": "run-a-illumina_run_qc",
            "project": "daylily",
            "aws_profile": "lsmc",
            "run_directory_trigger": {
                "trigger_euid": "URDT-1",
                "pipeline_order": 1,
                "predecessor_analysis_job_euid": None,
            },
        },
    )
    second = resources.create_analysis_job(
        job_name="run-a:02:illumina_bclconvert",
        workset_euid=workset.workset_euid,
        manifest_euid=manifest.manifest_euid,
        cluster_name="cluster-1",
        region="us-west-2",
        tenant_id=TENANT_ID,
        owner_user_id=OWNER_USER_ID,
        request={
            "analysis_command_id": "illumina_bclconvert",
            "destination": "s3://analysis-results/run-a/02-illumina_bclconvert/",
            "export_trigger": "on-success",
            "session_name": "run-a-illumina_bclconvert",
            "project": "daylily",
            "aws_profile": "lsmc",
            "run_directory_trigger": {
                "trigger_euid": "URDT-1",
                "pipeline_order": 2,
                "predecessor_analysis_job_euid": first.job_euid,
            },
        },
    )
    launched_sessions: list[str] = []

    class FakeDayEcClient:
        aws_profile = "lsmc"

        def workflow_launch(self, argv, *, cwd):  # noqa: ANN001
            _ = cwd
            args = list(argv)
            session_name = args[args.index("--session-name") + 1]
            launched_sessions.append(session_name)
            return subprocess.CompletedProcess(
                args=args,
                returncode=0,
                stdout=(
                    f"__DAYLILY_SESSION__={session_name}\n"
                    f"__DAYLILY_RUN_DIR__=/fsx/analysis/{session_name}\n"
                    "__DAYLILY_REPO_PATH__=/fsx/repos/daylily-omics-analysis\n"
                ),
                stderr="",
            )

        def workflow_status(self, *, session_name, region, cluster_name):  # noqa: ANN001
            _ = region, cluster_name
            return {
                "session_name": session_name,
                "exit_code": 0,
                "completed_at": "2026-05-27T00:10:00Z",
            }

    manager = AnalysisJobManager(
        resource_store=resources,
        client=FakeDayEcClient(),
        workspace_root=tmp_path,
    )

    launched = manager.launch_job(first.job_euid, actor_user_id=OWNER_USER_ID)
    assert launched.state == "RUNNING"
    assert resources.analysis_jobs[second.job_euid].state == "DEFINED"

    refreshed = manager.refresh_job(first.job_euid, actor_user_id=OWNER_USER_ID)

    assert refreshed.state == "COMPLETED"
    assert launched_sessions == ["run-a-illumina_run_qc", "run-a-illumina_bclconvert"]
    assert resources.analysis_jobs[second.job_euid].state == "RUNNING"
    assert resources.analysis_events[second.job_euid][0].event_type == ("run-directory-predecessor")


def test_dewey_client_registers_analysis_results_with_bearer_and_idempotency() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("Authorization")
        captured["idempotency"] = request.headers.get("Idempotency-Key")
        captured["body"] = request.read().decode("utf-8")
        return httpx.Response(
            201,
            json={
                "receipt": {"artifact_set_euid": "AS-RESULT-1"},
                "artifact_set": {"artifact_set_euid": "AS-RESULT-1"},
            },
        )

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as http_client:
        client = DeweyClient(
            base_url="https://dewey.example",
            token="dewey-token",
            client=http_client,
        )
        response = client.register_analysis_results(
            payload={
                "analysis_euid": "AN-1",
                "command_id": "illumina_snv_alignstats_relatedness_vep_multiqc",
                "result_status": "succeeded",
                "result_root_uri": "s3://bucket/results/AN-1/",
                "artifacts": [
                    {
                        "logical_name": "multiqc",
                        "artifact_role": "multiqc_html",
                        "relative_path": "multiqc_report.html",
                    }
                ],
            },
            idempotency_key="dewey-result-1",
        )

    assert response["receipt"]["artifact_set_euid"] == "AS-RESULT-1"
    assert captured["url"] == "https://dewey.example/api/v1/analysis-results/register"
    assert captured["authorization"] == "Bearer dewey-token"
    assert captured["idempotency"] == "dewey-result-1"
