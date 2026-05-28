from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from daylib_ursa import container_entry


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_docker_runtime_files_use_foreground_uv_and_no_legacy_runtime() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    entrypoint = (PROJECT_ROOT / "docker" / "entrypoint.sh").read_text(encoding="utf-8")

    assert "uv sync --frozen --no-dev --no-install-project" in dockerfile
    assert "uv sync --frozen --no-dev" in dockerfile
    assert "USER lsmc" in dockerfile
    assert 'python", "-m", "daylib_ursa.container_entry' in dockerfile
    assert ":latest" not in dockerfile
    assert "conda" not in dockerfile.lower()
    assert "tmux" not in entrypoint
    assert "background" not in entrypoint
    assert "${XDG_CONFIG_HOME:?XDG_CONFIG_HOME is required}" in entrypoint
    assert "${TAPDB_CONFIG_PATH:?TAPDB_CONFIG_PATH is required}" in entrypoint


def test_container_entry_requires_absolute_tapdb_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAPDB_CONFIG_PATH", "relative.yaml")

    with pytest.raises(RuntimeError, match="must be an absolute path"):
        container_entry._required_absolute_file("TAPDB_CONFIG_PATH")


def test_container_entry_runs_foreground_http_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    xdg_home = tmp_path / "xdg"
    xdg_home.mkdir()
    tapdb_path = tmp_path / "tapdb.yaml"
    tapdb_path.write_text("target: {}\n", encoding="utf-8")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_home))
    monkeypatch.setenv("TAPDB_CONFIG_PATH", str(tapdb_path))
    monkeypatch.setenv("HOST", "127.0.0.1")
    monkeypatch.setenv("PORT", "8913")

    with patch("daylib_ursa.container_entry._start_server") as start:
        container_entry.main()

    assert start.call_args.kwargs == {
        "port": 8913,
        "host": "127.0.0.1",
        "ssl": False,
        "cert": None,
        "key": None,
        "reload": False,
        "background": False,
        "check_cognito_uris": False,
    }
