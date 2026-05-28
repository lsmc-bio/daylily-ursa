# Ursa Run-Directory Analysis Trigger Ledger

Started: 2026-05-28T04:37:46Z  
Repo: `/Users/jmajor/projects/mega_dayhoff/repos_work/daylily-ursa-4.0.3-owy-run-triggers`  
Controlling plan: OWY Run-Directory Analysis Automation With Ursa 4.0.3 Inspection Gate

## Gate 0: Inventory Freeze

- Ursa repo status before this ledger: `## codex/owy-run-directory-analysis-20260528`; `HEAD=ec75bacd843edf3aec0731d0ec376796f474843b`; exact tag `4.0.3`
- Fresh Ursa clone path: `/Users/jmajor/projects/mega_dayhoff/repos_work/daylily-ursa-4.0.3-owy-run-triggers`
- Ursa `4.0.3` peeled commit: `ec75bacd843edf3aec0731d0ec376796f474843b`
- DayEC catalog path: `/Users/jmajor/.codex/worktrees/dyec-fsx-dra-mounts/daylily-ephemeral-cluster`
- DayEC `5.0.14` peeled commit: `28cbc61c0754b096fc74f4beb6d9ea404f43bbec`
- DayEC run-analysis command IDs observed in `config/daylily_available_repositories.yaml`: `illumina_run_qc`, `illumina_bclconvert`, `illumina_run_qc_bclconvert`, `ont_run_qc`, `ultima_run_qc`
- Existing Ursa route inspected: `POST /api/v1/dewey/run-analysis-triggers`
- Existing API sufficiency decision: insufficient. `daylib_ursa/workset_api.py` validates that `manifest.metadata.analysis_samples_manifest.content` is required for existing Dewey trigger manifests, and `docs/dewey_run_analysis_triggers.md` states Ursa will not infer a sample manifest from filesystem paths.
- Exact reason for Ursa changes: OWY owns a completed sequencing run directory S3 prefix and Dewey artifact EUID, not a caller-supplied sample-analysis manifest. Ursa must accept a run-directory trigger, derive run context, create or reuse Bloom run context, validate DayEC `run_analysis` command IDs, and return durable trigger/job identifiers.
- Bloom companion ledger decision: not created at Gate 0. Local Bloom inspection shows only a beta Atlas-facing create-run API; Ursa will call an explicit Ursa-facing Bloom endpoint through its client and fail hard if unavailable. A Bloom ledger is required only if production Bloom lacks that endpoint and the live/API contract must be changed.
- Live actions excluded from this implementation gate: production Bloom/Dewey/Ursa mutation, production cluster launch, xfer1 deployment, SeqNAS mutation, S3 deletion.

## Work Ledger

| ID | Area | Requirement | Status | Category | Approval Gate | Owner | Evidence | Root Cause | Terminal Note |
|---|---|---|---|---|---|---|---|---|---|
| URSA-001 | Inspection | Prove whether existing Ursa 4.0.3 APIs satisfy OWY run-directory trigger flow. | SUCCESS | not_applicable_after_inspection | Gate 0 | orchestrator | `docs/dewey_run_analysis_triggers.md`; `daylib_ursa/workset_api.py`; API requires `analysis_samples_manifest.content` and does not infer from filesystem paths. |  | Existing API is insufficient; fresh 4.0.3 clone/change is required. |
| URSA-002 | API | Add `POST /api/v1/dewey/run-directory-analysis-triggers` for Dewey sequencing run-dir artifacts. | SUCCESS | feature_implementation | Gate 1 | orchestrator | `daylib_ursa/workset_api.py`; `tests/test_dewey_run_analysis_triggers.py` |  | New endpoint accepts Dewey run-dir EUID, S3 URI, run folder, platform, and ordered command IDs. |
| URSA-003 | Command validation | Validate command IDs against DayEC 5.0.14 and accept only `command_class=run_analysis`. | SUCCESS | feature_implementation | Gate 1 | orchestrator | `tests/test_dayec_run_directory_command_catalog.py`; `uv.lock` DayEC `28cbc61c...` |  | Validated `illumina_run_qc`, `illumina_bclconvert`, `illumina_run_qc_bclconvert`, `ont_run_qc`, and `ultima_run_qc`. |
| URSA-004 | Run context | Derive `config/runs.tsv` run context from S3 run directory metadata without caller-supplied sample manifests. | SUCCESS | feature_implementation | Gate 1 | orchestrator | `build_run_context_tsv()`; run-context launch test |  | Endpoint writes a run-context manifest using the Dewey artifact S3 URI and run folder name. |
| URSA-005 | Bloom handoff | Create or reuse a Bloom run named exactly as the run directory folder, then link the Bloom EUID in the trigger response. | SUCCESS | active_product_contract | Gate 3 | orchestrator | `BloomResolverClient.create_or_reuse_run_directory_run()`; endpoint tests | production Bloom API not exercised | Ursa now calls explicit `/api/v1/external/ursa/run-directories` and fails hard if unavailable. |
| URSA-006 | Analysis jobs | Create durable Ursa trigger/job records and launch ordered DayEC run-analysis commands. | SUCCESS | feature_implementation | Gate 1 | orchestrator | `create_analysis_job`; `launch_analysis_job`; `tests/test_dewey_run_analysis_triggers.py` |  | First job launches immediately; successor jobs launch when the predecessor refreshes to `COMPLETED`. |
| URSA-007 | Dewey relations | Link Bloom run EUID, Ursa trigger/job EUIDs, and Dewey run artifact EUID through Dewey external-object relations where API support exists. | SUCCESS | feature_implementation | Gate 1 | orchestrator | `DeweyClient.create_external_object()`; `attach_external_object_relation()`; relation test |  | Relation failures fail the trigger request rather than being ignored. |
| URSA-008 | Tests | Add endpoint tests for validation, run context derivation, Bloom create/reuse, ordered command launch, and relation persistence. | SUCCESS | contract_test | Gate 5 | orchestrator | `tests/test_dewey_run_analysis_triggers.py`; `tests/test_dayec_run_directory_command_catalog.py` |  | Added endpoint, catalog, launch, and relation coverage. |
| URSA-009 | Validation | Run focused tests plus `pytest -q`, `ruff check .`, `ruff format --check .`, and `git diff --check` if Ursa changes are made. | SUCCESS | contract_test | Gate 5 | orchestrator | `CONDA_DEFAULT_ENV=ursa-test uv run pytest -q`: `343 passed, 2 skipped`; `ruff check .`; `ruff format --check .`; `git diff --check` |  | Full local Ursa validation completed with deployment-scoped conda env name for CLI runtime checks. |
| URSA-010 | Live acceptance | Production trigger for completed ILMN run using `illumina_run_qc` after local validation. | BLOCKED | active_product_contract | Gate 5 | orchestrator | Not run | live approval, production tokens, and production Bloom endpoint availability not exercised | Requires an explicit production mutation window before Dewey/Bloom/Ursa writes or cluster work. |

## Status Log

- 2026-05-28T04:50Z: Gate 0 recorded. Existing Ursa 4.0.3 API gap confirmed before implementation edits.
- 2026-05-28T06:20Z: Implemented fresh Ursa 4.0.3 endpoint, DayEC 5.0.14 command validation, run-context manifest generation, Bloom handoff client, Dewey relation persistence, ordered job creation, successor launch on predecessor completion, and DayEC 5.0.14 cluster config threading. Local validation passed: `uv run ruff check .`, `uv run ruff format --check .`, `CONDA_DEFAULT_ENV=ursa-test uv run pytest -q` (`343 passed, 2 skipped`), and `git diff --check`.
