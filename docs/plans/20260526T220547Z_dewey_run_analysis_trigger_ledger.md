# Dewey Run Analysis Trigger Ledger

Created: 2026-05-26T22:05:47Z

Private branch: `codex/sequencer-run-registration-20260526T220547Z`

Base tag: `4.0.0`

## Scope

Implement the Ursa side of Dewey sequencer-run handoff without adding arbitrary sidecar shell execution or live cluster cleanup.

## Rows

| ID | Requirement | Status | Evidence |
|---|---|---|---|
| URSA-TRIG-001 | Add service-token protected `POST /api/v1/dewey/run-analysis-triggers`. | DONE | `daylib_ursa/workset_api.py` |
| URSA-TRIG-002 | Add `GET /api/v1/dewey/run-analysis-triggers/{trigger_euid}`. | DONE | `daylib_ursa/workset_api.py` |
| URSA-TRIG-003 | Validate `command_id` through the DayEC command catalog and reject arbitrary shell fields. | DONE | `tests/test_dewey_run_analysis_triggers.py` |
| URSA-TRIG-004 | Add replay-safe idempotency behavior. | DONE | `tests/test_dewey_run_analysis_triggers.py` |
| URSA-TRIG-005 | Add Dewey client method for terminal analysis-result registration. | DONE | `daylib_ursa/integrations/dewey_client.py`, `tests/test_dewey_run_analysis_triggers.py` |
| URSA-EXEC-001 | Live cluster launch/export/idle cleanup. | DONE_PRIVATE_LOCAL | Implemented auto-launch and admin cleanup/export-before-delete in the private branch; see `docs/plans/20260527T051309Z_ursa_live_execution_cleanup_8agent_ledger.md`. No AWS deployment or live destructive cleanup performed. |

## Acceptance

- `pytest -q tests/test_dewey_run_analysis_triggers.py tests/test_dewey_client.py` passed.
- `ruff check daylib_ursa/workset_api.py daylib_ursa/integrations/dewey_client.py tests/test_dewey_run_analysis_triggers.py` passed.
- Repo-wide `URSA_DEPLOYMENT_CODE=runtrig ursa quality check` still fails on pre-existing unrelated format/typecheck debt.

## 2026-05-27 Update

- Auto-launch, durable trigger persistence, terminal Dewey result registration, and admin cleanup export-before-delete behavior were implemented in the follow-on private ledger.
- `URSA_DEPLOYMENT_CODE=runtrig ursa test run` passed with `334 passed, 2 skipped`.
- The previous live execution blocker is resolved for local/private implementation. AWS deployment, live cleanup execution, release tagging, PRs, and main merge remain explicitly deferred.
