"""Pytest configuration and shared fixtures."""

from importlib import metadata as importlib_metadata
import os
from pathlib import Path

import pytest

# Set WHITELIST_DOMAINS to the default base allowlist for tests.
# This must be set before importing any daylib_ursa modules
os.environ.setdefault(
    "WHITELIST_DOMAINS",
    "lsmc.com,lsmc.bio,lsmc.life,daylilyinformatics.com",
)
_PROJECT_ROOT = Path(__file__).resolve().parents[1]

os.environ["URSA_DEPLOYMENT_CODE"] = "local"
os.environ["CONDA_DEFAULT_ENV"] = "URSA-local"
os.environ.setdefault("CONDA_PREFIX", str(_PROJECT_ROOT / ".pytest-conda" / "URSA-local"))
os.environ.setdefault("XDG_CONFIG_HOME", str(_PROJECT_ROOT / ".pytest-xdg"))

_REAL_VERSION = importlib_metadata.version


def _test_distribution_version(distribution_name: str) -> str:
    if distribution_name == "daylily-ephemeral-cluster":
        from daylib_ursa.ephemeral_cluster import runner

        return runner.REQUIRED_DAYLILY_EC_VERSION
    return _REAL_VERSION(distribution_name)


importlib_metadata.version = _test_distribution_version


@pytest.fixture(autouse=True)
def _installed_required_dayec_for_unit_tests(monkeypatch):
    """Model the declared day-ec dependency in tests that construct the app."""

    from daylib_ursa.ephemeral_cluster import runner

    monkeypatch.setattr(runner.importlib_metadata, "version", _test_distribution_version)
