"""Container foreground entrypoint for Ursa."""

from __future__ import annotations

import os
from pathlib import Path


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


def _required_absolute_file(name: str) -> Path:
    path = Path(_required_env(name))
    if not path.is_absolute():
        raise RuntimeError(f"{name} must be an absolute path")
    if not path.is_file():
        raise RuntimeError(f"{name} does not exist: {path}")
    return path


def _required_absolute_dir(name: str) -> Path:
    path = Path(_required_env(name))
    if not path.is_absolute():
        raise RuntimeError(f"{name} must be an absolute path")
    if not path.is_dir():
        raise RuntimeError(f"{name} does not exist: {path}")
    return path


def _start_server(**kwargs: object) -> None:
    from daylib_ursa.cli.server import start

    start(**kwargs)


def _initialize_runtime_context() -> None:
    from cli_core_yo.errors import ContextNotInitializedError
    from cli_core_yo.runtime import get_context, initialize
    from cli_core_yo.xdg import resolve_paths

    from daylib_ursa.cli import spec

    try:
        get_context()
        return
    except ContextNotInitializedError:
        pass

    initialize(
        spec,
        resolve_paths(spec.xdg),
        config_path=None,
        invocation={"entrypoint": "container"},
        backend_name="container",
        backend_kind="container",
        runtime_guard_mode="off",
        runtime_check_skipped=True,
    )


def main() -> None:
    _required_absolute_dir("XDG_CONFIG_HOME")
    _required_absolute_file("TAPDB_CONFIG_PATH")
    _initialize_runtime_context()
    _start_server(
        port=int(_required_env("PORT")),
        host=_required_env("HOST"),
        ssl=False,
        cert=None,
        key=None,
        reload=False,
        background=False,
        check_cognito_uris=False,
    )


if __name__ == "__main__":
    main()
