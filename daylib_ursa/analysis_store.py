"""TapDB-backed analysis persistence for Ursa beta flows."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any
import uuid

from daylily_tapdb import generic_instance

from daylib_ursa.tapdb_graph import TapDBBackend, from_json_addl, utc_now_iso
from daylib_ursa.tapdb_provenance import (
    dewey_refs_from_inputs,
    expected_fanout_graph,
    explicit_ref,
    payload_with_tapdb_graph,
    replace_instance_properties,
)
from daylib_ursa.tapdb_templates import seed_ursa_templates


class AnalysisState(str, Enum):
    INGESTED = "INGESTED"
    RUNNING = "RUNNING"
    REVIEW_PENDING = "REVIEW_PENDING"
    REVIEWED = "REVIEWED"
    RETURNED = "RETURNED"
    FAILED = "FAILED"


class ReviewState(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


ANALYSIS_TEMPLATE = "RGX/analysis/run-linked/1.0/"
ARTIFACT_TEMPLATE = "RGX/artifact/analysis-output/1.0/"
REVIEW_EVENT_TEMPLATE = "RGX/analysis/review-event/1.0/"
RETURN_EVENT_TEMPLATE = "RGX/analysis/atlas-return/1.0/"
QUEUE_RECORD_TEMPLATE = "RGX/queue/beta-record/1.0/"
RESOLVED_CONTEXT_TEMPLATE = "RGX/reference/sequenced-assignment-context/1.0/"
BETA_QUEUE_NAMES = {
    "analysis_ready",
    "analysis_qc",
    "report_generation",
    "analysis_exception",
    "report_generation_exception",
}
QUEUE_RELATED_EUID_GRAPH_REFS = {
    "atlas_test_euid": ("atlas", "for_atlas_test", "test"),
    "atlas_trf_euid": ("atlas", "for_atlas_trf", "trf"),
    "bloom_library_euid": ("bloom", "uses_bloom_library", "library"),
    "bloom_pool_euid": ("bloom", "uses_bloom_pool", "pool"),
    "bloom_run_euid": ("bloom", "uses_bloom_run", "run"),
    "dewey_fastq_r1_euid": ("dewey", "uses_fastq_artifact", "fastq_artifact"),
    "dewey_fastq_r2_euid": ("dewey", "uses_fastq_artifact", "fastq_artifact"),
    "dewey_result_directory_euid": (
        "dewey",
        "registered_result_artifact",
        "result_directory",
    ),
    "dewey_vcf_artifact_euid": ("dewey", "registered_result_artifact", "vcf_artifact"),
}


@dataclass(frozen=True)
class RunResolution:
    run_euid: str
    flowcell_id: str
    lane: str
    library_barcode: str
    sequenced_library_assignment_euid: str
    tenant_id: uuid.UUID
    atlas_trf_euid: str
    atlas_test_euid: str
    atlas_test_fulfillment_item_euid: str
    sequencing_pool_euid: str | None = None


@dataclass(frozen=True)
class AnalysisArtifact:
    artifact_euid: str
    artifact_type: str
    storage_uri: str
    filename: str
    mime_type: str | None
    checksum_sha256: str | None
    size_bytes: int | None
    created_at: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class AnalysisRecord:
    analysis_euid: str
    workset_euid: str | None
    run_euid: str
    flowcell_id: str
    lane: str
    library_barcode: str
    sequenced_library_assignment_euid: str
    tenant_id: uuid.UUID
    atlas_trf_euid: str
    atlas_test_euid: str
    atlas_test_fulfillment_item_euid: str
    analysis_type: str
    state: str
    review_state: str
    result_status: str
    run_folder: str
    internal_bucket: str
    input_references: list[dict[str, Any]]
    result_payload: dict[str, Any]
    metadata: dict[str, Any]
    created_at: str
    updated_at: str
    atlas_return: dict[str, Any]
    artifacts: list[AnalysisArtifact]


@dataclass(frozen=True)
class UrsaQueueRecord:
    queue_record_euid: str
    queue_name: str
    object_euid: str
    object_type: str
    tenant_id: uuid.UUID
    state: str
    idempotency_key: str
    metadata: dict[str, Any]
    related_euids: dict[str, str]
    created_at: str
    updated_at: str


class AnalysisStore:
    """Stores Ursa beta analysis execution state in TapDB generic instances."""

    def __init__(self) -> None:
        self.backend = TapDBBackend(app_username="ursa")

    def bootstrap(self) -> None:
        with self.backend.session_scope(commit=True) as session:
            if callable(seed_ursa_templates):
                seed_ursa_templates(session)
            self.backend.ensure_templates(session)

    @staticmethod
    def _parse_tenant_uuid(value: Any) -> uuid.UUID:
        return uuid.UUID(str(value or "").strip())

    def _find_analysis(
        self,
        session,
        analysis_euid: str,
        *,
        for_update: bool = False,
    ) -> generic_instance | None:
        return self.backend.find_instance_by_euid(
            session,
            template_code=ANALYSIS_TEMPLATE,
            value=analysis_euid,
            for_update=for_update,
        )

    def _find_analysis_by_ingest_key(
        self, session, idempotency_key: str
    ) -> generic_instance | None:
        return self.backend.find_instance_by_external_id(
            session,
            template_code=ANALYSIS_TEMPLATE,
            key="ingest_idempotency_key",
            value=idempotency_key,
        )

    def _find_queue_record_by_idempotency_key(
        self, session, idempotency_key: str
    ) -> generic_instance | None:
        return self.backend.find_instance_by_external_id(
            session,
            template_code=QUEUE_RECORD_TEMPLATE,
            key="idempotency_key",
            value=idempotency_key,
        )

    @staticmethod
    def _payload(instance: generic_instance) -> dict[str, Any]:
        payload = dict(from_json_addl(instance))
        payload.pop("properties", None)
        return payload

    @staticmethod
    def _analysis_graph_metadata() -> dict[str, Any]:
        return expected_fanout_graph(
            node_kind="ursa_analysis",
            relationship_type="analysis_artifact",
            expected_fanout_max=250,
        )

    @staticmethod
    def _validate_queue_name(queue_name: str) -> str:
        normalized = str(queue_name or "").strip()
        if normalized not in BETA_QUEUE_NAMES:
            raise ValueError(f"Unsupported Ursa beta queue: {queue_name}")
        return normalized

    @staticmethod
    def _queue_refs(
        *,
        object_euid: str,
        object_type: str,
        related_euids: dict[str, str],
        timestamp: str,
    ) -> list[dict[str, Any] | None]:
        refs: list[dict[str, Any] | None] = [
            explicit_ref(
                service="ursa",
                relationship_type=f"queues_{object_type or 'object'}",
                target_euid=object_euid,
                field_path="object_euid",
                timestamp=timestamp,
                target_kind=object_type or "object",
            )
        ]
        for field_path, target_euid in related_euids.items():
            service = "ursa"
            relationship_type = f"related_{field_path}"
            target_kind = field_path
            if field_path in QUEUE_RELATED_EUID_GRAPH_REFS:
                service, relationship_type, target_kind = QUEUE_RELATED_EUID_GRAPH_REFS[field_path]
            refs.append(
                explicit_ref(
                    service=service,
                    relationship_type=relationship_type,
                    target_euid=target_euid,
                    field_path=f"related_euids.{field_path}",
                    timestamp=timestamp,
                    target_kind=target_kind,
                )
            )
        return refs

    @staticmethod
    def _resolved_context_refs(
        resolution: RunResolution, *, timestamp: str
    ) -> list[dict[str, Any] | None]:
        return [
            explicit_ref(
                service="bloom",
                relationship_type="uses_bloom_run",
                target_euid=resolution.run_euid,
                field_path="run_euid",
                timestamp=timestamp,
                target_kind="run",
            ),
            explicit_ref(
                service="bloom",
                relationship_type="uses_bloom_library",
                target_euid=resolution.sequenced_library_assignment_euid,
                field_path="sequenced_library_assignment_euid",
                timestamp=timestamp,
                target_kind="sequenced_library_assignment",
            ),
            explicit_ref(
                service="bloom",
                relationship_type="uses_bloom_pool",
                target_euid=resolution.sequencing_pool_euid,
                field_path="sequencing_pool_euid",
                timestamp=timestamp,
                target_kind="sequencing_pool",
            ),
            explicit_ref(
                service="atlas",
                relationship_type="for_atlas_trf",
                target_euid=resolution.atlas_trf_euid,
                field_path="atlas_trf_euid",
                timestamp=timestamp,
                target_kind="test_request_fulfillment",
            ),
            explicit_ref(
                service="atlas",
                relationship_type="for_atlas_test",
                target_euid=resolution.atlas_test_euid,
                field_path="atlas_test_euid",
                timestamp=timestamp,
                target_kind="test",
            ),
            explicit_ref(
                service="atlas",
                relationship_type="for_atlas_test",
                target_euid=resolution.atlas_test_fulfillment_item_euid,
                field_path="atlas_test_fulfillment_item_euid",
                timestamp=timestamp,
                target_kind="test_fulfillment_item",
            ),
        ]

    @staticmethod
    def _atlas_return_refs(
        atlas_return: dict[str, Any], *, timestamp: str
    ) -> list[dict[str, Any] | None]:
        refs: list[dict[str, Any] | None] = []
        for field_path in ("fulfillment_run_euid", "fulfillment_output_euid"):
            refs.append(
                explicit_ref(
                    service="atlas",
                    relationship_type="returned_to_atlas",
                    target_euid=atlas_return.get(field_path),
                    field_path=field_path,
                    timestamp=timestamp,
                    target_kind=field_path.removesuffix("_euid"),
                )
            )
        for index, artifact_euid in enumerate(list(atlas_return.get("artifact_euids") or [])):
            refs.append(
                explicit_ref(
                    service="dewey",
                    relationship_type="registered_result_artifact",
                    target_euid=artifact_euid,
                    field_path=f"artifact_euids[{index}]",
                    timestamp=timestamp,
                    target_kind="artifact",
                )
            )
        return refs

    def _artifact_from_instance(self, instance: generic_instance) -> AnalysisArtifact:
        payload = from_json_addl(instance)
        return AnalysisArtifact(
            artifact_euid=str(payload.get("artifact_euid") or instance.euid),
            artifact_type=str(payload.get("artifact_type") or ""),
            storage_uri=str(payload.get("storage_uri") or ""),
            filename=str(payload.get("filename") or ""),
            mime_type=str(payload.get("mime_type") or "") or None,
            checksum_sha256=str(payload.get("checksum_sha256") or "") or None,
            size_bytes=int(payload["size_bytes"])
            if payload.get("size_bytes") is not None
            else None,
            created_at=str(payload.get("created_at") or utc_now_iso()),
            metadata=dict(payload.get("metadata") or {}),
        )

    def _queue_record_from_instance(self, instance: generic_instance) -> UrsaQueueRecord:
        payload = from_json_addl(instance)
        return UrsaQueueRecord(
            queue_record_euid=str(instance.euid),
            queue_name=str(payload.get("queue_name") or ""),
            object_euid=str(payload.get("object_euid") or ""),
            object_type=str(payload.get("object_type") or ""),
            tenant_id=self._parse_tenant_uuid(payload.get("tenant_id")),
            state=str(payload.get("state") or instance.bstatus or ""),
            idempotency_key=str(payload.get("idempotency_key") or ""),
            metadata=dict(payload.get("metadata") or {}),
            related_euids={
                str(key): str(value)
                for key, value in dict(payload.get("related_euids") or {}).items()
                if str(value or "").strip()
            },
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or payload.get("created_at") or utc_now_iso()),
        )

    def _context_payload(self, session, analysis: generic_instance) -> dict[str, Any]:
        contexts = self.backend.list_children(
            session,
            parent=analysis,
            relationship_type="resolved_context",
        )
        if not contexts:
            return {}
        contexts.sort(key=lambda item: item.created_dt or item.modified_dt, reverse=True)
        return from_json_addl(contexts[0])

    def _atlas_return_payload(self, session, analysis: generic_instance) -> dict[str, Any]:
        events = self.backend.list_children(
            session,
            parent=analysis,
            relationship_type="atlas_return",
        )
        if not events:
            return {}
        events.sort(key=lambda item: item.created_dt or item.modified_dt, reverse=True)
        return from_json_addl(events[0])

    def _artifacts(self, session, analysis: generic_instance) -> list[AnalysisArtifact]:
        return [
            self._artifact_from_instance(child)
            for child in self.backend.list_children(
                session,
                parent=analysis,
                relationship_type="analysis_artifact",
            )
        ]

    def _record_from_instance(
        self,
        session,
        instance: generic_instance,
        artifacts: list[AnalysisArtifact],
    ) -> AnalysisRecord:
        payload = from_json_addl(instance)
        context = self._context_payload(session, instance)
        atlas_return = self._atlas_return_payload(session, instance)
        workset_euid = None
        list_parents = getattr(self.backend, "list_parents", None)
        if callable(list_parents):
            workset_parents = list_parents(
                session,
                child=instance,
                relationship_type="workset_analysis",
            )
            if workset_parents:
                workset_euid = str(workset_parents[0].euid)
        return AnalysisRecord(
            analysis_euid=str(instance.euid),
            workset_euid=workset_euid,
            run_euid=str(context.get("run_euid") or ""),
            flowcell_id=str(context.get("flowcell_id") or ""),
            lane=str(context.get("lane") or ""),
            library_barcode=str(context.get("library_barcode") or ""),
            sequenced_library_assignment_euid=str(
                context.get("sequenced_library_assignment_euid") or ""
            ),
            tenant_id=self._parse_tenant_uuid(context.get("tenant_id")),
            atlas_trf_euid=str(context.get("atlas_trf_euid") or ""),
            atlas_test_euid=str(context.get("atlas_test_euid") or ""),
            atlas_test_fulfillment_item_euid=str(
                context.get("atlas_test_fulfillment_item_euid") or ""
            ),
            analysis_type=str(payload.get("analysis_type") or ""),
            state=str(payload.get("state") or instance.bstatus),
            review_state=str(payload.get("review_state") or ReviewState.PENDING.value),
            result_status=str(payload.get("result_status") or "PENDING"),
            run_folder=str(payload.get("run_folder") or ""),
            internal_bucket=str(payload.get("internal_bucket") or ""),
            input_references=list(payload.get("input_references") or []),
            result_payload=dict(payload.get("result_payload") or {}),
            metadata=dict(payload.get("metadata") or {}),
            created_at=str(payload.get("created_at") or utc_now_iso()),
            updated_at=str(payload.get("updated_at") or payload.get("created_at") or utc_now_iso()),
            atlas_return=atlas_return,
            artifacts=artifacts,
        )

    def get_analysis(self, analysis_euid: str) -> AnalysisRecord | None:
        with self.backend.session_scope(commit=False) as session:
            analysis = self._find_analysis(session, analysis_euid)
            if analysis is None:
                return None
            return self._record_from_instance(session, analysis, self._artifacts(session, analysis))

    def list_analyses(
        self,
        *,
        tenant_id: uuid.UUID | None = None,
        workset_euid: str | None = None,
        limit: int = 200,
    ) -> list[AnalysisRecord]:
        with self.backend.session_scope(commit=False) as session:
            rows = self.backend.list_instances_by_template(
                session,
                template_code=ANALYSIS_TEMPLATE,
                limit=limit,
            )
            records: list[AnalysisRecord] = []
            for analysis in rows:
                record = self._record_from_instance(
                    session, analysis, self._artifacts(session, analysis)
                )
                if tenant_id and record.tenant_id != tenant_id:
                    continue
                if workset_euid and record.workset_euid != workset_euid:
                    continue
                records.append(record)
            return records

    def list_queue_records(
        self,
        *,
        queue_name: str,
        tenant_id: uuid.UUID | None = None,
        state: str | None = None,
        limit: int = 200,
    ) -> list[UrsaQueueRecord]:
        normalized_queue = self._validate_queue_name(queue_name)
        normalized_state = str(state or "").strip()
        with self.backend.session_scope(commit=False) as session:
            rows = self.backend.list_instances_by_template(
                session,
                template_code=QUEUE_RECORD_TEMPLATE,
                limit=limit,
            )
            records: list[UrsaQueueRecord] = []
            for row in rows:
                record = self._queue_record_from_instance(row)
                if record.queue_name != normalized_queue:
                    continue
                if tenant_id is not None and record.tenant_id != tenant_id:
                    continue
                if normalized_state and record.state != normalized_state:
                    continue
                records.append(record)
            return records

    def get_queue_record(self, queue_record_euid: str) -> UrsaQueueRecord | None:
        with self.backend.session_scope(commit=False) as session:
            record = self.backend.find_instance_by_euid(
                session,
                template_code=QUEUE_RECORD_TEMPLATE,
                value=queue_record_euid,
            )
            if record is None:
                return None
            return self._queue_record_from_instance(record)

    def create_queue_record(
        self,
        *,
        queue_name: str,
        object_euid: str,
        object_type: str,
        tenant_id: uuid.UUID,
        state: str,
        metadata: dict[str, Any] | None,
        related_euids: dict[str, str] | None,
        idempotency_key: str,
    ) -> UrsaQueueRecord:
        normalized_queue = self._validate_queue_name(queue_name)
        clean_object_euid = str(object_euid or "").strip()
        clean_object_type = str(object_type or "").strip()
        clean_state = str(state or "").strip() or "queued"
        clean_idempotency_key = str(idempotency_key or "").strip()
        if not clean_object_euid:
            raise ValueError("object_euid is required")
        if not clean_object_type:
            raise ValueError("object_type is required")
        if not clean_idempotency_key:
            raise ValueError("idempotency_key is required")
        with self.backend.session_scope(commit=True) as session:
            existing = self._find_queue_record_by_idempotency_key(
                session,
                clean_idempotency_key,
            )
            if existing is not None:
                return self._queue_record_from_instance(existing)
            now = utc_now_iso()
            compact_related = {
                str(key): str(value).strip()
                for key, value in dict(related_euids or {}).items()
                if str(value or "").strip()
            }
            record = self.backend.create_instance(
                session,
                QUEUE_RECORD_TEMPLATE,
                f"{normalized_queue}:{clean_object_euid}",
                json_addl=payload_with_tapdb_graph(
                    {
                        "queue_name": normalized_queue,
                        "object_euid": clean_object_euid,
                        "object_type": clean_object_type,
                        "tenant_id": str(tenant_id),
                        "state": clean_state,
                        "metadata": dict(metadata or {}),
                        "related_euids": compact_related,
                        "idempotency_key": clean_idempotency_key,
                        "created_at": now,
                        "updated_at": now,
                    },
                    refs=self._queue_refs(
                        object_euid=clean_object_euid,
                        object_type=clean_object_type,
                        related_euids=compact_related,
                        timestamp=now,
                    ),
                    timestamp=now,
                    graph=expected_fanout_graph(
                        node_kind="ursa_beta_queue_record",
                        relationship_type="queue_record_subject",
                        expected_fanout_max=16,
                    ),
                ),
                bstatus=clean_state,
                tenant_id=tenant_id,
            )
            return self._queue_record_from_instance(record)

    def transition_queue_record(
        self,
        queue_record_euid: str,
        *,
        state: str,
        metadata: dict[str, Any] | None = None,
    ) -> UrsaQueueRecord:
        clean_state = str(state or "").strip()
        if not clean_state:
            raise ValueError("state is required")
        with self.backend.session_scope(commit=True) as session:
            record = self.backend.find_instance_by_euid(
                session,
                template_code=QUEUE_RECORD_TEMPLATE,
                value=queue_record_euid,
                for_update=True,
            )
            if record is None:
                raise KeyError(f"queue record not found: {queue_record_euid}")
            payload = self._payload(record)
            payload["state"] = clean_state
            payload["updated_at"] = utc_now_iso()
            if metadata:
                merged = dict(payload.get("metadata") or {})
                merged.update(metadata)
                payload["metadata"] = merged
            history = list(payload.get("history") or [])
            history.append({"timestamp": payload["updated_at"], "state": clean_state})
            payload["history"] = history
            record.bstatus = clean_state
            replace_instance_properties(record, payload)
            session.flush()
            return self._queue_record_from_instance(record)

    def ingest_analysis(
        self,
        *,
        resolution: RunResolution,
        analysis_type: str,
        internal_bucket: str,
        idempotency_key: str,
        input_references: list[dict[str, Any]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AnalysisRecord:
        with self.backend.session_scope(commit=True) as session:
            existing = self._find_analysis_by_ingest_key(session, idempotency_key)
            if existing is not None:
                return self._record_from_instance(
                    session, existing, self._artifacts(session, existing)
                )

            now = utc_now_iso()
            analysis = self.backend.create_instance(
                session,
                ANALYSIS_TEMPLATE,
                f"analysis:{resolution.run_euid}:{resolution.lane}:{resolution.library_barcode}",
                json_addl=payload_with_tapdb_graph(
                    {
                        "analysis_type": analysis_type,
                        "state": AnalysisState.INGESTED.value,
                        "review_state": ReviewState.PENDING.value,
                        "result_status": "PENDING",
                        "internal_bucket": internal_bucket,
                        "run_folder": f"s3://{internal_bucket}/{resolution.run_euid}/",
                        "input_references": list(input_references or []),
                        "metadata": dict(metadata or {}),
                        "ingest_idempotency_key": idempotency_key,
                        "created_at": now,
                        "updated_at": now,
                        "result_payload": {},
                        "history": [
                            {
                                "timestamp": now,
                                "state": AnalysisState.INGESTED.value,
                                "reason": "INGESTED",
                            }
                        ],
                    },
                    refs=dewey_refs_from_inputs(
                        input_references=input_references,
                        timestamp=now,
                    ),
                    timestamp=now,
                    graph=self._analysis_graph_metadata(),
                ),
                bstatus=AnalysisState.INGESTED.value,
                tenant_id=resolution.tenant_id,
            )
            context_payload = {
                "run_euid": resolution.run_euid,
                "flowcell_id": resolution.flowcell_id,
                "lane": resolution.lane,
                "library_barcode": resolution.library_barcode,
                "sequenced_library_assignment_euid": (resolution.sequenced_library_assignment_euid),
                "tenant_id": str(resolution.tenant_id),
                "atlas_trf_euid": resolution.atlas_trf_euid,
                "atlas_test_euid": resolution.atlas_test_euid,
                "atlas_test_fulfillment_item_euid": (resolution.atlas_test_fulfillment_item_euid),
                "created_at": now,
            }
            if resolution.sequencing_pool_euid:
                context_payload["sequencing_pool_euid"] = resolution.sequencing_pool_euid
            context = self.backend.create_instance(
                session,
                RESOLVED_CONTEXT_TEMPLATE,
                f"context:{analysis.euid}",
                json_addl=payload_with_tapdb_graph(
                    context_payload,
                    refs=self._resolved_context_refs(resolution, timestamp=now),
                    timestamp=now,
                    graph=expected_fanout_graph(
                        node_kind="ursa_resolved_context",
                        relationship_type="resolved_context",
                        expected_fanout_max=10,
                    ),
                ),
                bstatus="active",
                tenant_id=resolution.tenant_id,
            )
            self.backend.create_lineage(
                session,
                parent=analysis,
                child=context,
                relationship_type="resolved_context",
            )
            return self._record_from_instance(session, analysis, [])

    def update_analysis_state(
        self,
        analysis_euid: str,
        *,
        state: AnalysisState,
        result_status: str | None = None,
        result_payload: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        reason: str | None = None,
    ) -> AnalysisRecord:
        with self.backend.session_scope(commit=True) as session:
            analysis = self._find_analysis(session, analysis_euid, for_update=True)
            if analysis is None:
                raise KeyError(f"analysis not found: {analysis_euid}")
            payload = self._payload(analysis)
            payload["state"] = state.value
            payload["updated_at"] = utc_now_iso()
            if result_status is not None:
                payload["result_status"] = result_status
            if result_payload is not None:
                payload["result_payload"] = dict(result_payload)
            if metadata:
                merged = dict(payload.get("metadata") or {})
                merged.update(metadata)
                payload["metadata"] = merged
            history = list(payload.get("history") or [])
            history.append(
                {
                    "timestamp": payload["updated_at"],
                    "state": state.value,
                    "reason": reason or state.value,
                }
            )
            payload["history"] = history
            analysis.bstatus = state.value
            replace_instance_properties(analysis, payload)
            session.flush()
            return self._record_from_instance(session, analysis, self._artifacts(session, analysis))

    def add_artifact(
        self,
        analysis_euid: str,
        *,
        artifact_type: str,
        storage_uri: str,
        filename: str,
        mime_type: str | None = None,
        checksum_sha256: str | None = None,
        size_bytes: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AnalysisArtifact:
        with self.backend.session_scope(commit=True) as session:
            analysis = self._find_analysis(session, analysis_euid, for_update=True)
            if analysis is None:
                raise KeyError(f"analysis not found: {analysis_euid}")
            dewey_artifact_euid = str((metadata or {}).get("dewey_artifact_euid") or "").strip()
            if not dewey_artifact_euid:
                raise ValueError("dewey_artifact_euid is required for persisted analysis artifacts")
            for child in self.backend.list_children(
                session,
                parent=analysis,
                relationship_type="analysis_artifact",
            ):
                payload = from_json_addl(child)
                if str(payload.get("artifact_euid") or "") == dewey_artifact_euid:
                    return self._artifact_from_instance(child)

            artifact_created_at = utc_now_iso()
            artifact = self.backend.create_instance(
                session,
                ARTIFACT_TEMPLATE,
                filename,
                json_addl=payload_with_tapdb_graph(
                    {
                        "artifact_euid": dewey_artifact_euid,
                        "artifact_type": artifact_type,
                        "storage_uri": storage_uri,
                        "filename": filename,
                        "mime_type": mime_type,
                        "checksum_sha256": checksum_sha256,
                        "size_bytes": size_bytes,
                        "metadata": dict(metadata or {}),
                        "created_at": artifact_created_at,
                    },
                    refs=[
                        explicit_ref(
                            service="dewey",
                            relationship_type="registered_result_artifact",
                            target_euid=dewey_artifact_euid,
                            field_path="artifact_euid",
                            timestamp=artifact_created_at,
                            target_kind="artifact",
                        )
                    ],
                    timestamp=artifact_created_at,
                ),
                bstatus="active",
            )
            self.backend.create_lineage(
                session,
                parent=analysis,
                child=artifact,
                relationship_type="analysis_artifact",
            )
            payload = self._payload(analysis)
            payload["state"] = AnalysisState.REVIEW_PENDING.value
            payload["updated_at"] = utc_now_iso()
            history = list(payload.get("history") or [])
            history.append(
                {
                    "timestamp": payload["updated_at"],
                    "state": AnalysisState.REVIEW_PENDING.value,
                    "reason": "ARTIFACT_ADDED",
                }
            )
            payload["history"] = history
            analysis.bstatus = AnalysisState.REVIEW_PENDING.value
            replace_instance_properties(analysis, payload)
            session.flush()
            return self._artifact_from_instance(artifact)

    def set_review_state(
        self,
        analysis_euid: str,
        *,
        review_state: ReviewState,
        reviewer: str | None = None,
        notes: str | None = None,
    ) -> AnalysisRecord:
        with self.backend.session_scope(commit=True) as session:
            analysis = self._find_analysis(session, analysis_euid, for_update=True)
            if analysis is None:
                raise KeyError(f"analysis not found: {analysis_euid}")
            payload = self._payload(analysis)
            payload["review_state"] = review_state.value
            payload["updated_at"] = utc_now_iso()
            if review_state == ReviewState.APPROVED:
                payload["state"] = AnalysisState.REVIEWED.value
                analysis.bstatus = AnalysisState.REVIEWED.value
            elif review_state == ReviewState.REJECTED:
                payload["state"] = AnalysisState.FAILED.value
                payload["result_status"] = "REJECTED"
                analysis.bstatus = AnalysisState.FAILED.value
            history = list(payload.get("history") or [])
            history.append(
                {
                    "timestamp": payload["updated_at"],
                    "state": str(payload.get("state") or analysis.bstatus),
                    "reason": f"REVIEW_{review_state.value}",
                }
            )
            payload["history"] = history
            replace_instance_properties(analysis, payload)
            session.flush()

            event = self.backend.create_instance(
                session,
                REVIEW_EVENT_TEMPLATE,
                f"review:{analysis_euid}:{payload['updated_at']}",
                json_addl={
                    "review_state": review_state.value,
                    "reviewer": reviewer,
                    "notes": notes,
                    "timestamp": payload["updated_at"],
                },
                bstatus=review_state.value,
            )
            self.backend.create_lineage(
                session,
                parent=analysis,
                child=event,
                relationship_type="review_event",
            )
            return self._record_from_instance(session, analysis, self._artifacts(session, analysis))

    def mark_returned(
        self,
        analysis_euid: str,
        *,
        atlas_return: dict[str, Any],
        idempotency_key: str,
    ) -> AnalysisRecord:
        with self.backend.session_scope(commit=True) as session:
            analysis = self._find_analysis(session, analysis_euid, for_update=True)
            if analysis is None:
                raise KeyError(f"analysis not found: {analysis_euid}")
            payload = self._payload(analysis)
            if (
                str(payload.get("review_state") or ReviewState.PENDING.value)
                != ReviewState.APPROVED.value
            ):
                raise ValueError("Analysis cannot be returned before manual approval")

            for event in self.backend.list_children(
                session,
                parent=analysis,
                relationship_type="atlas_return",
            ):
                event_payload = from_json_addl(event)
                if str(event_payload.get("idempotency_key") or "") == idempotency_key:
                    if payload.get("state") != AnalysisState.RETURNED.value:
                        returned_at = str(event_payload.get("returned_at") or utc_now_iso())
                        payload["state"] = AnalysisState.RETURNED.value
                        payload["result_status"] = str(
                            event_payload.get("result_status")
                            or payload.get("result_status")
                            or "RETURNED"
                        )
                        payload["updated_at"] = returned_at
                        history = list(payload.get("history") or [])
                        history.append(
                            {
                                "timestamp": returned_at,
                                "state": AnalysisState.RETURNED.value,
                                "reason": "ATLAS_RETURNED_REPLAY",
                            }
                        )
                        payload["history"] = history
                        analysis.bstatus = AnalysisState.RETURNED.value
                        replace_instance_properties(analysis, payload)
                        session.flush()
                    return self._record_from_instance(
                        session, analysis, self._artifacts(session, analysis)
                    )

            returned_at = utc_now_iso()
            payload["state"] = AnalysisState.RETURNED.value
            payload["result_status"] = str(
                atlas_return.get("result_status") or payload.get("result_status") or "RETURNED"
            )
            payload["updated_at"] = returned_at
            history = list(payload.get("history") or [])
            history.append(
                {
                    "timestamp": returned_at,
                    "state": AnalysisState.RETURNED.value,
                    "reason": "ATLAS_RETURNED",
                }
            )
            payload["history"] = history
            analysis.bstatus = AnalysisState.RETURNED.value
            replace_instance_properties(analysis, payload)
            session.flush()

            event = self.backend.create_instance(
                session,
                RETURN_EVENT_TEMPLATE,
                f"atlas-return:{analysis_euid}:{returned_at}",
                json_addl=payload_with_tapdb_graph(
                    {
                        **dict(atlas_return),
                        "idempotency_key": idempotency_key,
                        "returned_at": returned_at,
                    },
                    refs=self._atlas_return_refs(atlas_return, timestamp=returned_at),
                    timestamp=returned_at,
                ),
                bstatus="returned",
            )
            self.backend.create_lineage(
                session,
                parent=analysis,
                child=event,
                relationship_type="atlas_return",
            )
            return self._record_from_instance(session, analysis, self._artifacts(session, analysis))
