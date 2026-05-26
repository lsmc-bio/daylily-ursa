# Ursa Bucket Contract Release Ledger

Controlling plan: Ursa side of the 15-agent bucket contract release and `bucketsamok` validation.
Ledger path: `docs/plans/20260526T185422Z_bucket_contract_ursa_release_ledger.md`
Created: 2026-05-26T18:54:22Z

## Gate 0 Baseline

- Repo: `/Users/jmajor/projects/lsmc/daylily-ursa`
- Branch/head: `main`, `b22b2d230fbf7eb47c33133d2a3668858d7fc61d`
- Remote: `git@github.com:lsmc-bio/daylily-ursa.git`
- Dirty state at Gate 0: clean, behind `origin/main` by 26 commits.
- Latest local major tag: `3.0.0`; service context says active line is `3.0.6`.
- Current pins: DayEC `2.2.8`, DayOA `0.7.752` in `pyproject.toml`/`config/ecosystem-versions.json`.
- Sweep command: `rg -n "reference_bucket|control_data_bucket|stage_bucket|--reference-bucket|--control-data-bucket|--stage-bucket|bucket-or-prefix|/fsx/runtime_assets|/fsx/data|/data/staged_sample_data|lsmc-dayoa-omics-analysis-us-west-2" daylib_ursa bin config tests README.md AGENTS.md -S`
- Gate 0 hits: old `reference_bucket` request fields, old `--reference-bucket` CLI calls, `/data/staged_sample_data`, `/fsx/data`, old monolith bucket comments/examples, and DayEC `2.2.8` contract assumptions.

## Control Ledger

| ID | Agent | Area | Requirement | Status | Category | Approval Gate | Evidence | Root Cause | Terminal Note |
|---|---|---|---|---|---|---|---|---|---|
| URSA-BKT-001 | Agent 12 | Repo state | Bring release work onto a branch based on current remote main before implementation. | SUCCESS | config_or_startup_contract | Gate 0 | Fetched origin and created `codex/bucket-contract-dayec-5` from `origin/main` at `71f2949f789ebdb540f4eb56bb7eb9c6c31d89dc`; fetched tags include `3.0.6`. |  | Release work is based on current remote main. |
| URSA-BKT-002 | Agent 12 | API contract | Replace `reference_bucket` request/UI/API contract with explicit S3 URI naming. | SUCCESS | feature_implementation | Gate 1 | API/UI/config/tests now use `reference_s3_uri`, `control_data_s3_uri`, and `stage_s3_uri`; focused Ursa suite -> `114 passed`. |  | Public create/check-all contract is explicit S3 URI naming. |
| URSA-BKT-003 | Agent 12 | DayEC runner | Replace `--reference-bucket` calls with new DayEC CLI flags. | SUCCESS | feature_implementation | Gate 1 | `daylib_ursa/ephemeral_cluster/runner.py` maps DayEC cluster config fields to `reference_s3_uri`, `control_data_s3_uri`, and `stage_s3_uri`; local editable DayEC `5.0.0` installed in `URSA-lsmc`; focused Ursa suite -> `114 passed`. |  | Runner matches DayEC 5 contract locally. |
| URSA-BKT-004 | Agent 12 | Staging target | Replace `/data/staged_sample_data` and `/fsx/data` assumptions with `/staging/staged_external_sequencing_data` contract. | SUCCESS | feature_implementation | Gate 1 | Stage helpers default to `/staging/staged_external_sequencing_data`; `/data...` and `/fsx/data...` are rejected; active scan only finds explicit negative rejection guards/tests; focused Ursa suite -> `114 passed`. |  | Staging namespace is hard-fail only for the retired paths. |
| URSA-BKT-005 | Agent 12 | Pins | Pin final DayEC major and DayOA `2.0.0` after upstream releases. | SUCCESS | config_or_startup_contract | Release gate | DayEC `5.0.0` and DayOA `2.0.0` tags exist; `pyproject.toml`, `config/ecosystem-versions.json`, workset monitor configs, and tests are pinned to DayEC `5.0.0` and DayOA `2.0.0`; focused Ursa suite -> `114 passed`. |  | Final pins are ready for Ursa release. |
| URSA-BKT-006 | Agent 13 | Release | PR-merge/tag Ursa next major after tests and final pins. | BLOCKED | config_or_startup_contract | Release gate | Expected next major from service line: `4.0.0` unless remote tags differ. | Requires implementation, tests, PR merge. |  |

## Acceptance Checks

- Ursa tests for DayEC runner, staging jobs, workset API, GUI routes, activation metadata, and stage helpers passed: `114 passed`.
- Active scan is clean for old DayEC bucket/path contract.
- Ursa final release pins the new DayEC major and DayOA `2.0.0`.
