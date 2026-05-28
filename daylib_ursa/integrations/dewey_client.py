"""Ursa -> Dewey artifact integration client."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


class DeweyClientError(RuntimeError):
    """Raised on Dewey integration failures."""


def _require_https_url(value: str, *, field_name: str) -> str:
    normalized = str(value or "").strip().rstrip("/")
    if not normalized:
        raise DeweyClientError(f"{field_name} is required")
    if not normalized.startswith("https://"):
        raise DeweyClientError(f"{field_name} must use an absolute https:// URL")
    return normalized


@dataclass
class DeweyClient:
    base_url: str
    token: str
    timeout_seconds: float = 10.0
    verify_ssl: bool = True
    client: httpx.Client | None = None

    def _headers(self, *, idempotency_key: str | None = None) -> dict[str, str]:
        token = str(self.token or "").strip()
        if not token:
            raise DeweyClientError("Dewey API bearer token is required")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        clean_key = str(idempotency_key or "").strip()
        if clean_key:
            headers["Idempotency-Key"] = clean_key
        return headers

    def _http_client(self) -> tuple[httpx.Client, bool]:
        if self.client is not None:
            return self.client, False
        return (
            httpx.Client(timeout=self.timeout_seconds, verify=self.verify_ssl),
            True,
        )

    def get_artifact(self, artifact_euid: str) -> dict[str, Any]:
        target = str(artifact_euid or "").strip()
        if not target:
            raise DeweyClientError("artifact_euid is required")
        url = f"{_require_https_url(self.base_url, field_name='Dewey base URL')}/api/v1/artifacts/{target}"
        client, close_client = self._http_client()
        try:
            response = client.get(url, headers=self._headers())
        except httpx.HTTPError as exc:
            raise DeweyClientError(f"Dewey artifact lookup failed: {exc}") from exc
        finally:
            if close_client:
                client.close()
        if response.status_code >= 400:
            raise DeweyClientError(
                f"Dewey artifact lookup returned {response.status_code}: {response.text}"
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise DeweyClientError("Dewey artifact response was not a JSON object")
        return payload

    def resolve_artifact(self, artifact_euid: str) -> dict[str, Any]:
        url = f"{_require_https_url(self.base_url, field_name='Dewey base URL')}/api/v1/resolve/artifact"
        payload = {"artifact_euid": str(artifact_euid or "").strip()}
        if not payload["artifact_euid"]:
            raise DeweyClientError("artifact_euid is required")
        client, close_client = self._http_client()
        try:
            response = client.post(url, json=payload, headers=self._headers())
        except httpx.HTTPError as exc:
            raise DeweyClientError(f"Dewey resolve failed: {exc}") from exc
        finally:
            if close_client:
                client.close()
        if response.status_code >= 400:
            raise DeweyClientError(
                f"Dewey resolve returned {response.status_code}: {response.text}"
            )
        body = response.json()
        if not isinstance(body, dict):
            raise DeweyClientError("Dewey resolve response was not a JSON object")
        if not str(body.get("storage_uri") or "").strip():
            raise DeweyClientError("Dewey resolve response missing storage_uri")
        if not str(body.get("artifact_type") or "").strip():
            raise DeweyClientError("Dewey resolve response missing artifact_type")
        return body

    def resolve_artifact_set(self, artifact_set_euid: str) -> dict[str, Any]:
        url = (
            f"{_require_https_url(self.base_url, field_name='Dewey base URL')}"
            "/api/v1/resolve/artifact-set"
        )
        payload = {"artifact_set_euid": str(artifact_set_euid or "").strip()}
        if not payload["artifact_set_euid"]:
            raise DeweyClientError("artifact_set_euid is required")
        client, close_client = self._http_client()
        try:
            response = client.post(url, json=payload, headers=self._headers())
        except httpx.HTTPError as exc:
            raise DeweyClientError(f"Dewey artifact-set resolve failed: {exc}") from exc
        finally:
            if close_client:
                client.close()
        if response.status_code >= 400:
            raise DeweyClientError(
                f"Dewey artifact-set resolve returned {response.status_code}: {response.text}"
            )
        body = response.json()
        if not isinstance(body, dict):
            raise DeweyClientError("Dewey artifact-set resolve response was not a JSON object")
        if not str(body.get("artifact_set_euid") or "").strip():
            raise DeweyClientError("Dewey artifact-set resolve response missing artifact_set_euid")
        return body

    def import_artifact(
        self,
        *,
        artifact_type: str,
        storage_uri: str,
        metadata: dict[str, Any] | None,
        idempotency_key: str | None = None,
    ) -> str:
        url = f"{_require_https_url(self.base_url, field_name='Dewey base URL')}/api/v1/artifacts/import"
        payload = {
            "artifact_type": str(artifact_type or "").strip(),
            "storage_uri": str(storage_uri or "").strip(),
            "metadata": dict(metadata or {}),
        }
        if not payload["artifact_type"]:
            raise DeweyClientError("artifact_type is required")
        if not payload["storage_uri"]:
            raise DeweyClientError("storage_uri is required")
        client, close_client = self._http_client()
        try:
            response = client.post(
                url,
                json=payload,
                headers=self._headers(idempotency_key=idempotency_key),
            )
        except httpx.HTTPError as exc:
            raise DeweyClientError(f"Dewey artifact import failed: {exc}") from exc
        finally:
            if close_client:
                client.close()
        if response.status_code >= 400:
            raise DeweyClientError(
                f"Dewey artifact import returned {response.status_code}: {response.text}"
            )
        body = response.json()
        if not isinstance(body, dict):
            raise DeweyClientError("Dewey artifact import response was not a JSON object")
        artifact_euid = str(body.get("artifact_euid") or "").strip()
        if not artifact_euid:
            raise DeweyClientError("Dewey artifact import response missing artifact_euid")
        return artifact_euid

    def register_artifact(
        self,
        *,
        artifact_type: str,
        storage_uri: str,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> str:
        return self.import_artifact(
            artifact_type=artifact_type,
            storage_uri=storage_uri,
            metadata=metadata,
            idempotency_key=idempotency_key,
        )

    def register_analysis_results(
        self,
        *,
        payload: dict[str, Any],
        idempotency_key: str,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict) or not payload:
            raise DeweyClientError("analysis result registration payload is required")
        clean_key = str(idempotency_key or "").strip()
        if not clean_key:
            raise DeweyClientError("idempotency_key is required")
        url = (
            f"{_require_https_url(self.base_url, field_name='Dewey base URL')}"
            "/api/v1/analysis-results/register"
        )
        client, close_client = self._http_client()
        try:
            response = client.post(
                url,
                json=payload,
                headers=self._headers(idempotency_key=clean_key),
            )
        except httpx.HTTPError as exc:
            raise DeweyClientError(f"Dewey analysis-result registration failed: {exc}") from exc
        finally:
            if close_client:
                client.close()
        if response.status_code >= 400:
            raise DeweyClientError(
                "Dewey analysis-result registration returned "
                f"{response.status_code}: {response.text}"
            )
        body = response.json()
        if not isinstance(body, dict):
            raise DeweyClientError(
                "Dewey analysis-result registration response was not a JSON object"
            )
        receipt = body.get("receipt")
        if not isinstance(receipt, dict) or not str(receipt.get("artifact_set_euid") or "").strip():
            raise DeweyClientError(
                "Dewey analysis-result registration response missing receipt artifact_set_euid"
            )
        return body

    def create_external_object(
        self,
        *,
        external_system: str,
        external_object_type: str,
        external_object_id: str,
        external_uri: str | None = None,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        clean_key = str(idempotency_key or "").strip()
        if not clean_key:
            raise DeweyClientError("idempotency_key is required")
        payload = {
            "external_system": str(external_system or "").strip(),
            "external_object_type": str(external_object_type or "").strip(),
            "external_object_id": str(external_object_id or "").strip(),
            "external_uri": str(external_uri or "").strip() or None,
            "metadata": dict(metadata or {}),
        }
        for field_name in ("external_system", "external_object_type", "external_object_id"):
            if not payload[field_name]:
                raise DeweyClientError(f"{field_name} is required")
        url = f"{_require_https_url(self.base_url, field_name='Dewey base URL')}/api/v1/external-objects"
        client, close_client = self._http_client()
        try:
            response = client.post(
                url,
                json=payload,
                headers=self._headers(idempotency_key=clean_key),
            )
        except httpx.HTTPError as exc:
            raise DeweyClientError(f"Dewey external-object create failed: {exc}") from exc
        finally:
            if close_client:
                client.close()
        if response.status_code >= 400:
            raise DeweyClientError(
                f"Dewey external-object create returned {response.status_code}: {response.text}"
            )
        body = response.json()
        if not isinstance(body, dict):
            raise DeweyClientError("Dewey external-object response was not a JSON object")
        if not str(body.get("external_object_euid") or "").strip():
            raise DeweyClientError("Dewey external-object response missing external_object_euid")
        return body

    def attach_external_object_relation(
        self,
        *,
        target_type: str,
        target_euid: str,
        external_object_euid: str,
        relation_type: str,
        metadata: dict[str, Any] | None = None,
        idempotency_key: str,
    ) -> dict[str, Any]:
        clean_key = str(idempotency_key or "").strip()
        if not clean_key:
            raise DeweyClientError("idempotency_key is required")
        payload = {
            "target_type": str(target_type or "").strip(),
            "target_euid": str(target_euid or "").strip(),
            "external_object_euid": str(external_object_euid or "").strip(),
            "relation_type": str(relation_type or "").strip(),
            "metadata": dict(metadata or {}),
        }
        for field_name in ("target_type", "target_euid", "external_object_euid", "relation_type"):
            if not payload[field_name]:
                raise DeweyClientError(f"{field_name} is required")
        url = (
            f"{_require_https_url(self.base_url, field_name='Dewey base URL')}"
            "/api/v1/external-object-relations"
        )
        client, close_client = self._http_client()
        try:
            response = client.post(
                url,
                json=payload,
                headers=self._headers(idempotency_key=clean_key),
            )
        except httpx.HTTPError as exc:
            raise DeweyClientError(f"Dewey external-object relation failed: {exc}") from exc
        finally:
            if close_client:
                client.close()
        if response.status_code >= 400:
            raise DeweyClientError(
                f"Dewey external-object relation returned {response.status_code}: {response.text}"
            )
        body = response.json()
        if not isinstance(body, dict):
            raise DeweyClientError("Dewey external-object relation response was not a JSON object")
        if not str(body.get("external_object_relation_euid") or "").strip():
            raise DeweyClientError(
                "Dewey external-object relation response missing external_object_relation_euid"
            )
        return body
