"""Process entry point for one OWY run-directory orchestration trigger."""

from __future__ import annotations

import sys

from daylib_ursa.run_directory_orchestrator import main


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
