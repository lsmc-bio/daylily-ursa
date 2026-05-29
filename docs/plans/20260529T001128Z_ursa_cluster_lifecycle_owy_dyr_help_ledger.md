# Ursa Compute Cluster Lifecycle + OWY `dy-r help` Rollout Ledger

Date: 2026-05-29T00:11:28Z

## Objective

Bring the OWY rollout's remaining Agent 8 and Agent 9 rows to terminal states by
making Ursa explicitly model compute clusters and cluster jobs, expose the same
actions through API/CLI/GUI, and prove an OWY-style `dy-r help` command can be
placed on a cluster, complete, and close the Ursa analysis job lifecycle.

## Gate 0 Inventory

- Controlling user request: complete OWY Agent 8 and Agent 9; add Ursa compute
  cluster and cluster job top-level objects; support vanilla Slurm, AWS
  ParallelCluster Slurm, and generic clusters/jobs; assign `cluster_euid` per
  cluster and `analysis_experiment_euid` to array-cell-defined work; add GUI CLI
  visualization mode; ensure new functionality is available via CLI and GUI.
- Ledger path:
  `docs/plans/20260529T001128Z_ursa_cluster_lifecycle_owy_dyr_help_ledger.md`.
- Ursa worktree:
  `/Users/jmajor/.codex/worktrees/ursa-cluster-lifecycle-20260528/daylily-ursa`.
- Ursa branch: `codex/ursa-cluster-lifecycle-20260528`, tracking
  `origin/main`.
- Ursa base: `cebdeb7` / tag `4.0.25`, "Release Ursa with DYEC 5.0.28".
- Existing dirty Ursa checkouts were left untouched:
  - `/Users/jmajor/projects/daylily/daylily-ursa`: dirty `AGENTS.md`.
  - `/Users/jmajor/projects/lsmc/daylily-ursa`: dirty `AGENTS.md`.
  - `/Users/jmajor/projects/mega_dayhoff/repos_work/daylily-ursa`: dirty
    `daylib_ursa/container_entry.py` plus untracked
    `tests/test_container_entry_runtime.py`.
- OWY status: branch `codex/owy-run-directory-analysis-20260528`, clean at
  `22514ea`, tag `0.1.20`.
- DayOA status at inventory: branch
  `codex/dayoa-local-evidence-dewey-refactor-20260528`, dirty `README.md`
  outside this Ursa worktree.
- DYEC status at inventory: branch `codex/docs-plans-ledgers`, dirty/untracked
  files outside this Ursa worktree.
- Production Ursa OpenAPI at `https://ursa.day.lsmc.bio/openapi.json` returned
  HTTP 200 and listed 117 paths, including cluster, analysis-job, and
  Dewey-trigger endpoints.
- Known live blocker from OWY ledger: OWY write token receives HTTP 401 from
  Ursa analysis job/workset/manifest read endpoints, and trigger readback for
  `URDT-6844A94027E8A699` returned HTTP 500.
- No destructive DRA, FSx, S3 cleanup, or cluster deletion is approved in this
  turn.

## Tracking Rows

| ID | Area | Requirement | Status | Category | Approval Gate | Owner | Evidence | Root Cause | Terminal Note |
|---|---|---|---|---|---|---|---|---|---|
| GATE-001 | Inventory | Record Gate 0 before code edits. | SUCCESS | contract_test | Gate 0 | Agent 1 | Gate 0 inventory above. |  | Current source and live blockers recorded before implementation. |
| MODEL-001 | Ursa model | Add first-class compute cluster object with `cluster_euid`, explicit backend types `generic`, `vanilla_slurm`, and `aws_parallelcluster_slurm`. | SUCCESS | feature_implementation | Gate 1 | Agent 2 | `ComputeClusterRecord`; `ResourceStore.create_compute_cluster/get/list/update_compute_cluster_state`; TapDB template `RGX/compute/cluster/1.0/`; `tests/test_resource_store_canonical_jobs.py`. |  | Compute cluster identity is explicit and duplicate active name+region is rejected. |
| MODEL-002 | Ursa model | Add first-class cluster job object with `cluster_job_euid`, explicit job types `generic` and `slurm`, and link to compute cluster plus analysis job. | SUCCESS | feature_implementation | Gate 1 | Agent 2 | `ClusterJobRecord` now carries `cluster_job_euid`, `cluster_euid`, `job_type`, `analysis_job_euid`, `scheduler_job_id`; lineage `compute_cluster_job`; focused tests pass. |  | Existing `/api/v1/clusters/jobs` remains; top-level `/api/v1/cluster-jobs` is the durable object surface. |
| MODEL-003 | Ursa model | Assign `analysis_experiment_euid` to array-cell-defined analysis work. | SUCCESS | feature_implementation | Gate 1 | Agent 2 | `analysis_samples_manifest.analysis_experiments`; run-directory jobs derive deterministic `URXP-*` from run-context row, command ID, and pipeline order; tests in `test_worksets_api.py` and `test_dewey_run_analysis_triggers.py`. |  | EUIDs are evidence identifiers, not sample identity or QC disposition. |
| API-001 | Ursa API | Expose compute cluster and cluster job create/read/list/update surfaces without fallback or inferred defaults. | SUCCESS | feature_implementation | Gate 2 | Agent 3 | `GET/POST /api/v1/compute-clusters`, `GET /api/v1/compute-clusters/{cluster_euid}`, `POST /api/v1/compute-clusters/{cluster_euid}/state`, `GET/POST /api/v1/cluster-jobs`, `GET /api/v1/cluster-jobs/{cluster_job_euid}`; route-coverage tests pass. |  | Invalid cluster/job types fail through Pydantic literals and store validation. |
| API-002 | Ursa API | Fix OWY service-token readback for run-directory triggers and associated analysis job lifecycle. | SUCCESS | feature_implementation | Gate 2 | Agent 3 | `GET /api/v1/dewey/run-directory-analysis-triggers/{trigger_euid}` and `URDT-*` handling in generic `GET /api/v1/dewey/run-analysis-triggers/{trigger_euid}`; test proves readback refreshes `COMPLETED` job state. | Prior production `URDT-*` generic GET returned response-model HTTP 500. | Readback returns run-directory response shape and current analysis job rows. |
| CLI-001 | Ursa CLI | Add CLI commands for compute-cluster and cluster-job actions matching API behavior. | SUCCESS | feature_implementation | Gate 3 | Agent 4 | `daylib_ursa/cli/api.py`; registry exposes `api request`, `compute-clusters`, `cluster-jobs create/start/get/list`, and `run-directory-triggers`; CLI registry tests pass. |  | Commands require explicit `--api-base-url` and `--token`; no environment token fallback. |
| GUI-001 | Ursa GUI | Add CLI visualization mode for GUI actions with CLI analogs, floating command popup, and copy button. | SUCCESS | feature_implementation | Gate 3 | Agent 5 | `portal.js` CLI Viz toggle/popup/copy support; `main.css`; static tests and `node --check` pass. |  | GUI renders `<TOKEN>` placeholder instead of secrets. |
| GUI-002 | Ursa GUI | Surface compute clusters and cluster jobs without card-in-card clutter and preserve existing cluster UX. | SUCCESS | feature_implementation | Gate 3 | Agent 5 | `clusters.html` compute-cluster list/register surface plus queued-job Start action; API route tests pass. |  | Existing cluster page behavior and `/api/v1/clusters` routes are preserved. |
| LIFE-001 | Lifecycle | Ensure `dy-r help` can be represented, launched, completed, and reflected in Ursa analysis job lifecycle. | SUCCESS_LOCAL | feature_implementation | Gate 4 | Agent 6 | `run_dayoa_dyr_help_job` validates explicit request fields, creates an `ubuntu` headnode tmux session through SSM, runs `source dyoainit`, `dy-a`, and `dy-r help`, and persists captured output/return code. Focused worker/API/CLI/GUI tests pass. | Live cluster placement still requires production deploy and explicit live trigger/run. | Local lifecycle contract is implemented and tested; live execution remains in `OWY-001`. |
| OWY-001 | Live validation | Trigger/register an OWY-style `dy-r help` run on a cluster and verify returned terminal lifecycle. | OPEN | feature_implementation | Gate 5 | Agent 7 |  |  |  |
| DRA-001 | DRA/export | Verify DRA/export lifecycle or keep blocked only for explicit missing live prerequisite/destructive approval. | OPEN | legitimate_safety_handling | Gate 5 | Agent 8 |  |  |  |
| DOC-001 | Docs | Document new object model, CLI/GUI usage, OWY `dy-r help` lifecycle, and remaining destructive gate boundaries. | SUCCESS | contract_test | Gate 6 | Agent 9 | `README.md`, `docs/README.md`, `docs/dewey_run_analysis_triggers.md`, `docs/compute_cluster_lifecycle.md`. |  | Docs now state no default cluster placement, CLI/GUI parity, readback routes, and destructive cleanup gate boundaries. |
| TEST-001 | Tests | Add focused API/model/CLI/GUI-contract tests and run relevant suites. | SUCCESS | contract_test | Gate 6 | Agent 10 | `python -m pytest -q tests` -> `364 passed, 2 skipped`; `ruff check ...` passed; `node --check daylib_ursa/gui/static/portal.js` passed; `git diff --check` passed. | Initial full run exposed missing direct route samples, then fixed. | Local validation is green. |

## Validation Log

- 2026-05-29T00:23Z focused compile/tests: `python -m compileall -q
  daylib_ursa && python -m pytest -q tests/test_resource_store_canonical_jobs.py
  tests/test_dewey_run_analysis_triggers.py tests/test_cli_registry_v2.py
  tests/test_worksets_api.py tests/test_admin_gui_and_cluster_routes.py` -> `81
  passed`.
- 2026-05-29T00:27Z full tests first pass: `363 passed, 2 skipped, 1
  failed`; the only failure was direct route-coverage for newly added routes.
- 2026-05-29T00:28Z route coverage focused rerun:
  `tests/test_admin_gui_and_cluster_routes.py tests/test_v1_api_contracts.py` ->
  `28 passed`.
- 2026-05-29T00:29Z full tests final: `python -m pytest -q tests` -> `364
  passed, 2 skipped`.
- 2026-05-29T00:30Z lint/static checks: `ruff check ...`, `node --check
  daylib_ursa/gui/static/portal.js`, and `git diff --check` all passed.
- 2026-05-29T00:31Z live read-only Ursa inventory:
  `https://ursa.day.lsmc.bio/healthz` and `/readyz` returned `status=ok`,
  build `4.0.25`; OpenAPI reported version `4.0.25` and 117 paths.
- 2026-05-29T00:45Z production `4.0.26` readback probe:
  `GET /api/v1/dewey/run-directory-analysis-triggers/URDT-6844A94027E8A699`
  and generic `GET /api/v1/dewey/run-analysis-triggers/URDT-...` both returned
  HTTP 200. The durable OWY job remains `FAILED`.
- 2026-05-29T00:50Z old OWY failure root cause from headnode Snakemake log:
  `/fsx/analysis_results/xfer-cluster/M-RGX-9T77/daylily-omics-analysis/config/units.tsv`
  was missing; this is not a Dewey/Ursa readback failure.
- 2026-05-29T00:53Z focused local validation for new cluster-job execution:
  `CONDA_DEFAULT_ENV=URSA-test python -m pytest -q
  tests/test_cluster_job_worker.py
  tests/test_admin_gui_and_cluster_routes.py::test_compute_cluster_and_cluster_job_routes_are_first_class_objects
  tests/test_admin_gui_and_cluster_routes.py::test_gui_static_assets_include_cli_viz_mode_and_compute_cluster_surface
  tests/test_cli_registry_v2.py::test_cli_registry_exposes_v2_command_tree_and_policies
  tests/test_cli_registry_v2.py::test_key_command_help_includes_tested_examples
  tests/test_v1_api_contracts.py` -> `13 passed`.
- 2026-05-29T00:53Z static checks:
  `ruff check ...`, `node --check daylib_ursa/gui/static/portal.js`, and
  `git diff --check` passed.
- 2026-05-29T00:52Z broader local suite note: the local editable
  `daylily-ephemeral-cluster` reports `2.0.2` from package metadata and source
  checkout `5.0.27-dirty`, while Ursa requires exact `5.0.28`. Cluster-create
  dry-run tests that call the live local DayEC helper fail in this workstation
  environment; production Ursa is expected to use the pinned `5.0.28` runtime.

## Release/Live Gate

- `4.0.26` was committed, annotated, pushed, and deployed to production; public
  health/readiness and OpenAPI returned build/version `4.0.26`.
- Next release for the explicit headnode `dy-r help` cluster-job execution path
  is `4.0.27`.
- No cluster deletion, staged-data deletion, DRA mount deletion, or other
  destructive cleanup is included in this ledger without a second explicit
  approval naming the exact resource.
