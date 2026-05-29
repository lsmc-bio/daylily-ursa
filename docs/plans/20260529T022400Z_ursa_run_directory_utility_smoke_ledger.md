# Ursa Run-Directory Utility Smoke Command Ledger

## Gate 0 Inventory

- Ursa repo: `/Users/jmajor/projects/mega_dayhoff/repos_work/daylily-ursa`
- Branch: `codex/ursa-release-train-20260529`
- Baseline status: clean against `origin/codex/ursa-release-train-20260529`
- Baseline tag: `4.0.30`
- Requested behavior: allow the OWY run-directory trigger path to use the
  simple DayEC utility command that runs `dy-r help`.
- Current route behavior:
  `daylib_ursa/workset_api.py` rejects run-directory commands unless
  `command_class=run_analysis` and `input_contract=run_context`.
- Current launch behavior:
  `daylib_ursa/analysis_jobs.py` injects a run-context file for every
  `run_directory_trigger`, and rejects non-`run_analysis` commands without a
  staging directory.
- DayEC catalog evidence from the OWY-side inspection:
  `simple-test` runs
  `source dyoainit; dy-a local hg38; dy-r -p -k -j 1 help`, with
  `command_class=utility`, `input_contract=none`, `requires_staging=false`, and
  `requires_run_mount=false`.

## Work Ledger

| ID | Task | Status | Evidence | Notes |
| --- | --- | --- | --- | --- |
| G0-001 | Record baseline and route/launch constraints. | SUCCESS | This ledger. |  |
| API-001 | Permit run-directory utility commands only when they need no input contract, staging, or run mount. | SUCCESS | `daylib_ursa/workset_api.py` | Production run-analysis commands remain accepted as before. |
| EXEC-001 | Launch run-directory utility commands without run-context file or staging directory. | SUCCESS | `daylib_ursa/analysis_jobs.py` | Needed for `simple-test` / `dy-r help`. |
| TEST-001 | Add route and launch coverage for utility command acceptance. | SUCCESS | `tests/test_dewey_run_analysis_triggers.py` | Preserves rejection for sample-analysis commands. |
| DOC-001 | Document utility smoke-command allowance. | SUCCESS | `docs/dewey_run_analysis_triggers.md` |  |
| DEP-001 | Check installed DayEC package availability for `simple-test`. | SUCCESS | `pip index versions daylily-ephemeral-cluster` reports latest `5.0.31`; `python -m pip install --dry-run --no-deps daylily-ephemeral-cluster==5.0.31` succeeded after PyPI propagation. | Ursa active dependency, runtime guard, docs, ecosystem metadata, and tests now pin exact `daylily-ephemeral-cluster==5.0.31`, which contains the DayEC `simple-test` utility command. |
| VALID-001 | Run focused Ursa validation. | SUCCESS | `source ./activate owysmoke && python -m pytest -q tests/test_dewey_run_analysis_triggers.py tests/test_dayec_run_directory_command_catalog.py tests/test_activation_metadata.py tests/test_cluster_headnode_diagnostics.py tests/test_admin_gui_and_cluster_routes.py -k 'run_directory or simple_test or simple-test or daylily_ec or ecosystem or cluster_detail'` -> `28 passed, 44 deselected`; focused `ruff check` -> passed; `git diff --check` -> passed. | Validation ran after the `daylily-ephemeral-cluster==5.0.31` lock/install update. |
