"""Pytest configuration and shared fixtures."""

from importlib import metadata as importlib_metadata
import os

import pytest

# Set WHITELIST_DOMAINS to the default base allowlist for tests.
# This must be set before importing any daylib_ursa modules
os.environ.setdefault(
    "WHITELIST_DOMAINS",
    "lsmc.com,lsmc.bio,lsmc.life,daylilyinformatics.com",
)

os.environ.setdefault("XDG_CONFIG_HOME", "/tmp/ursa-test-config")
os.environ.setdefault("URSA_DEPLOYMENT_CODE", "test")

_REAL_METADATA_VERSION = importlib_metadata.version


def _test_metadata_version(distribution_name: str) -> str:
    if distribution_name == "daylily-ephemeral-cluster":
        return "5.0.24"
    return _REAL_METADATA_VERSION(distribution_name)


importlib_metadata.version = _test_metadata_version


@pytest.fixture(autouse=True)
def _installed_required_dayec_for_unit_tests(monkeypatch):
    """Model the declared day-ec dependency in tests that construct the app."""

    from daylib_ursa.ephemeral_cluster import runner

    def fake_version(distribution_name: str) -> str:
        if distribution_name == runner.DAYLILY_EC_DISTRIBUTION:
            return runner.REQUIRED_DAYLILY_EC_VERSION
        return _REAL_METADATA_VERSION(distribution_name)

    monkeypatch.setattr(runner.importlib_metadata, "version", fake_version)
