# Ursa Live Execution, Cleanup Toggle, and Cross-Service Readiness 8-Agent Ledger

Created: 2026-05-27T05:13:09Z

Private branch: `codex/sequencer-run-registration-20260526T220547Z`

Starting commit/tag: `47f7411` / `4.0.1`

## Gate 0 Inventory

- Repo: `/Users/jmajor/projects/mega_dayhoff/repos_work/daylily-ursa-sequencer-run-registration-20260526`
- `git status --short --branch`: `## codex/sequencer-run-registration-20260526T220547Z` with dirty tracked files:
  - `daylib_ursa/cluster_service.py`
  - `daylib_ursa/config.py`
  - `daylib_ursa/ephemeral_cluster/runner.py`
- Existing trigger ledger: `docs/plans/20260526T220547Z_dewey_run_analysis_trigger_ledger.md`
- Existing trigger ledger blocker: `URSA-EXEC-001` live cluster launch/export/idle cleanup marked `BLOCKED`.
- Baseline focused tests: `pytest -q tests/test_dewey_run_analysis_triggers.py tests/test_dewey_client.py` -> `6 passed`.
- Baseline quality: `URSA_DEPLOYMENT_CODE=runtrig ursa quality check` -> lint passed; format failed on 15 files; typecheck failed with 77 errors in 18 files. Touched-file quality relevance at Gate 0: `daylib_ursa/config.py` needs formatting; typecheck errors in touched `daylib_ursa/cluster_service.py` existed in the same file around cluster inventory typing and must be rechecked after edits.
- No AWS deployment or live destructive cleanup was started during Gate 0.

## Rows

| ID | Agent | Area | Requirement | Status | Evidence | Terminal Note |
|---|---:|---|---|---|---|---|
| SETUP-001 | 1 | Gate 0 | Record git state, dirty partial edits, existing ledgers, current baseline tests, and repo-wide quality failures. | SUCCESS | This file; dirty files listed above; focused baseline `6 passed`; quality baseline failed format/typecheck as recorded. | Gate 0 complete; implementation can proceed without claiming repo-wide quality is clean. |
| URSA-EXEC-001 | 2 | Trigger Execution | Make `POST /api/v1/dewey/run-analysis-triggers` launch when `auto_launch=true` using explicit workset/manifest/cluster execution context. | SUCCESS | `daylib_ursa/workset_api.py`; `tests/test_dewey_run_analysis_triggers.py::test_dewey_trigger_auto_launch_creates_analysis_job_and_replays`. | Auto-launch now creates workset/manifest as requested, defines an analysis job, calls the existing analysis job manager, and returns `analysis_job_euid`. |
| URSA-EXEC-002 | 2 | Permissions | Preserve scoped Dewey `X-API-Key` service auth while requiring explicit tenant/user attribution; do not rely on browser admin session for Dewey triggers. | SUCCESS | `DeweyRunAnalysisExecutionContext`; service-token tests in `tests/test_dewey_run_analysis_triggers.py`. | Trigger routes still require `X-API-Key`; auto-launch requires explicit `tenant_id` and `owner_user_id`. |
| URSA-STATE-001 | 3 | Durability | Persist trigger/idempotency state in TapDB/ResourceStore so replay cannot duplicate staging or analysis jobs. | SUCCESS | `daylib_ursa/resource_store.py`; `config/tapdb_templates/ursa/templates.json`; `daylib_ursa/tapdb_graph/backend.py`; replay test. | Added `RGX/dewey/run-analysis-trigger/1.0/` and ResourceStore create/get idempotency helpers; exact replay returns stored response without a second job. |
| URSA-RETURN-001 | 3 | Dewey Return | On terminal pass/fail, register analysis results back to Dewey with sample identifiers, artifact refs, status, and lineage. | SUCCESS | `_register_dewey_result_if_terminal`; `_register_analysis_job_dewey_result_if_terminal`; terminal test in `tests/test_dewey_run_analysis_triggers.py`. | Terminal `COMPLETED`/`FAILED` jobs with result-registration context call Dewey with status, sample identifiers, artifact refs, and Ursa lineage refs. |
| CLEANUP-001 | 4 | Admin Toggle | Add admin-only API and GUI control for auto cleanup on/off, 45-minute idle default, required S3 export destination, and receipt directory. | SUCCESS | `GET/PUT /api/v1/admin/cluster-cleanup-policy`; `/admin/config`; `docs/cluster_auto_cleanup.md`; admin/non-admin tests. | Policy is disabled by default, admin-only, and requires export source/destination/receipt directory when enabled. |
| CLEANUP-002 | 4 | Export Before Delete | Cleanup execution must DRA-export FSx analysis output to S3, verify successful export receipt, then delete; export failure blocks delete. | SUCCESS | `ClusterService.export_analysis_results`; `DaylilyEcClient.export_analysis_results`; `tests/test_admin_gui_and_cluster_routes.py::test_cluster_cleanup_policy_exports_before_delete_and_exposes_gui`; export-failure test. | Cleanup execute calls export, then delete-plan, then delete. Export failure marks candidate blocked and does not call delete. No live AWS delete was run. |
| QUALITY-001 | 5 | Quality Triage | Run `ursa quality check`; fix in-scope failures and classify unrelated pre-existing failures with exact evidence. | SUCCESS_WITH_RESIDUAL | `ursa test run` -> `334 passed, 2 skipped`; touched-file ruff check/format passed; `ursa quality check` lint passed but format/typecheck still failed. | Fixed in-scope touched-file format and typing issues. Residual quality: 12 unrelated files need formatting; mypy reports 67 errors in 16 files, concentrated in existing TapDB/config/gui/workset typing debt. |
| CROSS-001 | 6 | Cross-Service | Validate Dewey, DayEC, DayOA, QEO, Atlas handoff contracts; mark Bloom ULTIMA/hybrid wet-lab queue support `WONT_DO`. | SUCCESS | Dewey sequencer tests `6 passed`; DayEC catalog tests `8 passed`; Dewey QEO tests `17 passed`; DayOA QEO tests `8 passed`; Atlas Ursa return tests `11 passed`. | Private worktrees expose the expected Dewey, DayEC, DayOA/QEO, and Atlas contract surfaces. Bloom ULTIMA/hybrid wet-lab queue support remains `WONT_DO`; Zebra unchanged. |
| TEST-001 | 7 | Tests | Cover launch, auth, idempotency, Dewey terminal registration, cleanup toggle, export-before-delete, non-admin denial, and shell rejection. | SUCCESS | Focused Ursa tests `44 passed`; full `ursa test run` `334 passed, 2 skipped`; cross-repo focused tests passed. | Added regression tests for launch replay, service auth, terminal Dewey registration, cleanup policy, export-before-delete, export failure, non-admin denial, and shell rejection. |
| DOCS-001 | 7 | Ursa Docs | Update Ursa trigger docs, admin cleanup runbook, and execution ledger once local implementation succeeds. | SUCCESS | `docs/dewey_run_analysis_triggers.md`; `docs/cluster_auto_cleanup.md`; `README.md`; `docs/README.md`; this ledger. | Ursa trigger, Dewey return, cleanup policy, and export-before-delete behavior are documented. |
| DOCS-002 | 8 | Cross-Repo Docs | After successful cross-service validation, update documentation in every affected repo as warranted. | SUCCESS_WITH_SCOPE | Cross-repo docs inspected; Ursa docs updated; Dewey/DayEC/DayOA/QEO/Atlas docs already describe their current contracts. | No additional cross-repo doc edits were warranted by the Ursa-only implementation changes in this pass. |
| RELEASE-001 | 8 | Release Discipline | No main merge. No AWS deployment yet. When all service interactions pass, prepare numeric no-`v` tags and draft PRs for review only. | SUCCESS | Git branch remains private; no main merge performed. Cross-service release tagging/deploy evidence is tracked in Dayhoff ledger `docs/plans/20260527T154945Z_qeo_day_release_train_ledger.md`. | Ursa implementation is ready for numeric branch tag as part of the cross-service release train; no main merge and no live cleanup delete are included. |

## Acceptance Notes

- Live AWS deployment is intentionally out of scope for this implementation pass.
- No live cluster delete may be executed without a separate explicit destructive-action approval.
- Bloom ULTIMA/hybrid wet-lab queue support is intentionally `WONT_DO` for this plan.

## Terminal Validation

- Ursa focused trigger/cleanup tests: `pytest -q tests/test_dewey_run_analysis_triggers.py tests/test_admin_gui_and_cluster_routes.py -k 'dewey_trigger or cluster_cleanup'` -> `7 passed`.
- Ursa focused API regression: `pytest -q tests/test_dewey_run_analysis_triggers.py tests/test_worksets_api.py tests/test_admin_gui_and_cluster_routes.py` -> `44 passed`.
- Ursa full tests: `URSA_DEPLOYMENT_CODE=runtrig ursa test run` -> `334 passed, 2 skipped`.
- Cross-repo focused tests:
  - Dewey sequencer registration: `pytest -q tests/test_sequencer_run_registration.py` -> `6 passed`.
  - DayEC catalog: `pytest -q tests/test_repository_catalog.py` -> `8 passed`.
  - Dewey QEO registration: `pytest -q tests/test_qeo_artifact_set_registration.py tests/test_qeo_multiqc_registration.py tests/test_qeo_registration_events.py tests/test_qeo_registration_security.py` -> `17 passed`.
  - DayOA QEO registration: `python -m pytest -q tests/test_qeo_registration.py` -> `8 passed`.
  - Atlas Ursa return: `pytest -q tests/test_ursa_result_return_service.py tests/test_ursa_integration_api.py` -> `11 passed`.
- Touched-file lint/format: `ruff check` and `ruff format --check` over touched code/tests -> passed.
- Touched-file lint/format rerun: `ruff check ... && ruff format --check ...` over touched Ursa code/tests -> passed.
- `URSA_DEPLOYMENT_CODE=runtrig ursa quality check`: lint passed; format failed on 12 unrelated files; typecheck failed with 67 errors in 16 files. The command exits `0` despite reporting failed checks, so the ledger records the textual failure rather than trusting the exit code.
- No AWS deployment, no live cleanup execution, no live cluster delete, no main merge, no tag, and no PR were performed.
