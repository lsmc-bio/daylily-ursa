from __future__ import annotations

import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from daylib_ursa.tapdb_graph import from_json_addl
from daylib_ursa.resource_store import (
    ANALYSIS_JOB_TEMPLATE,
    CLUSTER_JOB_TEMPLATE,
    COMPUTE_CLUSTER_TEMPLATE,
    MANIFEST_TEMPLATE,
    STAGING_JOB_TEMPLATE,
    WORKSET_TEMPLATE,
    ResourceStore,
)

TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
USER_ID = "00000000-0000-0000-0000-000000000101"


@dataclass
class _Instance:
    uid: int
    euid: str
    name: str
    json_addl: dict
    bstatus: str
    template_code: str
    created_dt: datetime
    modified_dt: datetime
    tenant_id: uuid.UUID | None = None
    polymorphic_discriminator: str = "generic_instance"


class MemoryBackend:
    def __init__(self) -> None:
        self._uid = 0
        self.instances: list[_Instance] = []
        self.lineages: list[tuple[_Instance, _Instance, str]] = []

    @contextmanager
    def session_scope(self, commit: bool = False):
        _ = commit
        yield object()

    def create_instance(
        self,
        session,
        template_code: str,
        name: str,
        *,
        json_addl,
        bstatus,
        tenant_id: uuid.UUID | None = None,
        singleton: bool = False,
    ):
        _ = (session, singleton)
        self._uid += 1
        prefix = {
            WORKSET_TEMPLATE: "WS",
            MANIFEST_TEMPLATE: "MF",
            CLUSTER_JOB_TEMPLATE: "CJ",
            COMPUTE_CLUSTER_TEMPLATE: "CC",
            "RGX/cluster/ephemeral-job-event/1.0/": "CJE",
            ANALYSIS_JOB_TEMPLATE: "AJ",
            "RGX/analysis/launch-job-event/1.0/": "AJE",
            STAGING_JOB_TEMPLATE: "SJ",
            "RGX/staging/job-event/1.0/": "SJE",
        }.get(template_code, "GI")
        now = datetime.now(timezone.utc)
        instance = _Instance(
            uid=self._uid,
            euid=f"{prefix}-{self._uid}",
            name=name,
            json_addl=dict(json_addl),
            bstatus=bstatus,
            template_code=template_code,
            created_dt=now,
            modified_dt=now,
            tenant_id=tenant_id,
        )
        self.instances.append(instance)
        return instance

    def create_lineage(self, session, *, parent, child, relationship_type, name=None):
        _ = (session, name)
        self.lineages.append((parent, child, relationship_type))

    def list_children(self, session, *, parent, relationship_type=None):
        _ = session
        return [
            child
            for source, child, rel in self.lineages
            if source is parent and (relationship_type is None or rel == relationship_type)
        ]

    def find_instance_by_euid(
        self, session, *, template_code: str, value: str, for_update: bool = False
    ):
        _ = (session, for_update)
        for instance in self.instances:
            if instance.template_code == template_code and instance.euid == value:
                return instance
        return None

    def list_instances_by_property(
        self, session, *, template_code: str, key: str, value: str, limit: int = 200
    ):
        _ = session
        rows = [
            instance
            for instance in self.instances
            if instance.template_code == template_code
            and str(from_json_addl(instance).get(key) or "") == value
        ]
        return list(reversed(rows))[:limit]

    def list_instances_by_template(self, session, *, template_code: str, limit: int = 100):
        _ = session
        rows = [instance for instance in self.instances if instance.template_code == template_code]
        return list(reversed(rows))[:limit]

    def update_instance_json(self, session, instance, updates):
        _ = session
        properties = instance.json_addl.get("properties")
        if isinstance(properties, dict):
            properties.update(dict(updates))
        else:
            instance.json_addl.update(dict(updates))
        instance.modified_dt = datetime.now(timezone.utc)


def _store_with_backend() -> tuple[ResourceStore, MemoryBackend]:
    backend = MemoryBackend()
    return ResourceStore(backend=backend), backend


def _store_with_workset_manifest() -> tuple[ResourceStore, MemoryBackend, _Instance, _Instance]:
    store, backend = _store_with_backend()
    with backend.session_scope(commit=True) as session:
        workset = backend.create_instance(
            session,
            WORKSET_TEMPLATE,
            "workset",
            json_addl={
                "tenant_id": str(TENANT_ID),
                "owner_user_id": USER_ID,
                "state": "ACTIVE",
                "created_at": "2026-05-11T00:00:00Z",
                "updated_at": "2026-05-11T00:00:00Z",
            },
            bstatus="ACTIVE",
            tenant_id=TENANT_ID,
        )
        manifest = backend.create_instance(
            session,
            MANIFEST_TEMPLATE,
            "manifest",
            json_addl={
                "workset_euid": workset.euid,
                "tenant_id": str(TENANT_ID),
                "owner_user_id": USER_ID,
                "state": "ACTIVE",
                "created_at": "2026-05-11T00:00:00Z",
                "updated_at": "2026-05-11T00:00:00Z",
            },
            bstatus="ACTIVE",
            tenant_id=TENANT_ID,
        )
    return store, backend, workset, manifest


def _instance_for_euid(backend: MemoryBackend, euid: str) -> _Instance:
    for instance in backend.instances:
        if instance.euid == euid:
            return instance
    raise AssertionError(f"instance not found: {euid}")


def _assert_no_revision_objects(backend: MemoryBackend, instance: _Instance) -> None:
    assert backend.list_children(object(), parent=instance, relationship_type="revision") == []
    assert not any(rel == "revision" for _parent, _child, rel in backend.lineages)
    assert not any("revision" in instance.template_code for instance in backend.instances)


def _graph_payload(instance: _Instance) -> dict:
    return instance.json_addl["properties"]["external_payload"]["tapdb_graph"]


def test_cluster_job_statuses_mutate_canonical_job_and_keep_events_as_events() -> None:
    store, backend = _store_with_backend()

    queued = store.create_cluster_job(
        cluster_name="cluster-1",
        region="us-west-2",
        region_az="us-west-2a",
        tenant_id=TENANT_ID,
        owner_user_id=USER_ID,
        sponsor_user_id=USER_ID,
        request={"size": "small"},
    )
    running = store.update_cluster_job_status(
        job_euid=queued.job_euid,
        state="RUNNING",
        created_by=USER_ID,
        started_at="2026-05-11T00:01:00Z",
        cluster={"cluster_id": "c-1"},
    )
    completed = store.update_cluster_job_status(
        job_euid=queued.job_euid,
        state="COMPLETED",
        created_by=USER_ID,
        completed_at="2026-05-11T00:02:00Z",
        return_code=0,
        output_summary="created",
    )
    failed = store.update_cluster_job_status(
        job_euid=queued.job_euid,
        state="FAILED",
        created_by=USER_ID,
        return_code=1,
        error="retry failed",
    )
    event = store.add_cluster_job_event(
        job_euid=queued.job_euid,
        event_type="status",
        status="FAILED",
        summary="failure recorded",
        created_by=USER_ID,
    )

    assert [queued.job_euid, running.job_euid, completed.job_euid, failed.job_euid] == [
        queued.job_euid
    ] * 4
    assert [
        instance.euid
        for instance in backend.instances
        if instance.template_code == CLUSTER_JOB_TEMPLATE
    ] == [queued.job_euid]
    job = _instance_for_euid(backend, queued.job_euid)
    job_payload = from_json_addl(job)
    assert job_payload["state"] == "FAILED"
    assert job_payload["started_at"] == "2026-05-11T00:01:00Z"
    assert job_payload["completed_at"] == "2026-05-11T00:02:00Z"
    assert job_payload["return_code"] == 1
    assert job_payload["error"] == "retry failed"
    _assert_no_revision_objects(backend, job)
    event_children = backend.list_children(object(), parent=job, relationship_type="event")
    assert [child.euid for child in event_children] == [event.event_euid]


def test_compute_cluster_links_to_explicit_cluster_job() -> None:
    store, backend = _store_with_backend()

    cluster = store.create_compute_cluster(
        display_name="Majors Cluster",
        cluster_name="majors-cluster",
        cluster_type="aws_parallelcluster_slurm",
        region="us-west-2",
        tenant_id=TENANT_ID,
        owner_user_id=USER_ID,
        metadata={"region_az": "us-west-2a"},
    )
    job = store.create_cluster_job(
        cluster_euid=cluster.cluster_euid,
        job_name="dy-r help smoke",
        cluster_name=cluster.cluster_name,
        region=cluster.region,
        region_az="us-west-2a",
        tenant_id=TENANT_ID,
        owner_user_id=USER_ID,
        sponsor_user_id=USER_ID,
        request={"command": "dy-r help"},
        job_type="slurm",
        analysis_job_euid="AJ-1",
        scheduler_job_id="12345",
    )

    assert cluster.cluster_euid == "CC-1"
    assert cluster.cluster_type == "aws_parallelcluster_slurm"
    assert job.cluster_job_euid == job.job_euid
    assert job.job_name == "dy-r help smoke"
    assert job.cluster_euid == cluster.cluster_euid
    assert job.job_type == "slurm"
    assert job.analysis_job_euid == "AJ-1"
    assert job.scheduler_job_id == "12345"
    assert job.request == {"command": "dy-r help"}

    cluster_instance = _instance_for_euid(backend, cluster.cluster_euid)
    job_instance = _instance_for_euid(backend, job.job_euid)
    assert (cluster_instance, job_instance, "compute_cluster_job") in backend.lineages


def test_compute_cluster_rejects_duplicate_active_name_region() -> None:
    store, _backend = _store_with_backend()

    store.create_compute_cluster(
        display_name="Cluster",
        cluster_name="majors-cluster",
        cluster_type="generic",
        region="us-west-2",
        tenant_id=TENANT_ID,
        owner_user_id=USER_ID,
    )

    try:
        store.create_compute_cluster(
            display_name="Cluster again",
            cluster_name="majors-cluster",
            cluster_type="generic",
            region="us-west-2",
            tenant_id=TENANT_ID,
            owner_user_id=USER_ID,
        )
    except ValueError as exc:
        assert "compute cluster already exists" in str(exc)
    else:
        raise AssertionError("duplicate active compute cluster was accepted")


def test_analysis_job_statuses_mutate_canonical_job_without_revision_children() -> None:
    store, backend, workset, manifest = _store_with_workset_manifest()

    defined = store.create_analysis_job(
        job_name="analysis-1",
        workset_euid=workset.euid,
        manifest_euid=manifest.euid,
        cluster_name="cluster-1",
        region="us-west-2",
        tenant_id=TENANT_ID,
        owner_user_id=USER_ID,
        request={"analysis": "wgs"},
    )
    running = store.update_analysis_job_status(
        job_euid=defined.job_euid,
        state="RUNNING",
        created_by=USER_ID,
        started_at="2026-05-11T00:03:00Z",
        launch={"slurm_job_id": "42"},
    )
    completed = store.update_analysis_job_status(
        job_euid=defined.job_euid,
        state="COMPLETED",
        created_by=USER_ID,
        completed_at="2026-05-11T00:04:00Z",
        return_code=0,
        output_summary="done",
    )
    failed = store.update_analysis_job_status(
        job_euid=defined.job_euid,
        state="FAILED",
        created_by=USER_ID,
        return_code=2,
        error="launch failed",
    )

    assert [defined.job_euid, running.job_euid, completed.job_euid, failed.job_euid] == [
        defined.job_euid
    ] * 4
    assert [
        instance.euid
        for instance in backend.instances
        if instance.template_code == ANALYSIS_JOB_TEMPLATE
    ] == [defined.job_euid]
    job = _instance_for_euid(backend, defined.job_euid)
    job_payload = from_json_addl(job)
    assert job_payload["state"] == "FAILED"
    assert job_payload["started_at"] == "2026-05-11T00:03:00Z"
    assert job_payload["completed_at"] == "2026-05-11T00:04:00Z"
    assert job_payload["launch"] == {"slurm_job_id": "42"}
    assert job_payload["return_code"] == 2
    _assert_no_revision_objects(backend, job)


def test_resource_store_writes_manifest_and_job_graph_payloads() -> None:
    store, backend = _store_with_backend()

    workset = store.create_workset(
        name="workset",
        tenant_id=TENANT_ID,
        owner_user_id=USER_ID,
        artifact_set_euids=[],
        metadata={},
    )
    manifest = store.create_manifest(
        workset_euid=workset.workset_euid,
        name="manifest",
        artifact_set_euid="AS-1",
        artifact_euids=["AT-1"],
        input_references=[
            {"reference_type": "artifact_euid", "value": "AT-2"},
            {
                "reference_type": "artifact_set_euid",
                "value": "AS-2",
                "artifact_euids": ["AT-3"],
            },
        ],
        metadata={},
    )
    analysis_job = store.create_analysis_job(
        job_name="analysis",
        workset_euid=workset.workset_euid,
        manifest_euid=manifest.manifest_euid,
        cluster_name="cluster",
        region="us-west-2",
        tenant_id=TENANT_ID,
        owner_user_id=USER_ID,
        request={},
    )
    staging_job = store.create_staging_job(
        job_name="staging",
        workset_euid=workset.workset_euid,
        manifest_euid=manifest.manifest_euid,
        cluster_name="cluster",
        region="us-west-2",
        tenant_id=TENANT_ID,
        owner_user_id=USER_ID,
        request={},
    )

    manifest_instance = _instance_for_euid(backend, manifest.manifest_euid)
    manifest_graph = _graph_payload(manifest_instance)
    assert isinstance(manifest_graph, list)
    assert not any(ref["inferred"] for ref in manifest_graph)
    assert {(ref["relationship_type"], ref["target_euid"]) for ref in manifest_graph} >= {
        ("uses_fastq_artifact", "AS-1"),
        ("uses_fastq_artifact", "AT-1"),
        ("uses_fastq_artifact", "AT-2"),
        ("uses_fastq_artifact", "AS-2"),
        ("uses_fastq_artifact", "AT-3"),
    }

    analysis_job_instance = _instance_for_euid(backend, analysis_job.job_euid)
    analysis_graph = _graph_payload(analysis_job_instance)
    assert analysis_graph == []
    assert from_json_addl(analysis_job_instance)["graph"]["fanout"] == {
        "classification": "expected",
        "relationship_type": "event",
        "expected_fanout_max": 500,
    }

    staging_job_instance = _instance_for_euid(backend, staging_job.job_euid)
    staging_graph = _graph_payload(staging_job_instance)
    assert staging_graph == []
    assert from_json_addl(staging_job_instance)["graph"]["fanout"] == {
        "classification": "expected",
        "relationship_type": "event",
        "expected_fanout_max": 500,
    }


def test_staging_job_statuses_mutate_canonical_job_without_revision_children() -> None:
    store, backend, workset, manifest = _store_with_workset_manifest()

    defined = store.create_staging_job(
        job_name="staging-1",
        workset_euid=workset.euid,
        manifest_euid=manifest.euid,
        cluster_name="cluster-1",
        region="us-west-2",
        tenant_id=TENANT_ID,
        owner_user_id=USER_ID,
        request={"stage_target": "s3"},
    )
    staging = store.update_staging_job_status(
        job_euid=defined.job_euid,
        state="STAGING",
        created_by=USER_ID,
        started_at="2026-05-11T00:05:00Z",
        stage={"attempt": 1},
    )
    completed = store.update_staging_job_status(
        job_euid=defined.job_euid,
        state="COMPLETED",
        created_by=USER_ID,
        completed_at="2026-05-11T00:06:00Z",
        return_code=0,
        output_summary="staged",
    )
    failed = store.update_staging_job_status(
        job_euid=defined.job_euid,
        state="FAILED",
        created_by=USER_ID,
        return_code=3,
        error="stage failed",
    )

    assert [defined.job_euid, staging.job_euid, completed.job_euid, failed.job_euid] == [
        defined.job_euid
    ] * 4
    assert [
        instance.euid
        for instance in backend.instances
        if instance.template_code == STAGING_JOB_TEMPLATE
    ] == [defined.job_euid]
    job = _instance_for_euid(backend, defined.job_euid)
    job_payload = from_json_addl(job)
    assert job_payload["state"] == "FAILED"
    assert job_payload["started_at"] == "2026-05-11T00:05:00Z"
    assert job_payload["completed_at"] == "2026-05-11T00:06:00Z"
    assert job_payload["stage"] == {"attempt": 1}
    assert job_payload["return_code"] == 3
    _assert_no_revision_objects(backend, job)
