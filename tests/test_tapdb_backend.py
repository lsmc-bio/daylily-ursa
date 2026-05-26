"""Tests for the Ursa TapDB composition adapter and runtime helpers."""

from __future__ import annotations

import inspect
import json
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from daylib_ursa.integrations import tapdb_runtime
from daylib_ursa.tapdb_graph import backend as backend_module
from daylib_ursa.tapdb_graph.backend import (
    TEMPLATE_DEFINITIONS,
    URSA_TEMPLATE_DEFINITIONS,
    TapDBBackend,
    TemplateSpec,
    from_json_addl,
    to_action_history_entry,
    utc_now_iso,
)
from daylib_ursa.tapdb_templates import claim_ursa_template_prefixes


def _tapdb_dependency_spec() -> str:
    pyproject = tomllib.loads(
        (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8")
    )
    for dependency in pyproject["project"]["dependencies"]:
        if dependency.startswith("daylily-tapdb"):
            return dependency
    raise AssertionError("daylily-tapdb dependency missing from pyproject.toml")


def test_backend_adapter_reexports_tapdb_surface_directly() -> None:
    params = inspect.signature(TapDBBackend).parameters
    assert TapDBBackend.__mro__ == (TapDBBackend, object)
    assert "bundle" in params
    assert "app_username" in params
    assert backend_module.TEMPLATE_DEFINITIONS is TEMPLATE_DEFINITIONS
    assert callable(backend_module.from_json_addl)
    assert callable(backend_module.to_action_history_entry)
    assert callable(backend_module.utc_now_iso)


def test_template_definitions_cover_phase_one_objects() -> None:
    assert len(TEMPLATE_DEFINITIONS) >= 16
    codes = {spec.template_code for spec in TEMPLATE_DEFINITIONS}
    assert "RGX/analysis/run-linked/1.0/" in codes
    assert "RGX/workset/gui-ready/1.0/" in codes
    assert "RGX/manifest/dewey-bound/1.0/" in codes
    assert "RGX/auth/user-token/1.0/" in codes
    assert "RGX/auth/client-registration/1.0/" in codes


def test_template_definitions_exclude_revision_objects() -> None:
    removed_codes = {
        "RGX/auth/user-token-revision/1.0/",
        "RGX/cluster/ephemeral-job-revision/1.0/",
        "RGX/analysis/launch-job-revision/1.0/",
        "RGX/staging/job-revision/1.0/",
    }
    codes = {spec.template_code for spec in TEMPLATE_DEFINITIONS}
    assert codes.isdisjoint(removed_codes)

    template_pack = yaml.safe_load(
        Path("config/tapdb_templates/ursa/templates.json").read_text(encoding="utf-8")
    )
    pack_codes = {
        f"{template['category']}/{template['type']}/{template['subtype']}/{template['version']}/"
        for template in template_pack["templates"]
    }
    assert pack_codes.isdisjoint(removed_codes)


def test_template_definitions_are_template_spec_instances() -> None:
    for spec in URSA_TEMPLATE_DEFINITIONS:
        assert isinstance(spec, TemplateSpec)
        assert spec.template_code.endswith("/")


def test_template_definitions_use_frozen_prefix_remaps() -> None:
    template_pack = yaml.safe_load(
        Path("config/tapdb_templates/ursa/templates.json").read_text(encoding="utf-8")
    )
    prefixes = {template["instance_prefix"] for template in template_pack["templates"]}
    assert prefixes == {"RGX"}


def test_from_json_addl_extracts_dict() -> None:
    class _FakeInstance:
        json_addl = {"foo": "bar", "n": 42}

    result = from_json_addl(_FakeInstance())
    assert result == {"foo": "bar", "n": 42}
    assert result is not _FakeInstance.json_addl


def test_from_json_addl_handles_none() -> None:
    class _FakeInstance:
        json_addl = None

    assert from_json_addl(_FakeInstance()) == {}


def test_update_instance_json_replaces_nested_properties_and_marks_dirty(monkeypatch) -> None:
    flagged: list[tuple[object, str]] = []

    class _FakeSession:
        flushed = False

        def flush(self) -> None:
            self.flushed = True

    class _FakeInstance:
        tenant_id = None

        def __init__(self) -> None:
            self.original_json = {
                "properties": {
                    "state": "DEFINED",
                    "stage": {},
                }
            }
            self.json_addl = self.original_json

    monkeypatch.setattr(
        backend_module,
        "flag_modified",
        lambda instance, field: flagged.append((instance, field)),
    )

    instance = _FakeInstance()
    session = _FakeSession()
    backend = TapDBBackend.__new__(TapDBBackend)

    backend.update_instance_json(
        session,
        instance,
        {
            "state": "COMPLETED",
            "stage": {
                "stage_dir": "/staging/staged_external_sequencing_data/example",
                "stdout": "Remote FSx stage directory: /staging/staged_external_sequencing_data/example\n",
            },
        },
    )

    assert session.flushed
    assert flagged == [(instance, "json_addl")]
    assert instance.json_addl is not instance.original_json
    assert instance.original_json["properties"]["stage"] == {}
    assert instance.json_addl["properties"]["state"] == "COMPLETED"
    assert instance.json_addl["properties"]["stage"]["stage_dir"] == (
        "/staging/staged_external_sequencing_data/example"
    )


def test_to_action_history_entry_structure() -> None:
    entry = to_action_history_entry("a", "b", key="val")
    assert entry == {"args": ["a", "b"], "kwargs": {"key": "val"}}


def test_utc_now_iso_format() -> None:
    ts = utc_now_iso()
    assert ts.endswith("Z") or "+00:00" in ts
    assert "T" in ts


def test_adapter_module_has_no_removed_repo_reference() -> None:
    source = Path("daylib_ursa/tapdb_graph/backend.py").read_text(encoding="utf-8")
    assert "UrsaTapdbRepository" not in source
    assert "TapdbClientBundle" in source
    assert "sys.path.insert" not in source


def test_validate_database_target_accepts_current_targets() -> None:
    assert tapdb_runtime.validate_database_target("local") == "local"
    assert tapdb_runtime.validate_database_target("AURORA") == "aurora"


def test_validate_database_target_rejects_legacy_env_selectors() -> None:
    with pytest.raises(tapdb_runtime.TapDBRuntimeError, match="Unsupported database target"):
        tapdb_runtime.validate_database_target("dev")


def test_export_database_url_for_target_sets_runtime_environment(monkeypatch) -> None:
    monkeypatch.setattr(
        tapdb_runtime, "ensure_tapdb_version", lambda *_args, **_kwargs: _tapdb_dependency_spec()
    )
    monkeypatch.setattr(
        tapdb_runtime,
        "_get_tapdb_db_config",
        lambda **_kwargs: {
            "user": "ursa_user",
            "password": "secret",
            "host": "db.example.test",
            "port": "5432",
            "database": "daylily_ursa",
        },
    )
    monkeypatch.setattr(
        tapdb_runtime,
        "_resolve_runtime_env",
        lambda **_kwargs: {
            "aws_profile": "test-profile",
            "aws_region": "us-west-2",
            "client_id": "local",
            "database_name": "ursa",
            "schema_name": "tapdb_ursa_dev",
            "sslrootcert": "/tmp/rds-ca-bundle.pem",
            "physical_database": "daylily_ursa",
            "config_path": "/tmp/ursa-tapdb.yaml",
            "local_db_port": "5588",
            "local_ui_port": "8918",
            "domain_code": "Z",
            "owner_repo_name": "ursa",
            "domain_registry_path": "/tmp/domain.json",
            "prefix_registry_path": "/tmp/prefix.json",
        },
    )

    db_url = tapdb_runtime.export_database_url_for_target(
        target="local",
        client_id="local",
        profile="test-profile",
        region="us-west-2",
        namespace="ursa",
    )

    assert db_url == (
        "postgresql+psycopg2://ursa_user:secret@db.example.test:5432/daylily_ursa"
        "?options=-csearch_path%3Dtapdb_ursa_dev"
    )
    assert "DATABASE_URL" not in tapdb_runtime.os.environ


def test_export_database_url_supports_explicit_aurora_hostaddr(monkeypatch) -> None:
    monkeypatch.setattr(tapdb_runtime, "ensure_tapdb_version", lambda: _tapdb_dependency_spec())
    monkeypatch.setattr(
        tapdb_runtime,
        "_resolve_runtime_env",
        lambda **_kwargs: {
            "aws_profile": "test-profile",
            "aws_region": "us-west-2",
            "client_id": "ursa",
            "database_name": "ursa",
            "schema_name": "tapdb_ursa_unidbtst_local",
            "sslrootcert": "/tmp/rds-ca-bundle.pem",
            "physical_database": "tapdb_unidbtst_local",
            "config_path": "/tmp/ursa-tapdb.yaml",
        },
    )
    monkeypatch.setattr(
        tapdb_runtime,
        "_get_tapdb_db_config",
        lambda **_kwargs: {
            "engine_type": "aurora",
            "host": "dayhoff-test.cluster-example.us-west-2.rds.amazonaws.com",
            "hostaddr": "127.0.0.1",
            "port": "15432",
            "user": "ursa_user",
            "password": "secret",
            "database": "tapdb_unidbtst_local",
            "sslrootcert": "/tmp/rds-ca-bundle.pem",
        },
    )

    db_url = tapdb_runtime.export_database_url_for_target(
        target="aurora",
        client_id="ursa",
        profile="test-profile",
        region="us-west-2",
        namespace="ursa",
    )

    assert db_url == (
        "postgresql+psycopg2://ursa_user:secret@"
        "dayhoff-test.cluster-example.us-west-2.rds.amazonaws.com:15432/tapdb_unidbtst_local"
        "?options=-csearch_path%3Dtapdb_ursa_unidbtst_local"
        "&sslmode=verify-full&sslrootcert=%2Ftmp%2Frds-ca-bundle.pem&hostaddr=127.0.0.1"
    )


def test_export_database_url_supports_direct_aurora_without_hostaddr(monkeypatch) -> None:
    monkeypatch.setattr(tapdb_runtime, "ensure_tapdb_version", lambda: _tapdb_dependency_spec())
    monkeypatch.setattr(
        tapdb_runtime,
        "_resolve_runtime_env",
        lambda **_kwargs: {
            "aws_profile": "test-profile",
            "aws_region": "us-west-2",
            "client_id": "ursa",
            "database_name": "ursa",
            "schema_name": "tapdb_ursa_unidbtst_local",
            "sslrootcert": "/tmp/rds-ca-bundle.pem",
            "physical_database": "tapdb_unidbtst_local",
            "config_path": "/tmp/ursa-tapdb.yaml",
        },
    )
    monkeypatch.setattr(
        tapdb_runtime,
        "_get_tapdb_db_config",
        lambda **_kwargs: {
            "engine_type": "aurora",
            "host": "dayhoff-test.cluster-example.us-west-2.rds.amazonaws.com",
            "port": "5432",
            "user": "ursa_user",
            "password": "secret",
            "database": "tapdb_unidbtst_local",
            "sslrootcert": "/tmp/rds-ca-bundle.pem",
        },
    )

    db_url = tapdb_runtime.export_database_url_for_target(
        target="aurora",
        client_id="ursa",
        profile="test-profile",
        region="us-west-2",
        namespace="ursa",
    )

    assert db_url == (
        "postgresql+psycopg2://ursa_user:secret@"
        "dayhoff-test.cluster-example.us-west-2.rds.amazonaws.com:5432/tapdb_unidbtst_local"
        "?options=-csearch_path%3Dtapdb_ursa_unidbtst_local&sslmode=verify-full&sslrootcert=%2Ftmp%2Frds-ca-bundle.pem"
    )


def test_run_tapdb_cli_exports_explicit_identity_env(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(tapdb_runtime, "ensure_tapdb_version", lambda: _tapdb_dependency_spec())
    monkeypatch.setattr(
        tapdb_runtime,
        "_resolve_runtime_env",
        lambda **_kwargs: {
            "aws_profile": "lsmc",
            "aws_region": "us-west-2",
            "client_id": "local",
            "database_name": "ursa",
            "schema_name": "tapdb_ursa_dev",
            "sslrootcert": "/tmp/rds-ca-bundle.pem",
            "physical_database": "tapdb_shared_dev",
            "config_path": "/tmp/ursa-tapdb.yaml",
            "local_db_port": "5588",
            "local_ui_port": "8918",
            "domain_code": "Z",
            "owner_repo_name": "ursa",
            "domain_registry_path": "/tmp/domain.json",
            "prefix_registry_path": "/tmp/prefix.json",
        },
    )

    def fake_run(cmd, *, cwd=None, env=None, capture_output, text):
        captured["cmd"] = cmd
        captured["cwd"] = cwd
        captured["env"] = env
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(tapdb_runtime.subprocess, "run", fake_run)

    result = tapdb_runtime.run_tapdb_cli(
        ["bootstrap", "local", "--no-gui"],
        target="local",
        client_id="local",
        profile="lsmc",
        region="us-west-2",
        namespace="ursa",
    )

    assert result.returncode == 0
    assert captured["cmd"][:5] == [
        sys.executable,
        "-m",
        "daylily_tapdb.cli",
        "--config",
        "/tmp/ursa-tapdb.yaml",
    ]
    assert "--env" not in captured["cmd"]
    assert captured["env"]["MERIDIAN_DOMAIN_CODE"] == "Z"
    assert captured["env"]["TAPDB_OWNER_REPO"] == "ursa"


def test_ensure_local_tapdb_namespace_config_initializes_namespaced_config(
    monkeypatch, tmp_path
) -> None:
    captured: dict[str, object] = {"cmds": []}
    config_path = tmp_path / "tapdb" / "tapdb-config.yaml"

    monkeypatch.setattr(tapdb_runtime, "ensure_tapdb_version", lambda: _tapdb_dependency_spec())
    monkeypatch.setattr(
        tapdb_runtime,
        "_resolve_runtime_env",
        lambda **_kwargs: {
            "aws_profile": "lsmc",
            "aws_region": "us-west-2",
            "client_id": "local",
            "database_name": "ursa",
            "schema_name": "tapdb_ursa_dev",
            "sslrootcert": "/tmp/rds-ca-bundle.pem",
            "physical_database": "tapdb_shared_dev",
            "config_path": str(config_path),
            "local_db_port": "5588",
            "local_ui_port": "8918",
            "domain_code": "Z",
            "owner_repo_name": "ursa",
            "domain_registry_path": str(tmp_path / "domain.json"),
            "prefix_registry_path": str(tmp_path / "prefix.json"),
        },
    )

    def fake_run(cmd, *, env=None, capture_output, text):
        captured["cmds"].append(cmd)
        captured["env"] = env
        return SimpleNamespace(returncode=0, stdout="ok\n", stderr="")

    monkeypatch.setattr(tapdb_runtime.subprocess, "run", fake_run)

    result = tapdb_runtime.ensure_local_tapdb_namespace_config(config_path=str(config_path))

    assert result.returncode == 0
    assert config_path.parent.is_dir()
    assert captured["cmds"] == [
        [
            sys.executable,
            "-m",
            "daylily_tapdb.cli",
            "--config",
            str(config_path),
            "db-config",
            "init",
            "--client-id",
            "local",
            "--database-name",
            "ursa",
            "--schema-name",
            "tapdb_ursa_dev",
            "--owner-repo-name",
            "ursa",
            "--domain-code",
            "Z",
            "--domain-registry-path",
            str(tmp_path / "domain.json"),
            "--prefix-ownership-registry-path",
            str(tmp_path / "prefix.json"),
            "--engine-type",
            "local",
            "--host",
            "localhost",
            "--port",
            "5588",
            "--ui-port",
            "8918",
            "--user",
            "postgres",
            "--database",
            "tapdb_shared_dev",
        ],
        [
            sys.executable,
            "-m",
            "daylily_tapdb.cli",
            "--config",
            str(config_path),
            "--client-id",
            "local",
            "--database-name",
            "ursa",
            "db-config",
            "update",
            "--owner-repo-name",
            "ursa",
            "--domain-code",
            "Z",
            "--domain-registry-path",
            str(tmp_path / "domain.json"),
            "--prefix-ownership-registry-path",
            str(tmp_path / "prefix.json"),
            "--engine-type",
            "local",
            "--host",
            "localhost",
            "--port",
            "5588",
            "--ui-port",
            "8918",
            "--database",
            "tapdb_shared_dev",
            "--schema-name",
            "tapdb_ursa_dev",
        ],
    ]
    assert captured["env"]["MERIDIAN_DOMAIN_CODE"] == "Z"
    assert captured["env"]["TAPDB_OWNER_REPO"] == "ursa"


def test_ensure_local_tapdb_namespace_config_requires_explicit_config_path(monkeypatch) -> None:
    monkeypatch.setattr(
        tapdb_runtime,
        "_resolve_runtime_env",
        lambda **_kwargs: {
            "aws_profile": "lsmc",
            "aws_region": "us-west-2",
            "client_id": "local",
            "database_name": "ursa",
            "schema_name": "tapdb_ursa_dev",
            "sslrootcert": "/tmp/rds-ca-bundle.pem",
            "physical_database": "",
            "config_path": "",
            "local_db_port": "5588",
            "local_ui_port": "8918",
            "domain_code": "Z",
            "owner_repo_name": "ursa",
            "domain_registry_path": "/tmp/domain.json",
            "prefix_registry_path": "/tmp/prefix.json",
        },
    )

    with pytest.raises(tapdb_runtime.TapDBRuntimeError, match="TapDB config path is required"):
        tapdb_runtime.ensure_local_tapdb_namespace_config(config_path="")


@pytest.mark.parametrize("missing_key", ["domain_registry_path", "prefix_registry_path"])
def test_ensure_local_tapdb_namespace_config_requires_explicit_registry_paths(
    monkeypatch, missing_key
) -> None:
    runtime_env = {
        "aws_profile": "lsmc",
        "aws_region": "us-west-2",
        "client_id": "local",
        "database_name": "ursa",
        "schema_name": "tapdb_ursa_dev",
        "sslrootcert": "/tmp/rds-ca-bundle.pem",
        "physical_database": "",
        "config_path": "/tmp/ursa-tapdb.yaml",
        "local_db_port": "5588",
        "local_ui_port": "8918",
        "domain_code": "Z",
        "owner_repo_name": "ursa",
        "domain_registry_path": "/tmp/domain.json",
        "prefix_registry_path": "/tmp/prefix.json",
    }
    runtime_env[missing_key] = ""
    monkeypatch.setattr(tapdb_runtime, "_resolve_runtime_env", lambda **_kwargs: runtime_env)

    with pytest.raises(
        tapdb_runtime.TapDBRuntimeError,
        match="domain-registry-path|prefix-ownership-registry-path",
    ):
        tapdb_runtime.ensure_local_tapdb_namespace_config(config_path="/tmp/ursa-tapdb.yaml")


def test_resolve_tapdb_config_path_requires_explicit_path() -> None:
    resolved = tapdb_runtime._resolve_tapdb_config_path(namespace="ursa", client_id="local")

    assert resolved is None


def test_resolve_tapdb_config_path_returns_explicit_path() -> None:
    resolved = tapdb_runtime._resolve_tapdb_config_path(
        namespace="ursa",
        client_id="local",
        config_path="/tmp/ursa-tapdb.yaml",
    )

    assert resolved == "/tmp/ursa-tapdb.yaml"


def test_resolved_default_identity_uses_settings_config_and_registry_paths(monkeypatch) -> None:
    monkeypatch.setenv("TAPDB_CONFIG_PATH", "/tmp/from-env.yaml")
    monkeypatch.setenv("TAPDB_CLIENT_ID", "env-client")
    monkeypatch.setenv("TAPDB_DATABASE_NAME", "env-db")
    monkeypatch.setenv("TAPDB_SCHEMA_NAME", "tapdb_explicit_schema")

    monkeypatch.setitem(
        sys.modules,
        "daylib_ursa.config",
        SimpleNamespace(
            get_settings=lambda: SimpleNamespace(
                tapdb_client_id="yaml-client",
                tapdb_database_name="yaml-db",
                tapdb_config_path="/tmp/from-yaml.yaml",
                tapdb_schema_name="tapdb_yaml_dev",
                tapdb_physical_database="tapdb_shared_dev",
                tapdb_local_db_port=5533,
                tapdb_local_ui_port=8918,
                tapdb_domain_registry_path="/tmp/domain_code_registry.json",
                tapdb_prefix_ownership_registry_path="/tmp/prefix_ownership_registry.json",
                tapdb_domain_code="Z",
                tapdb_owner_repo_name="ursa",
            )
        ),
    )
    try:
        assert tapdb_runtime._resolved_default_identity() == (
            "env-client",
            "env-db",
            "tapdb_explicit_schema",
            "tapdb_shared_dev",
            "/tmp/from-yaml.yaml",
            "5533",
            "8918",
            "/tmp/domain_code_registry.json",
            "/tmp/prefix_ownership_registry.json",
            "Z",
            "ursa",
        )
    finally:
        sys.modules.pop("daylib_ursa.config", None)


def test_repo_ships_tapdb_config_template() -> None:
    template_path = Path("config/tapdb-config-ursa.yaml")
    payload = yaml.safe_load(template_path.read_text(encoding="utf-8"))

    assert template_path.is_file()
    assert payload["meta"]["config_version"] == 4
    assert payload["meta"]["client_id"] == "ursa"
    assert payload["meta"]["database_name"] == "ursa"
    assert payload["target"]["schema_name"] == "tapdb_ursa_dev"
    assert payload["meta"]["owner_repo_name"] == "ursa"
    assert payload["target"]["domain_code"] == "Z"
    assert payload["meta"]["domain_registry_path"] == "/absolute/path/to/domain_code_registry.json"
    assert (
        payload["meta"]["prefix_ownership_registry_path"]
        == "/absolute/path/to/prefix_ownership_registry.json"
    )
    assert payload["target"]["port"] == "5588"
    assert payload["target"]["database"] == "tapdb_shared_dev"
    assert payload["target"]["audit_log_euid_prefix"] == "RGX"
    assert payload["safety"]["safety_tier"] == "local"


def test_claim_ursa_template_prefixes_initializes_missing_registry(tmp_path: Path) -> None:
    domain_registry = tmp_path / "domain_code_registry.json"
    prefix_registry = tmp_path / "prefix_ownership_registry.json"
    domain_registry.write_text(
        json.dumps({"version": "0.4.0", "domains": {"Z": {"name": "localhost"}}}) + "\n",
        encoding="utf-8",
    )

    claimed = claim_ursa_template_prefixes(
        [{"instance_prefix": "RGX"}],
        domain_code="Z",
        owner_repo_name="ursa",
        domain_registry_path=domain_registry,
        prefix_registry_path=prefix_registry,
    )

    assert claimed == ["RGX"]
    payload = json.loads(prefix_registry.read_text(encoding="utf-8"))
    assert payload["ownership"]["Z"]["RGX"]["issuer_app_code"] == "ursa"


def test_claim_ursa_template_prefixes_rejects_conflict(tmp_path: Path) -> None:
    domain_registry = tmp_path / "domain_code_registry.json"
    prefix_registry = tmp_path / "prefix_ownership_registry.json"
    domain_registry.write_text(
        json.dumps({"version": "0.4.0", "domains": {"Z": {"name": "localhost"}}}) + "\n",
        encoding="utf-8",
    )
    prefix_registry.write_text(
        json.dumps(
            {
                "version": "0.4.0",
                "ownership": {"Z": {"RGX": {"issuer_app_code": "other-repo"}}},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="claimed by 'other-repo'"):
        claim_ursa_template_prefixes(
            [{"instance_prefix": "RGX"}],
            domain_code="Z",
            owner_repo_name="ursa",
            domain_registry_path=domain_registry,
            prefix_registry_path=prefix_registry,
        )


def test_backend_scopes_template_lookups_to_bundle_domain_code() -> None:
    template_calls: list[tuple[str, dict[str, str]]] = []

    class _FakeTemplateManager:
        def get_template(self, _session, template_code: str, **kwargs):
            template_calls.append((template_code, kwargs))
            return None

    backend = TapDBBackend(
        bundle=SimpleNamespace(
            connection=SimpleNamespace(domain_code="z"),
            template_manager=_FakeTemplateManager(),
            instance_factory=SimpleNamespace(),
        ),
        app_username="ursa",
        client_id="local",
        namespace="ursa",
    )

    with pytest.raises(RuntimeError, match="Missing Ursa templates"):
        backend.ensure_templates(object())

    assert template_calls
    assert {kwargs["domain_code"] for _, kwargs in template_calls} == {"Z"}


def test_backend_passes_settings_profile_and_region_to_tapdb_bundle(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeSettings:
        tapdb_client_id = "ursa"
        tapdb_database_name = "ursa-unidbtst"
        tapdb_config_path = "/tmp/ursa-tapdb.yaml"
        regions = [SimpleNamespace(name="us-west-2")]

        def get_effective_aws_profile(self) -> str:
            return "lsmc"

    def fake_get_tapdb_bundle(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            connection=SimpleNamespace(domain_code="Z"),
            template_manager=SimpleNamespace(),
            instance_factory=SimpleNamespace(),
        )

    monkeypatch.setattr(backend_module, "get_tapdb_bundle", fake_get_tapdb_bundle)
    monkeypatch.setattr("daylib_ursa.config.get_settings", lambda: _FakeSettings())

    backend = TapDBBackend()

    assert backend.bundle is not None
    assert captured["client_id"] == "ursa"
    assert captured["namespace"] == "ursa-unidbtst"
    assert captured["app_username"] == "ursa"
    assert captured["config_path"] == "/tmp/ursa-tapdb.yaml"
    assert captured["profile"] == "lsmc"
    assert captured["region"] == "us-west-2"


def test_backend_reads_runtime_settings_allowed_regions(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class _FakeSettings:
        tapdb_client_id = "ursa"
        tapdb_database_name = "ursa-unidbtst"
        tapdb_config_path = "/tmp/ursa-tapdb.yaml"

        def get_effective_aws_profile(self) -> str:
            return "lsmc"

        def get_allowed_regions(self) -> list[str]:
            return ["us-west-2"]

    def fake_get_tapdb_bundle(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            connection=SimpleNamespace(domain_code="Z"),
            template_manager=SimpleNamespace(),
            instance_factory=SimpleNamespace(),
        )

    monkeypatch.setattr(backend_module, "get_tapdb_bundle", fake_get_tapdb_bundle)
    monkeypatch.setattr("daylib_ursa.config.get_settings", lambda: _FakeSettings())

    backend = TapDBBackend()

    assert backend.bundle is not None
    assert captured["profile"] == "lsmc"
    assert captured["region"] == "us-west-2"


def test_get_tapdb_bundle_scopes_instance_factory_to_runtime_domain(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(tapdb_runtime, "ensure_tapdb_version", lambda: "6.0.9")
    monkeypatch.setattr(
        tapdb_runtime,
        "_resolve_runtime_env",
        lambda **_kwargs: {
            "client_id": "local",
            "database_name": "ursa",
            "schema_name": "tapdb_ursa_dev",
            "sslrootcert": "/tmp/rds-ca-bundle.pem",
            "physical_database": "tapdb_ursa_dev",
            "config_path": "/tmp/ursa.yaml",
            "aws_region": "us-west-2",
            "domain_code": "Z",
            "owner_repo_name": "ursa",
        },
    )
    monkeypatch.setattr(
        tapdb_runtime, "_require_config_path", lambda _runtime_env: "/tmp/ursa.yaml"
    )
    monkeypatch.setattr(
        tapdb_runtime,
        "_get_tapdb_db_config",
        lambda *_args, **_kwargs: {
            "host": "localhost",
            "port": "5432",
            "user": "ursa",
            "password": "secret",
            "database": "tapdb_ursa_dev",
            "engine_type": "postgres",
        },
    )

    class _FakeConnection:
        def __init__(self, **kwargs):
            captured["connection_kwargs"] = kwargs

    class _FakeTemplateManager:
        def __init__(self, config_path):
            captured["template_config_path"] = str(config_path)

    class _FakeInstanceFactory:
        def __init__(self, template_manager, *, domain_code=None):
            captured["instance_factory_template_manager"] = template_manager
            captured["instance_factory_domain_code"] = domain_code

    monkeypatch.setattr(tapdb_runtime, "TAPDBConnection", _FakeConnection)
    monkeypatch.setattr(tapdb_runtime, "TemplateManager", _FakeTemplateManager)
    monkeypatch.setattr(tapdb_runtime, "InstanceFactory", _FakeInstanceFactory)

    bundle = tapdb_runtime.get_tapdb_bundle()

    assert captured["connection_kwargs"]["domain_code"] == "Z"
    assert captured["connection_kwargs"]["schema_name"] == "tapdb_ursa_dev"
    assert captured["connection_kwargs"]["db_hostaddr"] is None
    assert captured["template_config_path"] == "/tmp/ursa.yaml"
    assert captured["instance_factory_domain_code"] == "Z"
    assert bundle.connection is not None


def test_get_tapdb_bundle_passes_explicit_hostaddr(monkeypatch) -> None:
    captured: dict[str, object] = {}

    monkeypatch.setattr(tapdb_runtime, "ensure_tapdb_version", lambda: "7.0.5")
    monkeypatch.setattr(
        tapdb_runtime,
        "_resolve_runtime_env",
        lambda **_kwargs: {
            "client_id": "ursa",
            "database_name": "ursa-unidbtst",
            "schema_name": "tapdb_ursa_unidbtst_local",
            "physical_database": "tapdb_unidbtst_local",
            "config_path": "/tmp/ursa.yaml",
            "aws_region": "us-west-2",
            "domain_code": "Z",
            "owner_repo_name": "ursa",
        },
    )
    monkeypatch.setattr(
        tapdb_runtime, "_require_config_path", lambda _runtime_env: "/tmp/ursa.yaml"
    )
    monkeypatch.setattr(
        tapdb_runtime,
        "_get_tapdb_db_config",
        lambda *_args, **_kwargs: {
            "host": "dayhoff-test.cluster-example.us-west-2.rds.amazonaws.com",
            "hostaddr": "127.0.0.1",
            "port": "15432",
            "user": "ursa",
            "password": "secret",
            "database": "tapdb_unidbtst_local",
            "engine_type": "aurora",
        },
    )

    class _FakeConnection:
        def __init__(self, **kwargs):
            captured["connection_kwargs"] = kwargs

    class _FakeTemplateManager:
        def __init__(self, config_path):
            captured["template_config_path"] = str(config_path)

    class _FakeInstanceFactory:
        def __init__(self, template_manager, *, domain_code=None):
            captured["instance_factory_domain_code"] = domain_code

    monkeypatch.setattr(tapdb_runtime, "TAPDBConnection", _FakeConnection)
    monkeypatch.setattr(tapdb_runtime, "TemplateManager", _FakeTemplateManager)
    monkeypatch.setattr(tapdb_runtime, "InstanceFactory", _FakeInstanceFactory)

    bundle = tapdb_runtime.get_tapdb_bundle(target="aurora")

    assert captured["connection_kwargs"]["db_hostaddr"] == "127.0.0.1"
    assert captured["connection_kwargs"]["db_hostname"] == (
        "dayhoff-test.cluster-example.us-west-2.rds.amazonaws.com:15432"
    )
    assert captured["connection_kwargs"]["schema_name"] == "tapdb_ursa_unidbtst_local"
    assert captured["template_config_path"] == "/tmp/ursa.yaml"
    assert captured["instance_factory_domain_code"] == "Z"
    assert bundle.connection is not None
