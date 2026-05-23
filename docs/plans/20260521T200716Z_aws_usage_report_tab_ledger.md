# AWS Usage Report Tab Ledger

## Gate 0

- Scope: AWS lsmcok1 Ursa checkout only.
- Source artifact: /Users/jmajor/Downloads/aws_usage_report, staged to /home/ubuntu/.cache/dayhoff/uploads/aws_usage_report.tgz.
- Runtime destination: /home/ubuntu/.local/state/dayhoff/lsmcok1/reports/aws_usage_report.
- Repo destination: daylib_ursa/gui/static/aws_usage_report.
- Repo HEAD before changes: 750a51057535956be26c2d29a92b42e51090e24b.
- Repo status before changes:

```
## codex/aws-ursa-lazy-load-cache-20260520...origin/codex/aws-ursa-lazy-load-cache-20260520
```

## Rows

| ID | Area | Requirement | Status | Category | Gate | Evidence | Root Cause | Terminal Note |
|---|---|---|---|---|---|---|---|---|
| LEDGER-001 | Ursa | Create execution ledger and record Gate 0 | SUCCESS | plan_amendment | Gate 0 | This file |  | Ledger created before runtime/code edits. |
| ART-001 | Ursa | Copy AWS usage report to runtime and repo static locations | SUCCESS | feature_implementation | Gate 1 | Runtime `/home/ubuntu/.local/state/dayhoff/lsmcok1/reports/aws_usage_report` and repo `daylib_ursa/gui/static/aws_usage_report` contain index/images. |  | Report snapshot copied. |
| CFG-001 | Ursa | Add explicit report settings and live config values | SUCCESS | config_or_startup_contract | Gate 1 | Added settings and live YAML values for `aws_usage_report_dir` and `aws_usage_report_allowed_domains`. |  | Explicit report configuration is present. |
| ROUTE-001 | Ursa | Serve /aws_usage_report/ only to lsmc.com authenticated users | SUCCESS | feature_implementation | Gate 1 | Added authenticated `/aws_usage_report/` routes and path traversal guard. |  | Route implemented. |
| NAV-001 | Ursa | Add top-level nav tab visible only to lsmc.com users | SUCCESS | feature_implementation | Gate 1 | Added `AWS Usage` nav link gated by actor email domain. |  | Nav implemented. |
| TEST-001 | Ursa | Run focused tests and static checks | SUCCESS | contract_test | Gate 2 | `python -m py_compile daylib_ursa/gui_app.py daylib_ursa/config.py daylib_ursa/ursa_config.py`; `python -m pytest tests/test_admin_gui_and_cluster_routes.py -q` -> 18 passed, 1 existing passlib warning. |  | Static and focused route tests passed after decorator bugfix. |
| LIVE-001 | Ursa | Restart only Ursa and smoke live route | SUCCESS | contract_test | Gate 3 | Restarted only Ursa session `lsmcok1-ursa-service-20260521T201309Z`; port 8913 listening; `https://localhost:8913/aws_usage_report/` and `https://ursa.dev.lsmc.life/aws_usage_report/` return 303 to login when unauthenticated. |  | Live route is reachable and protected; no other service was restarted. |


## Final Status

All rows are terminal. The AWS usage report snapshot is present in the runtime report directory and in the Ursa repo static tree. The live `lsmcok1` Ursa config points at the runtime directory and allows only `lsmc.com` for the report route. Focused tests passed, and live unauthenticated smoke confirms the public report URL is protected by login.
