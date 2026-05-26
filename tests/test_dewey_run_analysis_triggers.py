from __future__ import annotations

from dataclasses import dataclass, field

import httpx
from fastapi.testclient import TestClient

from daylib_ursa.config import Settings
from daylib_ursa.integrations.dewey_client import DeweyClient
from daylib_ursa.workset_api import create_app


class _DummyBloomClient:
    pass


class _DummyClusterService:
    client = object()


@dataclass
class _DummyStore:
    calls: list[dict] = field(default_factory=list)


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
    )


def _app(monkeypatch):
    def fake_analysis_command_payload(command_id: str):
        if command_id != "illumina_snv_alignstats_relatedness_vep_multiqc":
            raise ValueError(f"Unknown analysis command: {command_id}")
        return {
            "command_id": command_id,
            "workflow": "daylily-omics-analysis",
            "input_contract": "run_context",
        }

    monkeypatch.setattr(
        "daylib_ursa.workset_api.analysis_command_payload",
        fake_analysis_command_payload,
    )
    return create_app(
        _DummyStore(),
        bloom_client=_DummyBloomClient(),
        atlas_client=None,
        dewey_client=None,
        cluster_service=_DummyClusterService(),
        settings=_settings(),
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
