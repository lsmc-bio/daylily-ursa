from __future__ import annotations

import time
from types import SimpleNamespace

from daylily_ec.aws import ssm as ssm_module

from daylib_ursa.cluster_service import ClusterService
from daylib_ursa.ephemeral_cluster.runner import REQUIRED_DAYLILY_EC_VERSION


class FakeDaylilyEcClient:
    def __init__(self, *, instance_id: str | None = "i-0123456789abcdef0") -> None:
        self.instance_id = instance_id
        self.cluster_list_calls = 0
        self.cluster_describe_calls = 0
        self.run_calls = 0

    def cluster_describe(self, *, cluster_name: str, region: str):
        self.cluster_describe_calls += 1
        head_node = {
            "instanceType": "c7i.large",
            "state": "running",
        }
        if self.instance_id:
            head_node["instanceId"] = self.instance_id
        return {
            "clusterName": cluster_name,
            "clusterStatus": "CREATE_COMPLETE",
            "computeFleetStatus": "RUNNING",
            "headNode": head_node,
            "scheduler": {"type": "slurm"},
        }

    def cluster_list(self, *, region: str, details: bool = True):
        self.cluster_list_calls += 1
        return {
            "clusters": [
                {
                    "name": "cluster-1",
                    "status": "CREATE_COMPLETE",
                    "details": (
                        self.cluster_describe(cluster_name="cluster-1", region=region)
                        if details
                        else {}
                    ),
                }
            ]
        }

    def run(self, _args):
        self.run_calls += 1
        return SimpleNamespace(
            returncode=0,
            stdout=(
                "JOBID PARTITION CPUS ST NODELIST USER STATE MIN_MEMORY TIME NODES NAME\n"
                "42 compute 8 R compute-1 ubuntu RUNNING 4G 0:12 1 analysis\n"
                "43 compute 4 PD pending ubuntu PENDING 4G 0:00 1 waiting\n"
            ),
            stderr="",
        )


class FakeFsxClient:
    def get_paginator(self, operation_name: str):
        if operation_name == "describe_file_systems":
            return SimpleNamespace(
                paginate=lambda: [
                    {
                        "FileSystems": [
                            {
                                "FileSystemId": "fs-0123456789abcdef0",
                                "Lifecycle": "AVAILABLE",
                                "StorageCapacity": 4800,
                                "DNSName": "fsx.example.com",
                                "LustreConfiguration": {"MountName": "abcdefff"},
                                "Tags": [
                                    {
                                        "Key": "parallelcluster:cluster-name",
                                        "Value": "cluster-1",
                                    }
                                ],
                            }
                        ]
                    }
                ]
            )
        if operation_name == "describe_data_repository_associations":
            return SimpleNamespace(
                paginate=lambda **_kwargs: [
                    {
                        "Associations": [
                            {
                                "AssociationId": "dra-0123456789abcdef0",
                                "FileSystemId": "fs-0123456789abcdef0",
                                "FileSystemPath": "/fsx/run-a",
                                "DataRepositoryPath": "s3://bucket/run-a/",
                                "Lifecycle": "AVAILABLE",
                                "CreationTime": "2026-05-30T00:00:00Z",
                                "ImportedFileChunkSize": 1024,
                                "BatchImportMetaDataOnCreate": False,
                                "S3": {
                                    "AutoImportPolicy": {"Events": ["NEW"]},
                                    "AutoExportPolicy": {"Events": ["NEW", "CHANGED"]},
                                },
                            },
                            {
                                "AssociationId": "dra-deleting",
                                "FileSystemId": "fs-0123456789abcdef0",
                                "FileSystemPath": "/fsx/deleting",
                                "DataRepositoryPath": "s3://bucket/deleting/",
                                "Lifecycle": "DELETING",
                            },
                        ]
                    }
                ]
            )
        raise AssertionError(f"unexpected paginator: {operation_name}")


class FakeBoto3Session:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs

    def client(self, service_name: str):
        assert service_name == "fsx"
        return FakeFsxClient()


def _service(*, instance_id: str | None = "i-0123456789abcdef0") -> ClusterService:
    return ClusterService(
        regions=["us-west-2"],
        aws_profile="lsmc",
        client=FakeDaylilyEcClient(instance_id=instance_id),
    )


def test_cluster_payload_includes_pinned_version_console_url_and_cached_probe() -> None:
    service = _service()
    cluster = service.describe_cluster("cluster-1", "us-west-2")

    payload = cluster.to_dict()

    assert payload["daylily_ec_pinned_version"] == REQUIRED_DAYLILY_EC_VERSION
    assert payload["aws_console_url"] == (
        "https://us-west-2.console.aws.amazon.com/ec2/home?region=us-west-2"
        "#InstanceDetails:instanceId=i-0123456789abcdef0"
    )


def test_cluster_payload_can_include_fsx_volume_id(monkeypatch) -> None:
    monkeypatch.setattr("daylib_ursa.cluster_service.boto3.Session", FakeBoto3Session)
    service = _service()
    cluster = service.describe_cluster("cluster-1", "us-west-2")

    service.attach_fsx_inventory(cluster)
    payload = cluster.to_dict()

    assert payload["fsx_file_system_id"] == "fs-0123456789abcdef0"
    assert payload["fsx_discovery_error"] is None


def test_dra_probe_lists_active_associations(monkeypatch) -> None:
    monkeypatch.setattr("daylib_ursa.cluster_service.boto3.Session", FakeBoto3Session)
    service = _service()

    result = service.fetch_cluster_dra_probe(cluster_name="cluster-1", region="us-west-2")

    assert result["probe_type"] == "dra"
    assert result["data"]["file_system_id"] == "fs-0123456789abcdef0"
    assert result["data"]["association_count"] == 1
    association = result["data"]["associations"][0]
    assert association["association_id"] == "dra-0123456789abcdef0"
    assert association["file_system_path"] == "/fsx/run-a"
    assert association["data_repository_path"] == "s3://bucket/run-a/"
    assert association["auto_import_events"] == ["NEW"]
    assert association["auto_export_events"] == ["NEW", "CHANGED"]


def test_dra_probe_reports_empty_when_fsx_is_not_discovered(monkeypatch) -> None:
    class EmptyFsxClient(FakeFsxClient):
        def get_paginator(self, operation_name: str):
            if operation_name == "describe_file_systems":
                return SimpleNamespace(paginate=lambda: [{"FileSystems": []}])
            return super().get_paginator(operation_name)

    class EmptySession(FakeBoto3Session):
        def client(self, service_name: str):
            assert service_name == "fsx"
            return EmptyFsxClient()

    monkeypatch.setattr("daylib_ursa.cluster_service.boto3.Session", EmptySession)
    service = _service()

    result = service.fetch_cluster_dra_probe(cluster_name="cluster-1", region="us-west-2")

    assert result["error"] is None
    assert result["data"]["file_system_id"] is None
    assert result["data"]["association_count"] == 0
    assert "No ParallelCluster FSx filesystem" in result["data"]["message"]


def test_cluster_list_and_detail_share_900_second_cache() -> None:
    fake_client = FakeDaylilyEcClient()
    service = ClusterService(regions=["us-west-2"], aws_profile="lsmc", client=fake_client)

    names = service.list_clusters_in_region("us-west-2")
    cluster = service.describe_cluster("cluster-1", "us-west-2")
    cached_again = service.get_all_clusters()

    assert service.cache_ttl_seconds == 900
    assert names == ["cluster-1"]
    assert cluster.cluster_name == "cluster-1"
    assert cached_again[0].cluster_name == "cluster-1"
    assert fake_client.cluster_list_calls == 1

    service.describe_cluster("cluster-1", "us-west-2", force_refresh=True)

    assert fake_client.cluster_describe_calls == 2


def test_headnode_job_queue_uses_900_second_cache() -> None:
    fake_client = FakeDaylilyEcClient()
    service = ClusterService(regions=["us-west-2"], aws_profile="lsmc", client=fake_client)
    cluster = service.get_all_clusters()[0]

    first = service.fetch_headnode_status(cluster)
    second = service.fetch_headnode_status(cluster)

    assert service.job_queue_cache_ttl_seconds == 900
    assert fake_client.run_calls == 1
    assert first.job_queue is not None
    assert first.job_queue.running_jobs == 1
    assert first.job_queue.pending_jobs == 1
    assert second.job_queue is not None
    assert second.job_queue.total_cpus == 12

    service.fetch_headnode_status(cluster, force_refresh=True)

    assert fake_client.run_calls == 2


def test_static_probe_uses_ssm_and_caches_until_ttl(monkeypatch) -> None:
    calls: list[str] = []

    def fake_wait_for_ssm_online(*_args, **_kwargs) -> None:
        return None

    def fake_run_shell(_instance_id, _region, script, **_kwargs):
        calls.append(script)
        return SimpleNamespace(
            stdout=(
                "__DAYLILY_EC_VERSION_BEGIN__\n"
                '{"app": "daylily-ec", "version": "5.1.2", "git_hash": "abc123"}\n'
                "__DAYLILY_EC_VERSION_END__\n"
                "__DAY_CLONE_HELP_BEGIN__\n"
                "Usage: day-clone [OPTIONS]\n"
                "__DAY_CLONE_HELP_END__\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(ssm_module, "wait_for_ssm_online", fake_wait_for_ssm_online)
    monkeypatch.setattr(ssm_module, "run_shell", fake_run_shell)
    service = _service()
    service.get_all_clusters()

    first = service.fetch_headnode_static_probe(cluster_name="cluster-1", region="us-west-2")
    second = service.fetch_headnode_static_probe(cluster_name="cluster-1", region="us-west-2")
    listed = service.get_all_clusters()

    assert len(calls) == 1
    assert first["cached"] is False
    assert second["cached"] is True
    assert listed[0].headnode_probes["static"]["cached"] is True
    assert second["data"]["remote_daylily_ec_version"] == "5.1.2"
    assert second["data"]["remote_git_hash"] == "abc123"
    assert second["data"]["day_clone_available"] is True
    assert "day-clone --help" in calls[0]

    key = ("static", "us-west-2", "cluster-1")
    _expires_at, result = service._probe_cache[key]
    service._probe_cache[key] = (time.time() - 1, result)
    refreshed = service.fetch_headnode_static_probe(
        cluster_name="cluster-1",
        region="us-west-2",
    )

    assert len(calls) == 2
    assert refreshed["cached"] is False


def test_scheduler_and_fsx_probes_return_raw_outputs(monkeypatch) -> None:
    scripts: list[str] = []

    def fake_wait_for_ssm_online(*_args, **_kwargs) -> None:
        return None

    def fake_run_shell(_instance_id, _region, script, **_kwargs):
        scripts.append(script)
        if "squeue" in script:
            stdout = (
                "__SQUEUE_BEGIN__\n"
                "JOBID PARTITION NAME USER ST TIME NODES NODELIST(REASON)\n"
                "42 compute test ubuntu R 0:12 1 compute-1\n"
                "__SQUEUE_END__\n"
                "__SINFO_BEGIN__\n"
                "PARTITION AVAIL TIMELIMIT NODES STATE NODELIST\n"
                "compute* up infinite 1 idle compute-1\n"
                "__SINFO_END__\n"
            )
        else:
            stdout = (
                "__DF_FSX_BEGIN__\n"
                "Filesystem Size Used Avail Use% Mounted on\n"
                "fsx 1.2T 200G 1.0T 17% /fsx\n"
                "__DF_FSX_END__\n"
            )
        return SimpleNamespace(stdout=stdout, stderr="")

    monkeypatch.setattr(ssm_module, "wait_for_ssm_online", fake_wait_for_ssm_online)
    monkeypatch.setattr(ssm_module, "run_shell", fake_run_shell)
    service = _service()

    scheduler = service.fetch_headnode_scheduler_probe(
        cluster_name="cluster-1",
        region="us-west-2",
    )
    fsx = service.fetch_headnode_fsx_probe(cluster_name="cluster-1", region="us-west-2")

    assert "JOBID PARTITION" in scheduler["data"]["squeue_output"]
    assert "compute* up" in scheduler["data"]["sinfo_output"]
    assert "fsx 1.2T" in fsx["data"]["df_output"]
    assert any("sinfo" in script for script in scripts)
    assert any("df -h /fsx" in script for script in scripts)


def test_missing_instance_id_returns_probe_error(monkeypatch) -> None:
    called = False

    def fake_run_shell(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("run_shell should not run without an instance id")

    monkeypatch.setattr(ssm_module, "run_shell", fake_run_shell)
    service = _service(instance_id=None)

    result = service.fetch_headnode_fsx_probe(cluster_name="cluster-1", region="us-west-2")

    assert called is False
    assert result["error"] == "Headnode EC2 instance id is unavailable for cluster-1"
    assert result["instance_id"] is None


def test_nonzero_ssm_command_is_reported_inline(monkeypatch) -> None:
    def fake_wait_for_ssm_online(*_args, **_kwargs) -> None:
        return None

    def fake_run_shell(*_args, **_kwargs):
        command_result = ssm_module.SsmCommandResult(
            command_id="cmd-1",
            instance_id="i-0123456789abcdef0",
            status="Failed",
            response_code=127,
            stdout="",
            stderr="squeue: command not found",
        )
        raise ssm_module.SsmCommandFailedError("command failed", command_result)

    monkeypatch.setattr(ssm_module, "wait_for_ssm_online", fake_wait_for_ssm_online)
    monkeypatch.setattr(ssm_module, "run_shell", fake_run_shell)
    service = _service()

    result = service.fetch_headnode_scheduler_probe(
        cluster_name="cluster-1",
        region="us-west-2",
    )

    assert result["error"] == "squeue: command not found"
    assert result["data"]["response_code"] == 127
    assert result["data"]["status"] == "Failed"
