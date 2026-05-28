# OWY -> Ursa 500 Fix With DYEC 5.0.22 Ledger

Control ledger path: `/Users/jmajor/projects/mega_dayhoff/repos_work/release_worktrees/daylily-ursa-4-0-10-inf5-build-20260528/docs/plans/20260528T165200Z_owy_ursa_500_request_61456fbc_ledger.md`

Repo: `/Users/jmajor/projects/mega_dayhoff/repos_work/release_worktrees/daylily-ursa-4-0-10-inf5-build-20260528`

## Summary

Implement the OWY -> Ursa run-directory trigger fix and move Ursa to exact DYEC `5.0.22`, where DYEC is the `daylily-ephemeral-cluster` Python package used by Ursa.

Production deploy remains blocked until this exact approval phrase is received:

`APPROVE URSA PROD OWY FIX DEPLOY us-west-2 ursa.day.lsmc.bio`

No destructive AWS action is included. No production service restart, deploy, cron unpause, or live OWY re-trigger is approved by this ledger.

## Gate 0 Inventory Freeze

Recorded: 2026-05-28

- Instructions read:
  - `/Users/jmajor/.agents/AGENTS.md`
  - `/Users/jmajor/.codex/AGENTS.md`
  - `/Users/jmajor/.codex/docs/plan-ledger-workflow.md`
  - `/Users/jmajor/.codex/memories/aws-destructive-changes.md`
  - `/Users/jmajor/.codex/memories/fallback_and_legacy_and_migration_support_for_code_changes_DO_NOT_UNLESS_TOLD_TO_PLEASE.md`
  - `/Users/jmajor/projects/mega_dayhoff/dayhoff/AGENTS.md`
  - `/Users/jmajor/projects/mega_dayhoff/repos_work/release_worktrees/daylily-ursa-4-0-10-inf5-build-20260528/AGENTS.md`
- `git fetch --all --tags --prune && git status --short --branch`:
  - `## codex/ursa-4-0-11-docker-template-pack-20260528`
  - no dirty tracked files at inventory.
- `git log --oneline -5 --decorate`:
  - `1db7904 (HEAD -> codex/ursa-4-0-11-docker-template-pack-20260528, tag: 4.0.13, origin/codex/ursa-4-0-11-docker-template-pack-20260528) Document OWY run directory trigger policy`
  - `d3eadc7 (tag: 4.0.12) Show created Ursa tokens without reload`
  - `80f41c9 (tag: 4.0.11) Include Ursa TapDB templates in container image`
  - `e4e8a3e (tag: 4.0.9, tag: 4.0.10, origin/codex/owy-run-directory-analysis-20260528) Merge tag '4.0.8' into codex/owy-run-directory-analysis-20260528`
  - `e2f6968 Lock DAY-EC 5.0.20 for OWY run triggers`
- Latest local Ursa tags:
  - `4.0.13`, `4.0.12`, `4.0.11`, `4.0.10`, `4.0.9`, `4.0.8`, `4.0.7`, `4.0.6`, `4.0.5`, `4.0.4`
- DYEC availability:
  - `python -m pip index versions daylily-ephemeral-cluster` -> latest and available `5.0.22`.
  - active global install observed by pip was unrelated/stale `2.0.2`; repo lock currently resolves `5.0.20`.
- Current DYEC surfaces found by `rg`:
  - `pyproject.toml`: `daylily-ephemeral-cluster>=5.0.19`
  - `uv.lock`: `daylily-ephemeral-cluster` locked at `5.0.20`
  - `daylib_ursa/ephemeral_cluster/runner.py`: minimum/requirement constants use `5.0.19` and `>=`.
  - `config/ecosystem-versions.json`: current/tested combination uses `>=5.0.19`.
  - `README.md`, `daylib_ursa/analysis_jobs.py`, `daylib_ursa/analysis_commands.py`, `daylib_ursa/cluster_service.py`: docs/docstrings mention `>=5.0.19`.
  - tests reference `5.0.19` in `tests/conftest.py`, `tests/test_activation_metadata.py`, `tests/test_cluster_headnode_diagnostics.py`, and `tests/test_admin_gui_and_cluster_routes.py`.
- OWY failure context:
  - endpoint: `POST https://ursa.day.lsmc.bio/api/v1/dewey/run-directory-analysis-triggers`
  - request id: `61456fbc`
  - time: about `2026-05-28T16:10:49Z`
  - OWY execution: `dc5f4e8c-9e0f-48dd-810b-e0b66a3f32b9`
  - response: `HTTP 500 {"error":"An internal error occurred","request_id":"61456fbc"}`
  - prior policy-config `503` was reported fixed by Ursa `4.0.13`.
- Spawned worker agents:
  - Agent 1 production forensics: `019e6f9a-8118-7fe3-b7ed-833630bdd07b`
  - Agent 2 contract sanity review: `019e6f9a-9286-7f11-b238-f70060dd2920`
  - Agent 3 DYEC surface review: `019e6f9a-a3f7-7403-8628-27916f811fd9`
  - Agent 4 release verification planning: `019e6f9a-b2af-7070-b16d-4cd5752306ab`
- SSM note:
  - Local `aws ssm start-session` failed because `SessionManagerPlugin is not found`.
  - Agent 1 used read-only SSM Run Command as a fallback inspection path and reported no file edits, no deploy, no restart, no cron unpause, and no destructive AWS action.
- Release-line note:
  - Pre-commit tag audit found `4.0.14` on disjoint branch `codex/inf6-deploy-formalization-20260528`.
  - `git grep` on `4.0.14` showed `pyproject.toml` still using `daylily-ephemeral-cluster @ git+https://github.com/Daylily-Informatics/daylily-ephemeral-cluster.git@4.0.9` and no OWY run-directory route evidence.
  - Merging `4.0.14` into this OWY line would regress the requested route/DYEC work, so this ledger amends the release target to `4.0.15` without merging that disjoint tag.

## Gates

| Gate | Purpose | Status | Evidence |
|---|---|---|---|
| 0 | Inventory freeze | SUCCESS | Git/tag/DYEC/source inventory above. |
| 1 | Production read-only request forensics | OPEN | Agent 1 assigned; no production mutation approved. |
| 2 | Recommendation sanity review and root-cause decision | OPEN | Agent 2 assigned; local route/source inspection started. |
| 3 | Local reproduction | OPEN | Exact OWY payload fixture to be added. |
| 4 | Ursa fix and DYEC 5.0.22 update | OPEN | Source edits pending. |
| 5 | Release tag preparation | OPEN | Fetched tags changed during execution; `4.0.14` now exists, so final target is `4.0.15`. |
| 6 | Approval-gated production deploy | BLOCKED | Requires exact approval phrase. |
| 7 | OWY acceptance retry | BLOCKED | Requires deployed fixed Ursa and user/OWY retry approval. |
| 8 | Terminal report | OPEN | Pending. |

## Ledger Rows

| ID | Owner | Requirement | Status | Category | Gate | Evidence | Root Cause | Terminal Note |
|---|---|---|---|---|---|---|---|---|
| LEDGER-001 | Orchestrator | Create ledger with OWY handoff, prohibitions, approval phrase, and row table. | SUCCESS | plan_amendment | 0 | This file created under `docs/plans/`. |  | Ledger initialized before code edits. |
| INV-001 | Orchestrator | Record Ursa git status, tags, branch, current `4.0.13` evidence, route code, and DYEC surfaces. | SUCCESS | plan_amendment | 0 | Gate 0 inventory section. |  | Inventory complete. |
| DYEC-001 | Agent 2 | Confirm DYEC means Ursa's `daylily-ephemeral-cluster` dependency. | SUCCESS | plan_amendment | 0 | User corrected `dyrc` typo to `dyec`; Ursa source maps this to `daylily-ephemeral-cluster`. |  | Exact package target confirmed. |
| DYEC-002 | Agent 4 | Verify `daylily-ephemeral-cluster==5.0.22` availability from approved install source. | SUCCESS | config_or_startup_contract | 0 | `pip index versions daylily-ephemeral-cluster` lists `5.0.22`. |  | Dependency is available. |
| PROD-001 | Agent 1 | Verify production `ursa.day.lsmc.bio` health, OpenAPI version, route presence, runtime mode, and deployed commit/tag. | SUCCESS | legitimate_safety_handling | 1 | Public health -> service `ursa`, environment `lsmcok1`, build `4.0.13`; OpenAPI `4.0.13`, route present. Agent 1 read-only SSM evidence: instance `i-09126000eb19643b0`, host `ip-10-0-0-77`, direct `ubuntu` process, cwd `/home/ubuntu/.cache/dayhoff/local/lsmcok1/repos/daylily-ursa`, env `/home/ubuntu/miniconda3/envs/URSA-lsmcok1`, log `/home/ubuntu/.config/ursa-lsmcok1/logs/server_20260528_154632.log`, source `4.0.13-1-g8a945c2`, HEAD `8a945c228a219eff658cca2b6560c47ced9c1c05`. |  | Production runtime and route verified read-only. |
| PROD-002 | Agent 1 | Inspect production logs for request id `61456fbc` around `2026-05-28T16:10:49Z`; capture stack trace without secrets. | SUCCESS | legitimate_safety_handling | 1 | Agent 1 found timestamp/route/status match: `2026-05-28 16:10:50` unhandled exception on `/api/v1/dewey/run-directory-analysis-triggers`; `KeyError: 'Parent instance not found: URDT-0C6B582935602401'` from `resource_store.py:create_external_object_child`; Dewey calls immediately before returned `200 OK`; route returned `500`. |  | Production stack trace confirms Ursa parent lookup bug. |
| PROD-003 | Agent 1 | Record explicit run-directory policy/config values required by Ursa, redacting credentials only. | SUCCESS | config_or_startup_contract | 1 | Runtime config path `/home/ubuntu/.config/ursa-lsmcok1/ursa-config-lsmcok1.yaml`; production runtime packages include `daylily-ursa=4.0.13`, `daylily-ephemeral-cluster=5.0.20`, `daylily-tapdb=7.0.9`, `daylily-auth-cognito=2.1.5`; prior missing-policy 503 was not present. |  | Runtime policy/config availability is sufficient; production package pin is stale relative to this fix. |
| SANITY-001 | Agent 2 | Review OWY handoff claims against Ursa code/tests and mark each recommendation `VALID`, `PARTIAL`, or `REJECTED`. | SUCCESS | contract_test | 2 | Agent 2 concluded Ursa-only is likely; Bloom/Dewey/OWY changes rejected absent different request log evidence. |  | Recommendations recorded in chat and implemented locally. |
| SANITY-002 | Agent 2 | Confirm whether fix belongs in Ursa only; reject Bloom/Dewey/OWY changes unless logs prove a contract mismatch. | SUCCESS | contract_test | 2 | Agent 2 identified most likely root cause as Ursa local external-object parent lookup by TapDB EUID instead of stored `trigger_euid`. |  | Fix stayed Ursa-only. |
| REPRO-001 | Agent 3 | Add local test fixture for exact OWY payload, Bloom EUID `M-BRM-4Z`, Dewey EUID `M-DGX-9SD7`, and command `illumina_run_qc_bclconvert`. | SUCCESS | contract_test | 3 | `tests/test_dewey_run_analysis_triggers.py::test_run_directory_trigger_accepts_exact_owy_handoff_with_bloom_euid`. |  | Exact OWY handoff context is covered locally. |
| REPRO-002 | Agent 3 | Reproduce the production exception class locally, or record why logs make direct reproduction unnecessary. | SUCCESS | contract_test | 3 | Added explicit parent lookup assertion and missing-parent 503 test; code inspection shows production `4.0.13` could pass logical `trigger_euid` to a TapDB instance-EUID lookup when `bloom_run_euid` is present. |  | Root cause is source-grounded; direct prod stack trace remains blocked by SSM plugin. |
| DYEC-003 | Agent 3 | Update all Ursa version surfaces to exact DYEC `5.0.22`. | SUCCESS | config_or_startup_contract | 4 | Updated `pyproject.toml`, `uv.lock`, runtime guard, README, ecosystem metadata, docs/docstrings, tests, `environment.yaml`, `ursa-conformance-directive.md`, and `cluex.yaml`; stale-version grep over active surfaces returned no matches. |  | Ursa now requires exact `daylily-ephemeral-cluster==5.0.22`. |
| DYEC-004 | Agent 3 | Add/update tests proving Ursa reports and enforces DYEC `5.0.22`. | SUCCESS | contract_test | 4 | `tests/test_cluster_partition_helpers.py` now rejects newer `5.1.0`; activation/diagnostic tests updated to `5.0.22`; runtime proof `require_daylily_ec_version -> 5.0.22`. |  | Exact-version enforcement covered. |
| FIX-001 | Agent 3 | Patch Ursa route/config handling based on proven root cause; no inferred defaults, no fallback behavior. | SUCCESS | feature_implementation | 4 | `ResourceStore.create_external_object_child` accepts explicit `parent_external_id_key`; run-directory route passes `parent_external_id_key="trigger_euid"` for Bloom child records. |  | Fix is explicit and Ursa-scoped. |
| FIX-002 | Agent 3 | Ensure expected domain/config failures return explicit 4xx/409/503 responses instead of generic 500. | SUCCESS | feature_implementation | 4 | Bad request S3 URI returns 400; Dewey malformed storage URI maps to 502; local persistence parent failure maps to explicit 503. |  | Expected failures no longer collapse to generic 500 in covered paths. |
| TEST-001 | Agent 3 | Run focused Ursa tests for run-directory triggers, idempotency, Bloom-null path, OWY BCLConvert command, error handling, and DYEC pin. | SUCCESS | contract_test | 4 | `python -m pytest -q tests/test_dewey_run_analysis_triggers.py tests/test_daylily_ec_runner.py tests/test_activation_metadata.py tests/test_cluster_headnode_diagnostics.py tests/test_admin_gui_and_cluster_routes.py` -> 59 passed; `tests/test_dayec_run_directory_command_catalog.py tests/test_cluster_partition_helpers.py` -> 20 passed; `ruff check daylib_ursa tests`, `git diff --check`, `uv lock --check`, and `pip check` passed. |  | Focused local validation passed. |
| RELEASE-001 | Agent 4 | Fetch tags and compute next Ursa patch tag. | SUCCESS | plan_amendment | 5 | Initial audit found `4.0.13`; pre-commit audit found remote annotated tag `4.0.14` on commit `ad981db62159804962caa60bdcba6706b58eee64` (`codex/inf6-deploy-formalization-20260528`). |  | Release target amended to `4.0.15`; do not reuse `4.0.14`. |
| RELEASE-002 | Agent 4 | Prepare commit, annotated tag, and push plan after tests pass. | OPEN | plan_amendment | 5 | Pending. |  |  |
| DYEC-005 | Agent 4 | Include DYEC `5.0.22` proof in Ursa release, image/package provenance, and production deploy verification. | BLOCKED | plan_amendment | 5 | Requires completed source update and release artifact. | Release not built yet. | Unblock after tests and release packaging. |
| DEPLOY-001 | Agent 4 | Block production deploy until approval phrase is received. | BLOCKED | active_product_contract | 6 | Approval phrase not received. | Live production deploy/restart approval missing. | Unblock with `APPROVE URSA PROD OWY FIX DEPLOY us-west-2 ursa.day.lsmc.bio`. |
| DEPLOY-002 | Agent 4 | After approval, deploy only Ursa using the current production runtime path; do not migrate runtime lane. | BLOCKED | active_product_contract | 6 | Approval phrase not received. | Live production deploy/restart approval missing. | Unblock with approval phrase. |
| ACCEPT-001 | Agent 4 | After deploy, verify health/OpenAPI tag and coordinate one OWY retry for the same run. | BLOCKED | active_product_contract | 7 | Deploy blocked. | Fixed Ursa not deployed. | Unblock after approved deploy. |
| ACCEPT-002 | Agent 4 | Confirm no duplicate Bloom/Dewey sidecars, `.ursa.*` sidecar written only after success, and OWY failure stage cleared. | BLOCKED | active_product_contract | 7 | Deploy blocked. | OWY retry not approved/performed. | Unblock after approved deploy and OWY retry. |
| FINAL-001 | Orchestrator | Record status counts, changed files, pushed refs, deploy approval state, acceptance result, and remaining blockers. | OPEN | plan_amendment | 8 | Pending terminal report. |  |  |

## Working Notes

- Status counts after Gate 0: `SUCCESS=4`, `OPEN=15`, `BLOCKED=5`.
- The implementation must not silently reinterpret `DYEC 5.0.22` as a lower version or a loose minimum.
- The implementation must not add fallback config behavior or compatibility shims.
