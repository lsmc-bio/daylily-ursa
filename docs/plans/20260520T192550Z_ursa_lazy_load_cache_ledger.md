# Ursa Lazy Loading And 15-Minute In-Memory Cache Ledger

## Gate 0

- Scope: AWS lsmcok1 Ursa checkout only.
- Goal: shell-first dashboard, clusters, and usage pages with async data hydration.
- Cache: process-wide in-memory caches with 900 second TTL; actor-specific payloads keyed by actor visibility scope.
- No Dayhoff, other service, DB schema, or release train changes in this ledger.

## Rows

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| LEDGER-001 | Create execution ledger | SUCCESS | This file. |
| API-001 | Add authenticated dashboard and usage GUI JSON endpoints | SUCCESS | Added `/api/v1/gui/dashboard` and `/api/v1/gui/usage`; focused tests passed. |
| UI-001 | Make dashboard and usage render shell-first with loading/error states | SUCCESS | Dashboard and usage templates render loading shells and hydrate asynchronously; focused tests passed. |
| CACHE-001 | Use 900 second in-memory caches without cross-user leakage | SUCCESS | GUI payload cache is keyed by actor visibility scope and user id; cluster and usage services keep their existing 900 second caches. |
| LIVE-001 | Restart only Ursa after tests pass | SUCCESS | Restarted only Ursa from the generated Dayhoff start script; pid listens on 8913 and public ngrok reaches Uvicorn. |

## Verification

- `python -m py_compile daylib_ursa/gui_app.py`: SUCCESS.
- `python -m pytest tests/test_admin_gui_and_cluster_routes.py tests/test_aws_usage_reports.py tests/test_cluster_headnode_diagnostics.py -q`: SUCCESS, 25 passed, 1 existing deprecation warning.

## Live Smoke

- Restarted only Ursa; other service tmux sessions were not touched.
- Ursa listener: `*:8913`.
- `https://localhost:8913/` returned `303` to login in `0.016558s`.
- `https://localhost:8913/usage` returned `303` to login in `0.010294s`.
- `https://ursa.dev.lsmc.life/` reached Uvicorn over ngrok.

## Final Runtime Note

- Final Ursa process runs in tmux session `lsmcok1-ursa-service-20260520T193935Z` using the generated Dayhoff Ursa launch environment and foreground `python -m daylib_ursa.workset_api_cli`.
