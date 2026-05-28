from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
import uuid

from daylib_ursa.analysis_store import AnalysisStore, ReviewState, RunResolution
from daylib_ursa.tapdb_graph import from_json_addl

ANALYSIS_TEMPLATE = "RGX/analysis/run-linked/1.0/"
ARTIFACT_TEMPLATE = "RGX/artifact/analysis-output/1.0/"
ATLAS_RETURN_TEMPLATE = "RGX/analysis/atlas-return/1.0/"
RESOLVED_CONTEXT_TEMPLATE = "RGX/reference/sequenced-assignment-context/1.0/"

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _graph_payload(instance):
    return instance.json_addl["properties"]["external_payload"]["tapdb_graph"]


def _created_instance(backend, template_code: str):
    for created_template_code, _name, instance in backend.created:
        if created_template_code == template_code:
            return instance
    raise AssertionError(f"created instance not found for {template_code}")


class _FakeBackend:
    def __init__(self) -> None:
        self.created = []
        self.lineages = []

    @contextmanager
    def session_scope(self, *, commit: bool):
        _ = commit
        yield SimpleNamespace(flush=lambda: None)

    def ensure_templates(self, session) -> None:
        _ = session

    def find_instance_by_external_id(self, session, *, template_code, key, value):
        _ = session
        for created_template_code, _name, instance in self.created:
            if created_template_code != template_code:
                continue
            if str(from_json_addl(instance).get(key) or "") == value:
                return instance
        return None

    def find_instance_by_euid(self, session, *, template_code, value, for_update=False):
        _ = (session, template_code, for_update)
        for created_template_code, _name, instance in self.created:
            if created_template_code == template_code and str(instance.euid) == value:
                return instance
        return None

    def create_instance(self, session, template_code, name, *, json_addl, bstatus, tenant_id=None):
        _ = session
        instance = SimpleNamespace(
            euid=f"{template_code}:{len(self.created) + 1}",
            name=name,
            json_addl=dict(json_addl),
            bstatus=bstatus,
            created_dt=None,
            modified_dt=None,
            tenant_id=tenant_id,
        )
        self.created.append((template_code, name, instance))
        return instance

    def create_lineage(self, session, *, parent, child, relationship_type):
        _ = session
        self.lineages.append((parent, child, relationship_type))

    def list_children(self, session, *, parent, relationship_type):
        _ = session
        return [
            child
            for source, child, rel in self.lineages
            if source is parent and rel == relationship_type
        ]


class _WrappedContextBackend(_FakeBackend):
    def create_instance(self, session, template_code, name, *, json_addl, bstatus, tenant_id=None):
        payload = dict(json_addl)
        if (
            template_code == "RGX/reference/sequenced-assignment-context/1.0/"
            and "properties" not in payload
        ):
            payload = {"properties": payload}
        return super().create_instance(
            session,
            template_code,
            name,
            json_addl=payload,
            bstatus=bstatus,
            tenant_id=tenant_id,
        )


class _WrappedAnalysisBackend(_FakeBackend):
    def create_instance(self, session, template_code, name, *, json_addl, bstatus, tenant_id=None):
        payload = dict(json_addl)
        if template_code == "RGX/analysis/run-linked/1.0/" and "properties" not in payload:
            payload = {"properties": payload}
        return super().create_instance(
            session,
            template_code,
            name,
            json_addl=payload,
            bstatus=bstatus,
            tenant_id=tenant_id,
        )


def test_ingest_analysis_keeps_relationship_truth_on_context_reference():
    store = AnalysisStore.__new__(AnalysisStore)
    store.backend = _FakeBackend()

    record = store.ingest_analysis(
        resolution=RunResolution(
            run_euid="RUN-1",
            flowcell_id="FLOW-1",
            lane="1",
            library_barcode="LIB-1",
            sequenced_library_assignment_euid="SQA-1",
            tenant_id=TENANT_ID,
            atlas_trf_euid="TRF-1",
            atlas_test_euid="TST-1",
            atlas_test_fulfillment_item_euid="TPC-1",
        ),
        analysis_type="germline",
        internal_bucket="analysis-bucket",
        idempotency_key="idem-1",
        input_references=[
            {
                "reference_type": "s3_uri",
                "value": "s3://analysis-bucket/RUN-1/read1.fastq.gz",
                "storage_uri": "s3://analysis-bucket/RUN-1/read1.fastq.gz",
            }
        ],
        metadata={"pipeline": "beta"},
    )

    analysis_template, _analysis_name, analysis = store.backend.created[0]
    context_template, _context_name, context = store.backend.created[1]

    assert analysis_template == "RGX/analysis/run-linked/1.0/"
    assert context_template == "RGX/reference/sequenced-assignment-context/1.0/"

    analysis_payload = from_json_addl(analysis)
    assert "run_euid" not in analysis_payload
    assert "sequenced_library_assignment_euid" not in analysis_payload
    assert "atlas_trf_euid" not in analysis_payload
    assert "atlas_test_euid" not in analysis_payload
    assert "atlas_test_fulfillment_item_euid" not in analysis_payload

    context_payload = from_json_addl(context)
    assert context_payload["run_euid"] == "RUN-1"
    assert context_payload["sequenced_library_assignment_euid"] == "SQA-1"
    assert context_payload["atlas_trf_euid"] == "TRF-1"
    assert context_payload["atlas_test_euid"] == "TST-1"
    assert context_payload["atlas_test_fulfillment_item_euid"] == "TPC-1"

    assert store.backend.lineages[0][2] == "resolved_context"
    assert record.run_euid == "RUN-1"
    assert record.tenant_id == TENANT_ID
    assert record.atlas_test_fulfillment_item_euid == "TPC-1"


def test_ingest_analysis_reads_wrapped_context_payloads():
    store = AnalysisStore.__new__(AnalysisStore)
    store.backend = _WrappedContextBackend()

    record = store.ingest_analysis(
        resolution=RunResolution(
            run_euid="RUN-2",
            flowcell_id="FLOW-2",
            lane="2",
            library_barcode="LIB-2",
            sequenced_library_assignment_euid="SQA-2",
            tenant_id=TENANT_ID,
            atlas_trf_euid="TRF-2",
            atlas_test_euid="TST-2",
            atlas_test_fulfillment_item_euid="TPC-2",
        ),
        analysis_type="somatic",
        internal_bucket="analysis-bucket",
        idempotency_key="idem-2",
    )

    assert record.run_euid == "RUN-2"
    assert record.flowcell_id == "FLOW-2"
    assert record.sequenced_library_assignment_euid == "SQA-2"
    assert record.tenant_id == TENANT_ID
    assert record.atlas_test_fulfillment_item_euid == "TPC-2"


def test_wrapped_analysis_payload_updates_survive_review_and_return():
    store = AnalysisStore.__new__(AnalysisStore)
    store.backend = _WrappedAnalysisBackend()

    record = store.ingest_analysis(
        resolution=RunResolution(
            run_euid="RUN-3",
            flowcell_id="FLOW-3",
            lane="3",
            library_barcode="LIB-3",
            sequenced_library_assignment_euid="SQA-3",
            tenant_id=TENANT_ID,
            atlas_trf_euid="TRF-3",
            atlas_test_euid="TST-3",
            atlas_test_fulfillment_item_euid="TPC-3",
        ),
        analysis_type="wgs",
        internal_bucket="analysis-bucket",
        idempotency_key="idem-3",
    )

    reviewed = store.set_review_state(
        record.analysis_euid,
        review_state=ReviewState.APPROVED,
        reviewer="qa@example.com",
    )

    assert reviewed.review_state == ReviewState.APPROVED.value
    assert reviewed.state == "REVIEWED"

    returned = store.mark_returned(
        record.analysis_euid,
        atlas_return={"fulfillment_output_euid": "RES-1"},
        idempotency_key="return-1",
    )

    assert returned.review_state == ReviewState.APPROVED.value
    assert returned.state == "RETURNED"
    assert returned.atlas_return["fulfillment_output_euid"] == "RES-1"

    analysis = _created_instance(store.backend, ANALYSIS_TEMPLATE)
    payload = from_json_addl(analysis)
    payload["state"] = "REVIEWED"
    analysis.bstatus = "REVIEWED"
    analysis.json_addl = {"properties": payload}

    replayed = store.mark_returned(
        record.analysis_euid,
        atlas_return={"fulfillment_output_euid": "RES-1"},
        idempotency_key="return-1",
    )

    assert replayed.state == "RETURNED"


def test_analysis_store_writes_explicit_tapdb_graph_refs_and_timestamps():
    store = AnalysisStore.__new__(AnalysisStore)
    store.backend = _FakeBackend()

    record = store.ingest_analysis(
        resolution=RunResolution(
            run_euid="RUN-4",
            flowcell_id="FLOW-4",
            lane="4",
            library_barcode="LIB-4",
            sequenced_library_assignment_euid="SQA-4",
            tenant_id=TENANT_ID,
            atlas_trf_euid="TRF-4",
            atlas_test_euid="TST-4",
            atlas_test_fulfillment_item_euid="TPC-4",
            sequencing_pool_euid="POOL-4",
        ),
        analysis_type="wgs",
        internal_bucket="analysis-bucket",
        idempotency_key="idem-4",
        input_references=[
            {"reference_type": "artifact_euid", "value": "AT-INPUT-1"},
            {
                "reference_type": "artifact_set_euid",
                "value": "AS-INPUT-1",
                "artifact_euids": ["AT-INPUT-2"],
            },
        ],
    )
    artifact = store.add_artifact(
        record.analysis_euid,
        artifact_type="vcf",
        storage_uri="s3://analysis-bucket/results.vcf.gz",
        filename="results.vcf.gz",
        metadata={"dewey_artifact_euid": "AT-RESULT-1"},
    )
    store.set_review_state(
        record.analysis_euid,
        review_state=ReviewState.APPROVED,
        reviewer="qa@example.test",
    )
    store.mark_returned(
        record.analysis_euid,
        atlas_return={
            "fulfillment_run_euid": "ASR-4",
            "fulfillment_output_euid": "RES-4",
            "artifact_euids": [artifact.artifact_euid],
        },
        idempotency_key="return-4",
    )

    analysis = _created_instance(store.backend, ANALYSIS_TEMPLATE)
    context = _created_instance(store.backend, RESOLVED_CONTEXT_TEMPLATE)
    artifact_instance = _created_instance(store.backend, ARTIFACT_TEMPLATE)
    atlas_return = _created_instance(store.backend, ATLAS_RETURN_TEMPLATE)

    analysis_graph = _graph_payload(analysis)
    assert isinstance(analysis_graph, list)
    assert not any(ref["inferred"] for ref in analysis_graph)
    assert {(ref["relationship_type"], ref["target_euid"]) for ref in analysis_graph} >= {
        ("uses_fastq_artifact", "AT-INPUT-1"),
        ("uses_fastq_artifact", "AS-INPUT-1"),
        ("uses_fastq_artifact", "AT-INPUT-2"),
    }
    assert analysis.json_addl["properties"]["graph"]["fanout"] == {
        "classification": "expected",
        "relationship_type": "analysis_artifact",
        "expected_fanout_max": 250,
    }

    context_graph = _graph_payload(context)
    assert isinstance(context_graph, list)
    assert {(ref["relationship_type"], ref["target_euid"]) for ref in context_graph} >= {
        ("uses_bloom_run", "RUN-4"),
        ("uses_bloom_library", "SQA-4"),
        ("uses_bloom_pool", "POOL-4"),
        ("for_atlas_trf", "TRF-4"),
        ("for_atlas_test", "TST-4"),
        ("for_atlas_test", "TPC-4"),
    }
    assert from_json_addl(context)["sequencing_pool_euid"] == "POOL-4"

    artifact_graph = _graph_payload(artifact_instance)
    assert isinstance(artifact_graph, list)
    assert artifact_graph[0]["relationship_type"] == "registered_result_artifact"
    assert artifact_graph[0]["target_euid"] == "AT-RESULT-1"
    assert artifact_graph[0]["recorded_at"] == from_json_addl(artifact_instance)["created_at"]

    atlas_return_graph = _graph_payload(atlas_return)
    assert isinstance(atlas_return_graph, list)
    assert {(ref["relationship_type"], ref["target_euid"]) for ref in atlas_return_graph} >= {
        ("returned_to_atlas", "ASR-4"),
        ("returned_to_atlas", "RES-4"),
        ("registered_result_artifact", "AT-RESULT-1"),
    }
