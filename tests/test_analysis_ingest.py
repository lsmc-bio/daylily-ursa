from __future__ import annotations

from dataclasses import replace
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest

from daylib_ursa.analysis_store import (
    AnalysisArtifact,
    AnalysisRecord,
    AnalysisState,
    ReviewState,
    RunResolution,
    UrsaQueueRecord,
)
from daylib_ursa.auth import CurrentUser, Role
from daylib_ursa.config import Settings
from daylib_ursa.workset_api import create_app

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class DummyStore:
    def __init__(self) -> None:
        self.record = AnalysisRecord(
            analysis_euid="AN-1",
            workset_euid=None,
            run_euid="RUN-1",
            flowcell_id="FLOW-1",
            lane="1",
            library_barcode="LIB-1",
            sequenced_library_assignment_euid="SQA-1",
            tenant_id=TENANT_ID,
            atlas_trf_euid="TRF-1",
            atlas_test_euid="TST-1",
            atlas_test_fulfillment_item_euid="TPC-1",
            analysis_type="beta-default",
            state=AnalysisState.INGESTED.value,
            review_state=ReviewState.PENDING.value,
            result_status="PENDING",
            run_folder="s3://ursa-internal/RUN-1/",
            internal_bucket="ursa-internal",
            input_references=[],
            result_payload={},
            metadata={},
            created_at="2026-03-07T00:00:00Z",
            updated_at="2026-03-07T00:00:00Z",
            atlas_return={},
            artifacts=[],
        )
        self.last_ingest = None
        self.queue_records: dict[str, UrsaQueueRecord] = {}
        self.queue_record_calls: list[dict[str, object]] = []

    def ingest_analysis(self, **kwargs):
        self.last_ingest = kwargs
        self.record = replace(
            self.record,
            analysis_type=kwargs["analysis_type"],
            internal_bucket=kwargs["internal_bucket"],
            input_references=kwargs["input_references"],
        )
        return self.record

    def list_analyses(self, *, tenant_id=None, workset_euid=None, limit=200):
        _ = (workset_euid, limit)
        if tenant_id is not None and tenant_id != self.record.tenant_id:
            return []
        return [self.record]

    def get_analysis(self, analysis_euid: str):
        return self.record if analysis_euid == self.record.analysis_euid else None

    def update_analysis_state(self, analysis_euid: str, **kwargs):
        assert analysis_euid == self.record.analysis_euid
        self.record = replace(
            self.record,
            state=kwargs["state"].value,
            result_status=kwargs.get("result_status") or self.record.result_status,
            result_payload=kwargs.get("result_payload") or self.record.result_payload,
            metadata={**self.record.metadata, **kwargs.get("metadata", {})},
            updated_at="2026-03-07T01:00:00Z",
        )
        return self.record

    def add_artifact(self, analysis_euid: str, **kwargs):
        assert analysis_euid == self.record.analysis_euid
        artifact = AnalysisArtifact(
            artifact_euid="AF-1",
            artifact_type=kwargs["artifact_type"],
            storage_uri=kwargs["storage_uri"],
            filename=kwargs["filename"],
            mime_type=kwargs.get("mime_type"),
            checksum_sha256=kwargs.get("checksum_sha256"),
            size_bytes=kwargs.get("size_bytes"),
            created_at="2026-03-07T02:00:00Z",
            metadata=kwargs.get("metadata") or {},
        )
        self.record = replace(self.record, artifacts=[artifact])
        return artifact

    def set_review_state(self, analysis_euid: str, **kwargs):
        assert analysis_euid == self.record.analysis_euid
        self.record = replace(
            self.record,
            review_state=kwargs["review_state"].value,
            state=AnalysisState.REVIEWED.value,
            updated_at="2026-03-07T03:00:00Z",
        )
        return self.record

    def mark_returned(self, analysis_euid: str, **kwargs):
        assert analysis_euid == self.record.analysis_euid
        self.record = replace(
            self.record,
            state=AnalysisState.RETURNED.value,
            atlas_return=kwargs["atlas_return"],
            updated_at="2026-03-07T04:00:00Z",
        )
        return self.record

    def list_queue_records(self, *, queue_name, tenant_id=None, state=None, limit=200):
        _ = limit
        records = [
            record
            for record in self.queue_records.values()
            if record.queue_name == queue_name
            and (tenant_id is None or record.tenant_id == tenant_id)
            and (not state or record.state == state)
        ]
        return records

    def get_queue_record(self, queue_record_euid: str):
        return self.queue_records.get(queue_record_euid)

    def create_queue_record(self, **kwargs):
        self.queue_record_calls.append(kwargs)
        existing = next(
            (
                record
                for record in self.queue_records.values()
                if record.idempotency_key == kwargs["idempotency_key"]
            ),
            None,
        )
        if existing is not None:
            return existing
        record = UrsaQueueRecord(
            queue_record_euid=f"UQ-{len(self.queue_records) + 1}",
            queue_name=kwargs["queue_name"],
            object_euid=kwargs["object_euid"],
            object_type=kwargs["object_type"],
            tenant_id=kwargs["tenant_id"],
            state=kwargs["state"],
            idempotency_key=kwargs["idempotency_key"],
            metadata=kwargs.get("metadata") or {},
            related_euids=kwargs.get("related_euids") or {},
            created_at="2026-03-07T05:00:00Z",
            updated_at="2026-03-07T05:00:00Z",
        )
        self.queue_records[record.queue_record_euid] = record
        return record

    def transition_queue_record(self, queue_record_euid: str, **kwargs):
        record = self.queue_records[queue_record_euid]
        updated = replace(
            record,
            state=kwargs["state"],
            metadata={**record.metadata, **(kwargs.get("metadata") or {})},
            updated_at="2026-03-07T06:00:00Z",
        )
        self.queue_records[queue_record_euid] = updated
        return updated


class DummyBloomClient:
    def __init__(self) -> None:
        self.calls = []

    def resolve_run_assignment(
        self, run_euid: str, flowcell_id: str, lane: str, library_barcode: str
    ) -> RunResolution:
        self.calls.append((run_euid, flowcell_id, lane, library_barcode))
        return RunResolution(
            run_euid=run_euid,
            flowcell_id=flowcell_id,
            lane=lane,
            library_barcode=library_barcode,
            sequenced_library_assignment_euid="SQA-1",
            tenant_id=TENANT_ID,
            atlas_trf_euid="TRF-1",
            atlas_test_euid="TST-1",
            atlas_test_fulfillment_item_euid="TPC-1",
        )


class DummyAuthProvider:
    def resolve_access_token(self, access_token: str) -> CurrentUser:
        assert access_token == "atlas-token"
        return CurrentUser(
            sub="00000000-0000-0000-0000-000000000101",
            email="user@example.test",
            name="User One",
            tenant_id=TENANT_ID,
            roles=[Role.ADMIN.value],
            auth_source="cognito",
        )


def _settings() -> Settings:
    return Settings(
        aws_profile="",
        cors_origins="*",
        session_secret_key="test-session-secret",
        ursa_internal_api_key="ursa-test-key",
        bloom_base_url="https://bloom.example",
        atlas_base_url="https://atlas.example",
        cognito_domain="ursa.auth.us-west-2.amazoncognito.com",
        cognito_app_client_id="client-123",
        cognito_callback_url="https://localhost:8913/auth/callback",
        cognito_logout_url="https://localhost:8913/login",
        ursa_internal_output_bucket="ursa-internal",
        ursa_tapdb_mount_enabled=False,
    )


def _create_test_app(*args, **kwargs):
    with patch("daylib_ursa.workset_api.RegionAwareS3Client", return_value=object()):
        return create_app(*args, **kwargs)


def test_ingest_analysis_resolves_mixed_input_references():
    store = DummyStore()
    bloom = DummyBloomClient()

    class FakeDeweyClient:
        def resolve_artifact(self, artifact_euid: str):
            assert artifact_euid == "AT-1"
            return {
                "artifact_euid": "AT-1",
                "artifact_type": "fastq",
                "storage_uri": "s3://dewey-bucket/RUN-1/read1.fastq.gz",
                "metadata": {"source": "dewey"},
            }

        def resolve_artifact_set(self, artifact_set_euid: str):
            assert artifact_set_euid == "AS-1"
            return {
                "artifact_set_euid": "AS-1",
                "members": [
                    {
                        "artifact_euid": "AT-2",
                        "artifact_type": "bam",
                        "storage_uri": "s3://dewey-bucket/RUN-1/sample.bam",
                        "metadata": {},
                    }
                ],
            }

    app = _create_test_app(
        store,
        bloom_client=bloom,
        dewey_client=FakeDeweyClient(),
        settings=_settings(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/analyses/ingest",
            headers={
                "X-API-Key": "ursa-test-key",
                "Idempotency-Key": "idem-1",
            },
            json={
                "run_euid": "RUN-1",
                "flowcell_id": "FLOW-1",
                "lane": "1",
                "library_barcode": "LIB-1",
                "analysis_type": "germline",
                "input_references": [
                    {"reference_type": "artifact_euid", "value": "AT-1"},
                    {"reference_type": "artifact_set_euid", "value": "AS-1"},
                ],
            },
        )

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["analysis_euid"] == "AN-1"
    assert body["tenant_id"] == str(TENANT_ID)
    assert body["internal_bucket"] == "ursa-internal"
    assert len(body["input_references"]) == 2
    assert bloom.calls == [("RUN-1", "FLOW-1", "1", "LIB-1")]
    assert store.last_ingest["idempotency_key"] == "idem-1"


def test_ingest_analysis_requires_idempotency_key(monkeypatch):
    app = _create_test_app(DummyStore(), bloom_client=DummyBloomClient(), settings=_settings())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/analyses/ingest",
            headers={"X-API-Key": "ursa-test-key"},
            json={
                "run_euid": "RUN-1",
                "flowcell_id": "FLOW-1",
                "lane": "1",
                "library_barcode": "LIB-1",
                "input_references": [{"reference_type": "artifact_euid", "value": "AT-1"}],
            },
        )

    assert response.status_code == 400
    assert "Idempotency-Key" in response.text


def test_ingest_analysis_requires_dewey_client():
    app = _create_test_app(DummyStore(), bloom_client=DummyBloomClient(), settings=_settings())

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/analyses/ingest",
            headers={
                "X-API-Key": "ursa-test-key",
                "Idempotency-Key": "idem-2",
            },
            json={
                "run_euid": "RUN-1",
                "flowcell_id": "FLOW-1",
                "lane": "1",
                "library_barcode": "LIB-1",
                "input_references": [{"reference_type": "artifact_euid", "value": "AT-1"}],
            },
        )

    assert response.status_code == 503
    assert "Dewey integration is required" in response.json()["detail"]


def test_analysis_list_get_and_status_routes() -> None:
    store = DummyStore()
    app = _create_test_app(
        store,
        bloom_client=DummyBloomClient(),
        auth_provider=DummyAuthProvider(),
        settings=_settings(),
    )

    with TestClient(app) as client:
        listed = client.get(
            "/api/v1/analyses",
            headers={"Authorization": "Bearer atlas-token"},
        )
        detail = client.get(
            "/api/v1/analyses/AN-1",
            headers={"Authorization": "Bearer atlas-token"},
        )
        status_update = client.post(
            "/api/v1/analyses/AN-1/status",
            headers={"X-API-Key": "ursa-test-key"},
            json={
                "state": "REVIEW_PENDING",
                "result_status": "RUNNING",
                "metadata": {"phase": "qc"},
            },
        )

    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["analysis_euid"] == "AN-1"
    assert detail.status_code == 200, detail.text
    assert detail.json()["tenant_id"] == str(TENANT_ID)
    assert status_update.status_code == 200, status_update.text
    assert status_update.json()["state"] == "REVIEW_PENDING"
    assert status_update.json()["result_status"] == "RUNNING"
    assert status_update.json()["metadata"]["phase"] == "qc"


def test_beta_queue_routes_create_list_and_transition_records() -> None:
    store = DummyStore()
    app = _create_test_app(
        store,
        bloom_client=DummyBloomClient(),
        auth_provider=DummyAuthProvider(),
        settings=_settings(),
    )

    with TestClient(app) as client:
        created = client.post(
            "/api/v1/beta/queues/analysis_ready/items",
            headers={
                "Authorization": "Bearer atlas-token",
                "Idempotency-Key": "analysis-ready-1",
            },
            json={
                "object_euid": "DWY-FASTQ-1",
                "object_type": "dewey_fastq_artifact",
                "metadata": {"product_code": "ILMN_PROBAND"},
                "related_euids": {
                    "atlas_test_euid": "TST-1",
                    "bloom_run_euid": "RUN-1",
                    "dewey_artifact_euid": "DWY-FASTQ-1",
                },
            },
        )
        listed = client.get(
            "/api/v1/beta/queues/analysis_ready/items",
            headers={"Authorization": "Bearer atlas-token"},
        )
        transitioned = client.post(
            "/api/v1/beta/queues/analysis_ready/items/UQ-1/transition",
            headers={"Authorization": "Bearer atlas-token"},
            json={"state": "selected", "metadata": {"manifest_euid": "MF-1"}},
        )

    assert created.status_code == 201, created.text
    assert created.json()["queue_name"] == "analysis_ready"
    assert created.json()["object_euid"] == "DWY-FASTQ-1"
    assert created.json()["metadata"]["product_code"] == "ILMN_PROBAND"
    assert listed.status_code == 200, listed.text
    assert listed.json()[0]["queue_record_euid"] == "UQ-1"
    assert transitioned.status_code == 200, transitioned.text
    assert transitioned.json()["state"] == "selected"
    assert transitioned.json()["metadata"]["manifest_euid"] == "MF-1"


def test_beta_queue_create_requires_idempotency_key() -> None:
    app = _create_test_app(
        DummyStore(),
        bloom_client=DummyBloomClient(),
        auth_provider=DummyAuthProvider(),
        settings=_settings(),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/beta/queues/analysis_ready/items",
            headers={"Authorization": "Bearer atlas-token"},
            json={"object_euid": "DWY-FASTQ-1", "object_type": "dewey_fastq_artifact"},
        )

    assert response.status_code == 400
    assert "Idempotency-Key" in response.text


def test_settings_reject_non_https_cross_service_urls():
    with pytest.raises(ValueError, match="absolute https:// URL"):
        Settings(
            bloom_base_url="http://bloom.example",
            atlas_base_url="https://atlas.example",
            ursa_internal_output_bucket="ursa-internal",
        )

    with pytest.raises(ValueError, match="absolute https:// URL"):
        Settings(
            bloom_base_url="https://bloom.example",
            atlas_base_url="http://atlas.example",
            ursa_internal_output_bucket="ursa-internal",
        )
