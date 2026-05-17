from __future__ import annotations

import subprocess

import pytest

from daylib_ursa.ephemeral_cluster import runner


def test_run_json_raises_when_daylily_ec_returns_empty_stdout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner,
        "require_daylily_ec_version",
        lambda: runner.REQUIRED_DAYLILY_EC_VERSION,
    )

    def fake_run(*_args, **_kwargs) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=["python", "-m", "daylily_ec.cli", "--json", "cluster", "list"],
            returncode=0,
            stdout="",
            stderr="AWS profile is required. Set AWS_PROFILE or use --profile.\n",
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    client = runner.DaylilyEcClient()

    with pytest.raises(RuntimeError, match="AWS profile is required"):
        client.run_json(["cluster", "list", "--region", "us-west-2"])


def test_run_json_parses_object_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner,
        "require_daylily_ec_version",
        lambda: runner.REQUIRED_DAYLILY_EC_VERSION,
    )
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs) -> subprocess.CompletedProcess[str]:  # noqa: ANN001
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=["python", "-m", "daylily_ec.cli", "--json", "cluster", "list"],
            returncode=0,
            stdout='{"clusters":[],"regions":["us-west-2"]}\n',
            stderr="",
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    client = runner.DaylilyEcClient()

    assert client.run_json(["cluster", "list", "--region", "us-west-2"]) == {
        "clusters": [],
        "regions": ["us-west-2"],
    }
    assert captured["command"][:4] == [
        runner.sys.executable,
        "-m",
        "daylily_ec.cli",
        "--json",
    ]


def test_stage_samples_builds_daylily_ec_224_argv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        runner,
        "require_daylily_ec_version",
        lambda: runner.REQUIRED_DAYLILY_EC_VERSION,
    )

    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    client = runner.DaylilyEcClient(aws_profile="profile-a")
    result = client.stage_samples(
        analysis_samples=tmp_path / "analysis_samples.tsv",
        reference_bucket="s3://bucket/ref",
        config_dir=tmp_path,
        region="us-west-2",
        stage_target="/data/staged_sample_data",
        debug=True,
    )

    assert result.returncode == 0
    assert captured["command"] == [
        runner.sys.executable,
        "-m",
        "daylily_ec.cli",
        "samples",
        "stage",
        str(tmp_path / "analysis_samples.tsv"),
        "--reference-bucket",
        "s3://bucket/ref",
        "--config-dir",
        str(tmp_path),
        "--region",
        "us-west-2",
        "--stage-target",
        "/data/staged_sample_data",
        "--profile",
        "profile-a",
        "--debug",
    ]


def test_daylily_ec_subprocess_disables_inherited_s3_acceleration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        runner,
        "require_daylily_ec_version",
        lambda: runner.REQUIRED_DAYLILY_EC_VERSION,
    )
    source_config = tmp_path / "aws-config"
    source_config.write_text(
        "\n".join(
            [
                "[profile lsmc]",
                "region = us-west-2",
                "sso_session = lsmc",
                "s3 =",
                "    addressing_style = virtual",
                "    use_accelerate_endpoint = true",
                "[sso-session lsmc]",
                "sso_region = us-west-2",
                "sso_start_url = https://example.awsapps.com/start",
                "",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AWS_CONFIG_FILE", str(source_config))
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        env = kwargs["env"]
        captured["command"] = command
        captured["env"] = env
        captured["aws_config_text"] = runner.Path(env["AWS_CONFIG_FILE"]).read_text(
            encoding="utf-8"
        )
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="ok", stderr="")

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    client = runner.DaylilyEcClient(aws_profile="lsmc")
    result = client.stage_samples(
        analysis_samples=tmp_path / "analysis_samples.tsv",
        reference_bucket="s3://bucket/ref",
        config_dir=tmp_path,
        region="us-west-2",
    )

    assert result.returncode == 0
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["AWS_PROFILE"] == "lsmc"
    assert env["AWS_CONFIG_FILE"] != str(source_config)
    aws_config_text = str(captured["aws_config_text"])
    assert "[profile lsmc]" in aws_config_text
    assert "[sso-session lsmc]" in aws_config_text
    assert "addressing_style = virtual" in aws_config_text
    assert "use_accelerate_endpoint = false" in aws_config_text
    assert "use_accelerate_endpoint = true" not in aws_config_text


def test_aws_validate_all_builds_daylily_ec_224_argv(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        runner,
        "require_daylily_ec_version",
        lambda: runner.REQUIRED_DAYLILY_EC_VERSION,
    )
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout='{"summary":{"PASS":1,"WARN":0,"FAIL":0}}\n',
            stderr="",
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    result = runner.run_aws_validate_all_sync(
        region_az="us-west-2b",
        aws_profile="lsmc",
        config_path="/tmp/daylily-cluster.yaml",
        gap_analysis_path=tmp_path / "gap_analysis.md",
    )

    assert result.returncode == 0
    assert captured["command"] == [
        runner.sys.executable,
        "-m",
        "daylily_ec.cli",
        "--json",
        "aws",
        "validate",
        "all",
        "--profile",
        "lsmc",
        "--region-az",
        "us-west-2b",
        "--config",
        "/tmp/daylily-cluster.yaml",
        "--gap-analysis",
        str(tmp_path / "gap_analysis.md"),
    ]


def test_create_dry_run_builds_daylily_ec_create_with_day_break(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        runner,
        "require_daylily_ec_version",
        lambda: runner.REQUIRED_DAYLILY_EC_VERSION,
    )
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout="Dry-run passed\n",
            stderr="",
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)
    config_path = tmp_path / "cluster.yaml"
    config_path.write_text("ephemeral_cluster:\n  config: {}\n", encoding="utf-8")

    result = runner.run_create_dry_run_sync(
        region_az="us-west-2b",
        aws_profile="lsmc",
        config_path=str(config_path),
        pass_on_warn=True,
        debug=True,
        contact_email="ops@example.com",
        repo_overrides=["daylily-omics-analysis:main"],
    )

    assert result.returncode == 0
    assert captured["command"] == [
        runner.sys.executable,
        "-m",
        "daylily_ec.cli",
        "create",
        "--region-az",
        "us-west-2b",
        "--config",
        str(config_path),
        "--non-interactive",
        "--profile",
        "lsmc",
        "--pass-on-warn",
        "--debug",
        "--repo-override",
        "daylily-omics-analysis:main",
    ]
    env = captured["kwargs"]["env"]
    assert env["AWS_PROFILE"] == "lsmc"
    assert env["DAY_CONTACT_EMAIL"] == "ops@example.com"
    assert env["DAY_BREAK"] == "1"


def test_run_mount_create_uses_json_cli_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner,
        "require_daylily_ec_version",
        lambda: runner.REQUIRED_DAYLILY_EC_VERSION,
    )
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout='{"mount_id":"RUN-1","headnode_path":"/fsx/run_dir_mounts/RUN-1/"}\n',
            stderr="",
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    client = runner.DaylilyEcClient(aws_profile="lsmc")
    payload = client.run_mount_create(
        s3_uri="s3://bucket/RUN-1/",
        region="us-west-2",
        cluster_name="cluster-a",
        mount_id="RUN-1",
        run_id="RUN-1",
        platform="ILLUMINA",
        file_system_path="/run_dir_mounts/RUN-1/",
        wait=False,
    )

    assert payload["mount_id"] == "RUN-1"
    assert captured["command"] == [
        runner.sys.executable,
        "-m",
        "daylily_ec.cli",
        "--json",
        "mounts",
        "create",
        "--s3-uri",
        "s3://bucket/RUN-1/",
        "--region",
        "us-west-2",
        "--cluster",
        "cluster-a",
        "--mount-id",
        "RUN-1",
        "--run-id",
        "RUN-1",
        "--platform",
        "ILLUMINA",
        "--file-system-path",
        "/run_dir_mounts/RUN-1/",
        "--no-wait",
        "--profile",
        "lsmc",
    ]


def test_run_mount_verify_uses_json_cli_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        runner,
        "require_daylily_ec_version",
        lambda: runner.REQUIRED_DAYLILY_EC_VERSION,
    )
    captured: dict[str, object] = {}

    def fake_run(command, **kwargs):  # noqa: ANN001
        captured["command"] = command
        captured["kwargs"] = kwargs
        return subprocess.CompletedProcess(
            args=command,
            returncode=0,
            stdout='{"mount_id":"RUN-1","verified":true}\n',
            stderr="",
        )

    monkeypatch.setattr(runner.subprocess, "run", fake_run)

    client = runner.DaylilyEcClient(aws_profile="lsmc")
    payload = client.run_mount_verify(
        mount_id="RUN-1",
        region="us-west-2",
        cluster_name="cluster-a",
    )

    assert payload["verified"] is True
    assert captured["command"] == [
        runner.sys.executable,
        "-m",
        "daylily_ec.cli",
        "--json",
        "mounts",
        "verify",
        "--mount-id",
        "RUN-1",
        "--cluster",
        "cluster-a",
        "--region",
        "us-west-2",
        "--profile",
        "lsmc",
    ]
