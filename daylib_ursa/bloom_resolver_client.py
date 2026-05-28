"""HTTP client for Bloom sequenced-assignment resolution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import uuid

import httpx

from daylib_ursa.analysis_store import RunResolution


class BloomResolverError(RuntimeError):
    """Raised when Bloom resolution fails."""


def _require_https_url(value: str, *, field_name: str) -> str:
    normalized = str(value or "").strip().rstrip("/")
    if not normalized:
        raise BloomResolverError(f"{field_name} is required")
    if not normalized.startswith("https://"):
        raise BloomResolverError(f"{field_name} must use an absolute https:// URL")
    return normalized


@dataclass
class BloomResolverClient:
    base_url: str
    token: str
    timeout_seconds: float = 10.0
    verify_ssl: bool = True
    client: httpx.Client | None = None

    def _headers(self) -> dict[str, str]:
        token = str(self.token or "").strip()
        if not token:
            raise BloomResolverError("Bloom API bearer token is required")
        return {
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        }

    def resolve_run_assignment(
        self,
        run_euid: str,
        flowcell_id: str,
        lane: str,
        library_barcode: str,
    ) -> RunResolution:
        url = (
            f"{_require_https_url(self.base_url, field_name='Bloom base URL')}"
            f"/api/v1/external/atlas/beta/runs/{run_euid}/resolve"
        )
        client = self.client or httpx.Client(
            timeout=self.timeout_seconds,
            verify=self.verify_ssl,
        )
        close_client = self.client is None
        try:
            response = client.get(
                url,
                params={
                    "flowcell_id": flowcell_id,
                    "lane": lane,
                    "library_barcode": library_barcode,
                },
                headers=self._headers(),
            )
        except httpx.HTTPError as exc:
            raise BloomResolverError(f"Bloom resolver request failed: {exc}") from exc
        finally:
            if close_client:
                client.close()

        if response.status_code >= 400:
            raise BloomResolverError(
                f"Bloom resolver returned {response.status_code}: {response.text}"
            )

        body: dict[str, Any] = response.json()
        required = (
            "run_euid",
            "flowcell_id",
            "lane",
            "library_barcode",
            "sequenced_library_assignment_euid",
            "atlas_tenant_id",
            "atlas_trf_euid",
            "atlas_test_euid",
            "atlas_test_fulfillment_item_euid",
        )
        missing = [key for key in required if not str(body.get(key) or "").strip()]
        if missing:
            raise BloomResolverError(
                f"Bloom resolver response missing required fields: {', '.join(missing)}"
            )

        return RunResolution(
            run_euid=str(body["run_euid"]),
            flowcell_id=str(body["flowcell_id"]),
            lane=str(body["lane"]),
            library_barcode=str(body["library_barcode"]),
            sequenced_library_assignment_euid=str(body["sequenced_library_assignment_euid"]),
            tenant_id=uuid.UUID(str(body["atlas_tenant_id"])),
            atlas_trf_euid=str(body["atlas_trf_euid"]),
            atlas_test_euid=str(body["atlas_test_euid"]),
            atlas_test_fulfillment_item_euid=str(body["atlas_test_fulfillment_item_euid"]),
            sequencing_pool_euid=str(
                body.get("sequencing_pool_euid") or body.get("pool_euid") or ""
            ).strip()
            or None,
        )

    def create_or_reuse_run_directory_run(
        self,
        *,
        run_folder_name: str,
        platform: str,
        storage_uri: str,
        dewey_artifact_euid: str,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        clean_name = str(run_folder_name or "").strip()
        clean_platform = str(platform or "").strip()
        clean_storage_uri = str(storage_uri or "").strip()
        clean_artifact_euid = str(dewey_artifact_euid or "").strip()
        clean_key = str(idempotency_key or "").strip()
        if not clean_name:
            raise BloomResolverError("run_folder_name is required")
        if clean_platform not in {"ILMN", "ONT", "ULTIMA"}:
            raise BloomResolverError("platform must be one of: ILMN, ONT, ULTIMA")
        if not clean_storage_uri:
            raise BloomResolverError("storage_uri is required")
        if not clean_artifact_euid:
            raise BloomResolverError("dewey_artifact_euid is required")
        if not clean_key:
            raise BloomResolverError("idempotency_key is required")
        url = (
            f"{_require_https_url(self.base_url, field_name='Bloom base URL')}"
            "/api/v1/external/ursa/run-directories"
        )
        payload = {
            "run_folder_name": clean_name,
            "platform": clean_platform,
            "storage_uri": clean_storage_uri,
            "dewey_artifact_euid": clean_artifact_euid,
            "metadata": dict(metadata or {}),
        }
        headers = {
            **self._headers(),
            "Content-Type": "application/json",
            "Idempotency-Key": clean_key,
        }
        client = self.client or httpx.Client(
            timeout=self.timeout_seconds,
            verify=self.verify_ssl,
        )
        close_client = self.client is None
        try:
            response = client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise BloomResolverError(f"Bloom run-directory request failed: {exc}") from exc
        finally:
            if close_client:
                client.close()

        if response.status_code >= 400:
            raise BloomResolverError(
                f"Bloom run-directory request returned {response.status_code}: {response.text}"
            )
        body: dict[str, Any] = response.json()
        if not isinstance(body, dict):
            raise BloomResolverError("Bloom run-directory response was not a JSON object")
        run_euid = str(body.get("run_euid") or body.get("bloom_run_euid") or "").strip()
        if not run_euid:
            raise BloomResolverError("Bloom run-directory response missing run_euid")
        body["run_euid"] = run_euid
        return body
