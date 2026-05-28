from __future__ import annotations

from cli_core_yo import runtime as cli_runtime


def test_container_entry_initializes_cli_runtime(monkeypatch, tmp_path):
    import daylib_ursa.container_entry as entry

    tapdb_path = tmp_path / "tapdb.yaml"
    tapdb_path.write_text("target: {}\n", encoding="utf-8")
    monkeypatch.setenv("TAPDB_CONFIG_PATH", str(tapdb_path))
    monkeypatch.setenv("PORT", "8913")
    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("URSA_DEPLOYMENT_CODE", "inf9")
    for name in ("config", "state", "data", "cache"):
        (tmp_path / "xdg" / name).mkdir(parents=True)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg" / "config"))
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "xdg" / "state"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg" / "data"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg" / "cache"))

    observed: dict[str, object] = {}

    def fake_start(**kwargs: object) -> None:
        observed["kwargs"] = kwargs
        observed["state_root"] = cli_runtime.get_context().xdg_paths.state

    monkeypatch.setattr(entry, "_start_server", fake_start)
    cli_runtime._reset()
    try:
        entry.main()
    finally:
        cli_runtime._reset()

    assert observed["state_root"].is_absolute()
    assert observed["kwargs"] == {
        "port": 8913,
        "host": "0.0.0.0",
        "ssl": False,
        "cert": None,
        "key": None,
        "reload": False,
        "background": False,
        "check_cognito_uris": False,
    }
