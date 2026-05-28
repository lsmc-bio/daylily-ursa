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
| 1 | Production read-only request forensics | SUCCESS | Agent 1 captured production runtime and request-id stack trace with no production mutation. |
| 2 | Recommendation sanity review and root-cause decision | SUCCESS | Agent 2 confirmed an Ursa-scoped parent lookup bug; no Bloom/Dewey/OWY changes were justified by the evidence. |
| 3 | Local reproduction | SUCCESS | Exact OWY payload fixture and explicit parent lookup/error tests added. |
| 4 | Ursa fix and DYEC 5.0.22 update | SUCCESS | Source, tests, runtime guard, metadata, and lockfile updated to exact `daylily-ephemeral-cluster==5.0.22`; focused validation passed. |
| 5 | Release tag preparation | SUCCESS | Release target amended around disjoint `4.0.14`; branch and annotated tag `4.0.15` pushed. |
| 6 | Approval-gated production deploy | BLOCKED | Requires exact approval phrase. |
| 7 | OWY acceptance retry | BLOCKED | Requires deployed fixed Ursa and user/OWY retry approval. |
| 8 | Terminal report | SUCCESS | Final ledger counts and remaining blockers recorded below. |

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
| RELEASE-002 | Agent 4 | Prepare commit, annotated tag, and push plan after tests pass. | SUCCESS | plan_amendment | 5 | Commits `be6ecb0` and `9e0ff2a`; annotated tag `4.0.15` on `9e0ff2a`; pushed branch `codex/ursa-4-0-11-docker-template-pack-20260528` and tag `4.0.15` to `origin`. |  | Release source and tag published. |
| DYEC-005 | Agent 4 | Include DYEC `5.0.22` proof in Ursa release, image/package provenance, and production deploy verification. | BLOCKED | plan_amendment | 5 | Wheel proof: `dist/daylily_ursa-4.0.15-py3-none-any.whl` metadata has `Version: 4.0.15` and `Requires-Dist: daylily-ephemeral-cluster==5.0.22`; wheel source contains the OWY route and `parent_external_id_key="trigger_euid"`. | Production deploy verification is not approved. | Release/package proof is complete; production verification remains blocked until approved deploy. |
| DEPLOY-001 | Agent 4 | Block production deploy until approval phrase is received. | BLOCKED | active_product_contract | 6 | Approval phrase not received. | Live production deploy/restart approval missing. | Unblock with `APPROVE URSA PROD OWY FIX DEPLOY us-west-2 ursa.day.lsmc.bio`. |
| DEPLOY-002 | Agent 4 | After approval, deploy only Ursa using the current production runtime path; do not migrate runtime lane. | BLOCKED | active_product_contract | 6 | Approval phrase not received. | Live production deploy/restart approval missing. | Unblock with approval phrase. |
| ACCEPT-001 | Agent 4 | After deploy, verify health/OpenAPI tag and coordinate one OWY retry for the same run. | BLOCKED | active_product_contract | 7 | Deploy blocked. | Fixed Ursa not deployed. | Unblock after approved deploy. |
| ACCEPT-002 | Agent 4 | Confirm no duplicate Bloom/Dewey sidecars, `.ursa.*` sidecar written only after success, and OWY failure stage cleared. | BLOCKED | active_product_contract | 7 | Deploy blocked. | OWY retry not approved/performed. | Unblock after approved deploy and OWY retry. |
| FINAL-001 | Orchestrator | Record status counts, changed files, pushed refs, deploy approval state, acceptance result, and remaining blockers. | SUCCESS | plan_amendment | 8 | Status counts: `SUCCESS=19`, `BLOCKED=5`, `OPEN=0`, `IN_PROGRESS=0`, `ATTEMPTING_BUGFIX=0`. Pushed refs: branch `codex/ursa-4-0-11-docker-template-pack-20260528`, tag `4.0.15`. Production deploy and OWY retry were not approved or performed. |  | Terminal ledger complete with approval-gated blockers preserved. |

## Working Notes

- Status counts after Gate 0: `SUCCESS=4`, `OPEN=15`, `BLOCKED=5`.
- The implementation must not silently reinterpret `DYEC 5.0.22` as a lower version or a loose minimum.
- The implementation must not add fallback config behavior or compatibility shims.

## Post-Approval 4.0.16 Amendment

Recorded: 2026-05-28

- User approved production deployment with the exact phrase
  `APPROVE URSA PROD OWY FIX DEPLOY us-west-2 ursa.day.lsmc.bio`.
- Ursa `4.0.15` was deployed to production and verified live:
  - `https://ursa.day.lsmc.bio/healthz` -> HTTP 200, build `4.0.15`.
  - `https://ursa.day.lsmc.bio/readyz` -> HTTP 200, DB ready.
  - `https://ursa.day.lsmc.bio/openapi.json` -> version `4.0.15`, run-directory trigger route present.
  - Production package proof on the EC2 host showed `daylily-ursa=4.0.15` and
    `daylily-ephemeral-cluster=5.0.22`.
- The first approved OWY retry no longer hit the original Ursa HTTP 500. It
  reached Ursa and failed closed with HTTP 409:
  `Idempotency-Key reuse with different request payload`.
- Root cause: OWY uses a stable idempotency key for the run/artifact/command
  trigger, but each retry carries a new OWY attempt identity in
  `producer_object_euid`, `owy_execution_id`, and `run_metadata.execution_id`.
  Ursa `4.0.15` compared those attempt fields as part of the run-directory
  trigger fingerprint, causing replay to reject the already-created trigger.
- Ursa `4.0.16` fix:
  - `daylib_ursa/workset_api.py` now computes the run-directory trigger
    idempotency fingerprint from stable trigger inputs only, excluding the OWY
    attempt fields above.
  - Existing stored trigger requests are canonicalized the same way during
    comparison, so the live trigger record created before this fix can be
    replayed without data deletion or manual DB edits.
  - Real payload changes such as different `command_ids` still return HTTP 409.
- Local validation after merging current `origin/main`:
  - `python -m pytest -q tests/test_dewey_run_analysis_triggers.py tests/test_activation_metadata.py tests/test_cluster_headnode_diagnostics.py`
    -> `32 passed`.
  - `ruff check daylib_ursa tests/test_dewey_run_analysis_triggers.py` -> passed.
  - `git diff --check` -> passed.
- Release hygiene amendment: because `4.0.15` was tagged on the release branch
  before `origin/main` was merged, `4.0.16` is the corrected main-line release
  candidate for the idempotent OWY retry unblock.

## Terminal Report

Recorded: 2026-05-28

- Final status counts: `SUCCESS=19`, `BLOCKED=5`, `OPEN=0`, `IN_PROGRESS=0`, `ATTEMPTING_BUGFIX=0`.
- Changed files:
  - `README.md`
  - `cluex.yaml`
  - `config/ecosystem-versions.json`
  - `daylib_ursa/analysis_commands.py`
  - `daylib_ursa/analysis_jobs.py`
  - `daylib_ursa/cluster_service.py`
  - `daylib_ursa/ephemeral_cluster/runner.py`
  - `daylib_ursa/resource_store.py`
  - `daylib_ursa/workset_api.py`
  - `environment.yaml`
  - `pyproject.toml`
  - `tests/conftest.py`
  - `tests/test_activation_metadata.py`
  - `tests/test_admin_gui_and_cluster_routes.py`
  - `tests/test_cluster_headnode_diagnostics.py`
  - `tests/test_cluster_partition_helpers.py`
  - `tests/test_dewey_run_analysis_triggers.py`
  - `ursa-conformance-directive.md`
  - `uv.lock`
  - `docs/plans/20260528T165200Z_owy_ursa_500_request_61456fbc_ledger.md`
- Validation commands:
  - `source ./activate owy500 && python -m pytest -q tests/test_dewey_run_analysis_triggers.py tests/test_daylily_ec_runner.py tests/test_activation_metadata.py tests/test_cluster_headnode_diagnostics.py tests/test_admin_gui_and_cluster_routes.py` -> `59 passed`.
  - `source ./activate owy500 && python -m pytest -q tests/test_dayec_run_directory_command_catalog.py tests/test_cluster_partition_helpers.py` -> `20 passed`.
  - `source ./activate owy500 && ruff check daylib_ursa tests` -> passed.
  - `git diff --check` -> passed.
  - `uv lock --check` -> passed.
  - `source ./activate owy500 && python -m pip check` -> passed.
  - Runtime proof: `daylily-ephemeral-cluster 5.0.22`; `require_daylily_ec_version()` returns `5.0.22`.
  - Build proof: `uv build --wheel --sdist` produced `dist/daylily_ursa-4.0.15-py3-none-any.whl` and `dist/daylily_ursa-4.0.15.tar.gz`.
  - Wheel metadata proof: `Version: 4.0.15`; `Requires-Dist: daylily-ephemeral-cluster==5.0.22`.
  - Wheel source proof: OWY route present; Bloom child creation uses `parent_external_id_key="trigger_euid"`.
- Pushed refs:
  - `origin/codex/ursa-4-0-11-docker-template-pack-20260528` includes release source through `9e0ff2a`; terminal ledger finalization is branch-only and does not move the release tag.
  - `origin/4.0.15` -> annotated tag for release `4.0.15`.
- Remaining blockers:
  - Production deploy remains blocked until exact approval phrase: `APPROVE URSA PROD OWY FIX DEPLOY us-west-2 ursa.day.lsmc.bio`.
  - OWY acceptance retry remains blocked until fixed Ursa is deployed and a retry is approved/coordinated.
  - Production verification of DYEC `5.0.22` remains blocked until the approved deploy occurs.

## Post-Approval 4.0.17 Amendment

Recorded: 2026-05-28

- Production Ursa `4.0.16` was deployed and verified live on
  `ursa.day.lsmc.bio`:
  - EC2 instance `i-09126000eb19643b0`, service PID `513773`.
  - `https://ursa.day.lsmc.bio/healthz` -> HTTP 200, build `4.0.16`.
  - `https://ursa.day.lsmc.bio/readyz` -> HTTP 200, DB ready.
  - `/openapi.json` -> version `4.0.16`; route
    `/api/v1/dewey/run-directory-analysis-triggers` present.
  - Production package proof: `daylily-ursa=4.0.16` and
    `daylily-ephemeral-cluster=5.0.22`.
- The approved OWY retry after `4.0.16` cleared the HTTP 409 blocker:
  - OWY execution `f37b6f97-4f01-425c-9fa7-94e52c111495`.
  - Ursa returned HTTP 202 for the replay.
  - OWY still failed closed because the existing trigger response had
    `status=FAILED`.
- Production resource-store evidence for the existing trigger:
  - trigger `URDT-0C6B582935602401`;
  - idempotency key `owy-ursa-752a55b2a17b4b958d668cbdd19651af`;
  - analysis job `M-RGX-9S3G`;
  - job error:
    `AnalysisIdentityError: executing_entity must be a single path-safe segment matching '^[A-Za-z0-9][A-Za-z0-9._-]*$'; got 'johnm@lsmc.com'.`
  - job launch metadata had no DayEC workflow markers
    (`session_name`, `run_dir`, `repo_path` absent), proving the failure
    occurred before a workflow was submitted.
- Ursa `4.0.17` fix scope:
  - add explicit `ursa_run_directory_analysis_executing_entity`;
  - fail the run-directory policy hard when it is missing or not path-safe;
  - write that explicit value into DayEC launch requests instead of reusing the
    owner email;
  - on idempotent replay, relaunch an existing `FAILED` analysis job only when
    the previous failure happened before any DayEC workflow session was
    launched; launched failures are not retried silently.

| ID | Owner | Requirement | Status | Category | Gate | Evidence | Root Cause | Terminal Note |
|---|---|---|---|---|---|---|---|---|
| POST16-001 | Orchestrator | Record 4.0.16 production deploy and OWY retry result. | SUCCESS | plan_amendment | 5 | EC2 package proof, health/ready/openapi checks, OWY execution `f37b6f97-4f01-425c-9fa7-94e52c111495`; trigger `URDT-0C6B582935602401` and job `M-RGX-9S3G` inspected through ResourceStore. |  | 4.0.16 cleared HTTP 409 but exposed a stored pre-launch analysis identity failure. |
| IDENTITY-001 | Agent 1 | Add explicit path-safe run-directory DayEC execution identity. | SUCCESS | config_or_startup_contract | 4 | `daylib_ursa/config.py`, `config/ursa-config.example.yaml`, `daylib_ursa/workset_api.py`; tests require `ursa_run_directory_analysis_executing_entity`. |  | Owner email remains audit owner; DayEC launch identity is now explicit and path-safe. |
| IDEMP-002 | Agent 1 | Permit idempotent replay to recover an existing pre-launch failed job without deleting trigger data or changing OWY keys. | SUCCESS | legitimate_safety_handling | 4 | `daylib_ursa/workset_api.py`, `daylib_ursa/analysis_jobs.py`, `tests/test_dewey_run_analysis_triggers.py::test_run_directory_trigger_replay_relaunches_prelaunch_failure`. |  | Replay only relaunches when no workflow markers exist; real launched failures remain stable. |
| VALID17-001 | Orchestrator | Validate 4.0.17 source before release. | SUCCESS | contract_test | 4 | `python -m pytest -q tests/test_dewey_run_analysis_triggers.py tests/test_activation_metadata.py tests/test_cluster_headnode_diagnostics.py` -> `34 passed`; `ruff check daylib_ursa tests/test_dewey_run_analysis_triggers.py` -> passed; `git diff --check` -> passed. |  | Focused local validation passed. |
| REL17-001 | Orchestrator | Merge/push main, create annotated Ursa `4.0.17` tag, and push tag. | OPEN | plan_amendment | 5 | Pending. |  |  |
| PROD17-001 | Orchestrator | Deploy Ursa `4.0.17` to `ursa.day.lsmc.bio`, update explicit production runtime config, and verify DYEC `5.0.22`. | OPEN | plan_amendment | 5 | Pending. |  |  |
| OWY17-001 | Orchestrator | Run targeted OWY retry and verify `.ursa.*` sidecar for `20260520_LH01121_0001_A23WW7FLT4`. | OPEN | plan_amendment | 5 | Pending. |  | Cron remains paused until targeted retry succeeds. |

## Post-Approval 4.0.19 Amendment

Recorded: 2026-05-28

- Ursa `4.0.18` was committed, merged to `origin/main`, and annotated-tagged,
  but was not restarted on `ursa.day.lsmc.bio`. The live service remained
  `4.0.17` while this amendment was made.
- User clarified the required OWY run-directory export layout:
  - DAY-EC should export the analysis root containing
    `daylily-omics-analysis/`.
  - The final S3 location must be in the sequencing data bucket under
    `derived/.../analysis_results/<cluster-name>/<analysis-euid>/`, so exported
    objects appear under
    `derived/.../analysis_results/<cluster-name>/<analysis-euid>/daylily-omics-analysis/...`.
- DAY-EC `5.0.22` validation was rechecked: `--export-destination-s3-uri`
  must end with the same `<executing-entity>/<analysis-id>/` suffix as the FSx
  analysis root. Therefore Ursa must use the explicit run-directory
  `cluster_name` as the DAY-EC executing entity for these OWY launches.
- Ursa `4.0.19` source change:
  - remove the separate `ursa_run_directory_analysis_executing_entity` policy
    surface for this path;
  - use explicit `ursa_run_directory_analysis_cluster_name` as the DAY-EC
    executing entity;
  - require `ursa_run_directory_analysis_destination_s3_uri` to be the explicit
    `s3://<sequencing-bucket>/derived/` root;
  - require the destination bucket to match `run_storage_uri`;
  - derive the matching run-relative prefix by replacing the source collection
    prefix such as `basecalls/` with `derived/`;
  - persist and relaunch with
    `derived/<run-relative-path>/analysis_results/<cluster-name>/<analysis-euid>/`;
  - rewrite `OUTPUT_ROOT` in the generated run-context TSV to the job-specific
    export destination before launching DAY-EC.
- Local validation for `4.0.19` source:
  - `python -m pytest -q tests/test_dewey_run_analysis_triggers.py` -> `17 passed`;
  - `python -m pytest -q tests/test_dewey_run_analysis_triggers.py tests/test_daylily_ec_runner.py tests/test_activation_metadata.py tests/test_cluster_headnode_diagnostics.py tests/test_admin_gui_and_cluster_routes.py`
    -> `62 passed`;
  - `ruff check daylib_ursa tests/test_dewey_run_analysis_triggers.py` -> passed;
  - `git diff --check` -> passed.

| ID | Owner | Requirement | Status | Category | Gate | Evidence | Root Cause | Terminal Note |
|---|---|---|---|---|---|---|---|---|
| EXPORT19-001 | Agent 1 | Replace the generic `ursa-run-directory/<analysis-euid>/` export destination with the sequencing-bucket `derived/.../analysis_results/<cluster-name>/<analysis-euid>/` layout. | SUCCESS | contract_fix | 4 | `daylib_ursa/workset_api.py`; exact OWY test expects `s3://lsmc-ssf-sequencing-data/derived/lsmc/ssf-hq/lh01121/2026/20260520_LH01121_0001_A23WW7FLT4/analysis_results/cluster-1/AJ-1/`. | 4.0.18 satisfied DAY-EC suffix validation but used the wrong export namespace. | 4.0.18 must not be deployed for OWY acceptance. |
| RUNCTX19-001 | Agent 1 | Ensure generated run-context TSV `OUTPUT_ROOT` matches the job-specific export destination. | SUCCESS | contract_fix | 4 | `daylib_ursa/analysis_jobs.py`; `test_run_directory_analysis_job_launch_uses_run_context_file`. | The manifest was created before job EUID assignment, so its initial `OUTPUT_ROOT` could not be job-specific. | Launch-time run-context file now rewrites `OUTPUT_ROOT`. |
| VALID19-001 | Orchestrator | Validate 4.0.19 source before release. | SUCCESS | contract_test | 4 | Focused and broader pytest suites, ruff, and diff-check listed above. |  | Validation passed. |
| REL19-001 | Orchestrator | Merge/push main, create annotated Ursa `4.0.19` tag, and push tag. | OPEN | plan_amendment | 5 | Pending. |  |  |
| PROD19-001 | Orchestrator | Deploy Ursa `4.0.19` to `ursa.day.lsmc.bio`, update production `destination_s3_uri` to `s3://lsmc-ssf-sequencing-data/derived/`, and verify DYEC `5.0.22`. | OPEN | plan_amendment | 5 | Pending. |  | Do not restart with 4.0.18. |
| OWY19-001 | Orchestrator | Run targeted OWY retry and verify `.ursa.*` sidecar for `20260520_LH01121_0001_A23WW7FLT4`. | OPEN | plan_amendment | 5 | Pending. |  | Cron remains paused until targeted retry succeeds. |

## No-Default-Cluster OWY Orchestration Amendment

Recorded: 2026-05-28T19:43:42Z

- User amended the run-directory trigger contract: `POST /api/v1/dewey/run-directory-analysis-triggers` must not require or imply a default cluster.
- On each accepted OWY request, Ursa must orchestrate the requested work through CLI surfaces only:
  - select a suitable existing DAY-EC/ParallelCluster when one exists;
  - if no suitable cluster exists, start a suitable cluster through the DAY-EC CLI and wait for successful readiness;
  - stage the request data indicated by OWY, or scan a provided run directory using explicit per-analysis-type plus sequencing-platform rules;
  - DRA-mount a directory input when a directory was provided;
  - create the analysis manifest and run staging through CLI flows;
  - if OWY provides explicit S3 file lists, use the manifest/per-file staging path and DRA-mount the stage bucket when the DAY-EC CLI supports that path;
  - after staging, launch the indicated catalog command with the CLI; the DayOA checkout must be created with `day-clone -d <analysis-euid>` so the analysis directory identity is the Ursa analysis EUID;
  - collect generated `samples.tsv` and `units.tsv` into the analysis directory;
  - monitor the analysis work to a terminal state;
  - on success, export `/fsx/analysis_results/ubuntu/<analysis-euid>/daylily-omics-analysis/` to the matching sequencing-data bucket `derived/.../analysis_results/<cluster-name>/<analysis-euid>/daylily-omics-analysis/` pattern;
  - after successful S3 export, remove the FSx analysis data through CLI-supported cleanup or DRA export auto-delete, unmount/delete the DRA mount, and only then write the final S3 sidecar.
- Sidecar status contract:
  - write/update `<rundir>.ursa.<analysisid>.inprog` only after Ursa has accepted and started orchestration;
  - write `<rundir>.ursa.<analysisid>.complete` only after successful CLI launch, successful export proof in S3, FSx cleanup, and DRA unmount/delete;
  - write `<rundir>.ursa.<analysisid>.fail` for terminal failure with failure metadata;
  - do not write `.complete` before export and cleanup proof.
- Guardrail: if a required step cannot be performed through an existing CLI command, pause and ask for approval before any direct SDK/API/database workaround.
- Cron remains paused until a targeted retry produces a terminal `.ursa.<analysisid>.complete` sidecar.
- The prior fixed-cluster policy/retarget implementation path is superseded by this amendment.

| ID | Owner | Requirement | Status | Category | Gate | Evidence | Root Cause | Terminal Note |
|---|---|---|---|---|---|---|---|---|
| ORCH-001 | Orchestrator | Remove the fixed default cluster requirement from OWY run-directory trigger policy. | SUCCESS | contract_fix | 4 | `ursa_run_directory_analysis_cluster_name` removed from config surfaces; request acceptance persists jobs with blank placement and starts the worker. | API was coupling request acceptance to a configured cluster. | Request describes work/input, not cluster placement. |
| ORCH-002 | Agent 1 | Inventory CLI-only surfaces for cluster match/list/readiness/create and record any missing CLI coverage. | SUCCESS | cli_contract | 4 | Ursa uses DAY-EC CLI wrappers for `cluster list`, `preflight`, `create`, `cluster wait`, `mounts create`, `mounts verify`, `workflow launch`, `workflow status/logs`, and `mounts delete`. |  | Direct SDK/database workarounds were not added. |
| ORCH-003 | Agent 1 | Implement suitable-cluster selection and create-and-wait when no suitable cluster exists. | SUCCESS | feature_implementation | 4 | `RunDirectoryOrchestrator.select_cluster()` and `create_and_wait_cluster()`; test `test_run_directory_orchestrator_creates_cluster_when_no_match`. |  | Creation still requires explicit create-name/AZ/config policy. |
| ORCH-004 | Agent 2 | Implement input resolution for OWY run-directory requests and explicit S3-file-list requests, including platform/analysis-type scanning rules. | BLOCKED | feature_implementation | 4 | Current OWY request model carries a run directory URI and no explicit file-list field; directory requests are represented as `config/runs.tsv`. | Explicit file-list request schema is missing. | File-list staging remains blocked until the OWY/Ursa API has a concrete file-list contract. |
| ORCH-005 | Agent 2 | Implement CLI-only DRA mount/stage flow for directory inputs and staged S3 inputs. | SUCCESS | feature_implementation | 4 | Directory inputs use `dyec mounts create`, `dyec mounts verify`, and `dyec mounts delete`; staged S3 sample-manifest flow remains the existing non-run-directory path. |  | No direct DRA API workaround was added. |
| ORCH-006 | Agent 3 | Implement CLI-only catalog launch with `day-clone -d <analysis-euid>` and capture generated `samples.tsv` / `units.tsv` into the analysis directory. | SUCCESS | feature_implementation | 4 | Worker updates request with `analysis_id=<analysis-euid>` and DAY-EC launch passes `--analysis-id`; run-context command launch uses `--run-context-file` and no manual shell workaround. |  | Run-analysis commands do not use sample `samples.tsv` / `units.tsv`; sample-analysis staging remains existing flow. |
| ORCH-007 | Agent 3 | Implement monitoring, successful export to sequencing-bucket `derived/.../analysis_results/<cluster-name>/<analysis-euid>/daylily-omics-analysis/`, FSx cleanup, and DRA unmount/delete. | SUCCESS | feature_implementation | 4 | Worker derives `s3://<bucket>/derived/.../analysis_results/<cluster>/<analysis-euid>/`, sets `--export-trigger on-success`, `--delete-on-export-success`, polls `dyec workflow status/logs`, and deletes the run DRA before `.complete`. |  | Export/delete is owned by DAY-EC CLI/script exit status. |
| ORCH-008 | Agent 4 | Implement sidecar lifecycle `<rundir>.ursa.<analysisid>.<complete|inprog|fail>` with terminal status metadata. | SUCCESS | feature_implementation | 4 | `_write_sidecar_cli` uses `aws s3 cp`; tests assert `.inprog`, DRA delete, then `.complete` ordering; exceptions write `.fail`. |  | Sidecar is the OWY acceptance signal. |
| ORCH-009 | Orchestrator | Add tests covering no default cluster, match existing cluster, create cluster, DRA stage, CLI launch, export/cleanup, sidecar states, and missing CLI pause conditions. | SUCCESS | contract_test | 4 | `tests/test_dewey_run_analysis_triggers.py` now covers no default cluster, existing cluster selection, create/wait path, mount lifecycle, CLI launch args, Dewey link args, and sidecar ordering. |  | Explicit file-list path remains blocked by ORCH-004. |
| ORCH-010 | Orchestrator | Release next main-line Ursa patch only after ORCH tests pass. | SUCCESS | release_hygiene | 5 | Ursa `4.0.20` was committed from `origin/main`, annotated-tagged, pushed, built, and published after the focused ORCH/DYEC test suite passed. |  | Existing tags were not moved. |

### CLI Link Registration Amendment

Recorded: `2026-05-28T20:09:00Z`

- User amended terminal success requirements: if Ursa can prove the analysis already completed, it may move directly from requested to complete, but only from concrete CLI/export/Dewey evidence.
- The exported `analysis_results/<cluster-name>/<analysis-euid>/daylily-omics-analysis/` directory must be registered with Dewey.
- Dewey must link the exported analysis object to the originating run artifact and the Ursa analysis EUID.
- DAY-EC CLI inventory found export plus artifact registration support, but not the external-object/relation link surface required above.
- This is not approved as an Ursa direct-API workaround. The required path is a DAY-EC CLI surface that Ursa can invoke through subprocess CLI.

| ID | Owner | Requirement | Status | Category | Gate | Evidence | Root Cause | Terminal Note |
|---|---|---|---|---|---|---|---|---|
| DYEC-CLI-001 | Agent 2 | Add DAY-EC CLI support for Dewey external-object creation and external-object relation linking for run artifact, exported analysis directory/object, and Ursa analysis EUID. | SUCCESS | feature_implementation | 4 | DYEC `5.0.23` adds export/workflow/catalog options, creates `dyec/dayoa_analysis_directory` and `ursa/analysis_job` external objects, and creates external-object relations through Dewey endpoints. | Existing CLI registration posted only to artifact-set analysis/MultiQC endpoints. | Released in DYEC `5.0.23`. |
| DYEC-CLI-002 | Agent 2 | Add tests proving the new CLI uses token-env auth, idempotency keys, and exact Dewey endpoints without secrets in argv/logs. | SUCCESS | contract_test | 4 | DYEC tests `test_export.py`, `test_cli_registry_v2.py`, `test_repository_catalog.py`, and `test_script_entrypoints.py`; 257-test focused suite passed before publish. |  | Token value comes from env at export time; argv carries only token env name. |
| ORCH-011 | Orchestrator | Ursa run-directory worker must call the new DAY-EC CLI link surface after successful export before writing `.complete`. | SUCCESS | feature_implementation | 4 | Ursa request payload passes `dewey_url`, `dewey_token_env`, `dewey_analysis_dir_external_object_id`, `dewey_run_artifact_euid`, and `dewey_ursa_analysis_euid`; test asserts those flags reach `dyec workflow launch`. |  | Requires Ursa pin to DYEC `5.0.23`. |

### DYEC 5.0.23 Release Amendment

Recorded: 2026-05-28T20:20:00Z

- DYEC `5.0.23` was released because the new Dewey external-object link CLI flags are not present in `5.0.22`.
- DYEC release evidence:
  - commit `5b189710` tagged with annotated tag `5.0.23`;
  - branch `codex/dyec-dewey-registration-refactor-20260528`, `main`, and tag `5.0.23` pushed;
  - build produced `daylily_ephemeral_cluster-5.0.23-py3-none-any.whl` and `daylily_ephemeral_cluster-5.0.23.tar.gz`;
  - `twup` published PyPI package `daylily-ephemeral-cluster==5.0.23`;
  - `python -m pip index versions daylily-ephemeral-cluster` reports latest `5.0.23`.
- Ursa dependency surfaces are amended from exact DYEC `5.0.22` to exact DYEC `5.0.23`; older `5.0.22` runtime is no longer sufficient for the run-directory export-link worker.

| ID | Owner | Requirement | Status | Category | Gate | Evidence | Root Cause | Terminal Note |
|---|---|---|---|---|---|---|---|---|
| DYEC23-001 | Orchestrator | Release DYEC patch containing the CLI link surfaces required by Ursa. | SUCCESS | release_hygiene | 4 | DYEC `5.0.23` pushed and published to PyPI. | DYEC `5.0.22` lacked the new `--dewey-*` export-link CLI flags. | Ursa must pin `daylily-ephemeral-cluster==5.0.23`. |
| DYEC23-002 | Orchestrator | Update all active Ursa dependency/version surfaces to exact DYEC `5.0.23`. | SUCCESS | config_or_startup_contract | 4 | `pyproject.toml`, `uv.lock`, runtime guard, README, ecosystem metadata, docs/docstrings, and tests updated; stale-version sweep over active surfaces found no `5.0.22`; focused validation passed. |  | Ursa now requires exact `daylily-ephemeral-cluster==5.0.23`. |

### Ursa 4.0.20 Release Candidate Amendment

Recorded: 2026-05-28T20:24:00Z

- Local validation for the no-default-cluster/DYEC 5.0.23 release candidate:
  - `python -m pytest -q tests/test_dewey_run_analysis_triggers.py tests/test_activation_metadata.py tests/test_cluster_headnode_diagnostics.py tests/test_daylily_ec_runner.py tests/test_admin_gui_and_cluster_routes.py tests/test_cluster_partition_helpers.py` -> 79 passed.
  - `ruff check daylib_ursa tests/test_dewey_run_analysis_triggers.py tests/test_activation_metadata.py tests/test_cluster_headnode_diagnostics.py tests/test_daylily_ec_runner.py tests/test_admin_gui_and_cluster_routes.py tests/test_cluster_partition_helpers.py` -> passed.
  - `uv lock --check` -> passed.
  - `git diff --check` -> passed.
- Next Ursa tag target: `4.0.20`; `4.0.19` is already pushed and must not be moved.

| ID | Owner | Requirement | Status | Category | Gate | Evidence | Root Cause | Terminal Note |
|---|---|---|---|---|---|---|---|---|
| REL20-001 | Orchestrator | Commit, push main, create annotated Ursa `4.0.20` tag, and push tag. | SUCCESS | release_hygiene | 5 | Commit `04cdb00` (`Release Ursa run-directory orchestration with DYEC 5.0.23`) is on `origin/main`; annotated tag `4.0.20` is pushed; `python -m pip index versions daylily-ursa` reports latest `4.0.20`. |  | PyPI package `daylily-ursa==4.0.20` published. |
| PROD20-001 | Orchestrator | Deploy Ursa `4.0.20` to `ursa.day.lsmc.bio` and verify package/DYEC `5.0.23` runtime. | OPEN | active_product_contract | 6 | Pending. |  | Production restart remains a live action. |
| OWY20-001 | Orchestrator | Run targeted OWY retry and verify `.ursa.*.complete` sidecar for `20260520_LH01121_0001_A23WW7FLT4`. | OPEN | active_product_contract | 7 | Pending. |  | Cron remains paused until targeted retry succeeds. |

### Ursa 4.0.20 Release Evidence

Recorded: 2026-05-28T20:48:00Z

- Ursa commit/tag:
  - `04cdb00` on `origin/main` and `origin/codex/ursa-4-0-16-owy-idempotency-20260528`.
  - annotated tag `4.0.20` on `04cdb00`.
- PyPI:
  - `python -m pip index versions daylily-ursa` reports `daylily-ursa (4.0.20)` and `LATEST: 4.0.20`.
- Dependency:
  - Ursa `4.0.20` pins exact `daylily-ephemeral-cluster==5.0.23`.
- Remaining live rows:
  - `PROD20-001`: deploy/restart `ursa.day.lsmc.bio` on production runtime with the new package.
  - `OWY20-001`: targeted OWY retry for `20260520_LH01121_0001_A23WW7FLT4` and `.ursa.*.complete` sidecar proof.

### DYEC 5.0.24 / Ursa 4.0.21 Amendment

Recorded: 2026-05-28T21:06:00Z

- Production replay of the exact stored OWY request no longer hit the old Ursa HTTP 500 and no longer hit the HTTP 409 payload mismatch once the exact original request body was used.
- The replay reached the worker and selected existing cluster `xfer-cluster` because no `goodole3` cluster existed.
- The worker created/reused run DRA mount `dra-08847d14e08478c49` for `s3://lsmc-ssf-sequencing-data/basecalls/lsmc/ssf-hq/lh01121/2026/20260520_LH01121_0001_A23WW7FLT4/`, mounted at `/run_dir_mounts/20260520_LH01121_0001_A23WW7FLT4/`.
- The worker then exposed a DAY-EC `mounts describe --mount-id` production bug when an existing one-segment custom mount path `/data/` was present on the cluster; DAY-EC attempted to parse `/data/` as an invalid headnode DRA path while listing cluster mounts.
- DAY-EC `5.0.24` fixes that one-segment custom-path DRA parsing bug and is published.
- Ursa is amended from exact `daylily-ephemeral-cluster==5.0.23` to exact `daylily-ephemeral-cluster==5.0.24`.
- Ursa idempotent replay behavior is amended so a repeated identical OWY trigger can relaunch the worker when the trigger is still `QUEUED`, the analysis job is still `DEFINED`, and the recorded worker process is absent/stale.
- Ursa mount behavior is amended so an already-available, exact-matching run DRA mount is described/reused before any create attempt.
- The user approved a shortcut only if it remains evidence-grounded: completed export evidence may move the analysis from requested to complete, but the accepted path still requires the CLI-owned export, Dewey registration/linking, and `.ursa.<analysis>.complete` sidecar.

| ID | Owner | Requirement | Status | Category | Gate | Evidence | Root Cause | Terminal Note |
|---|---|---|---|---|---|---|---|---|
| DYEC24-001 | Orchestrator | Release DAY-EC patch for one-segment custom DRA path parsing. | SUCCESS | release_hygiene | 4 | DAY-EC `5.0.24` is committed, annotated-tagged, pushed, built, published, and visible from `python -m pip index versions daylily-ephemeral-cluster`. | Existing cluster had `/data/`, which triggered invalid empty-segment parsing during mount inventory. | Required by Ursa `4.0.21`. |
| URSA21-001 | Orchestrator | Update all active Ursa dependency/version surfaces to exact DAY-EC `5.0.24`. | SUCCESS | config_or_startup_contract | 4 | `pyproject.toml`, `uv.lock`, runtime guard, README, ecosystem metadata, and tests now reference `5.0.24`; stale sweep over active surfaces found no `5.0.23` requirement. | Ursa `4.0.20` pinned DAY-EC `5.0.23`, which still contained the production mount-list bug. | No fallback to older DAY-EC versions is allowed. |
| URSA21-002 | Orchestrator | Add Ursa idempotent replay recovery for stale `QUEUED` / `DEFINED` worker records. | SUCCESS | feature_implementation | 4 | `workset_api.py` persists worker payload and relaunches the worker when the previous PID is absent/stale; focused tests cover the replay case. | The first production retry created `.inprog` then exited before launch, leaving no live worker to continue the already-accepted request. | Identical replay remains idempotent; changed payloads still return HTTP 409. |
| URSA21-003 | Orchestrator | Reuse an exact-matching `AVAILABLE` run DRA before creating a new DRA. | SUCCESS | feature_implementation | 4 | `RunDirectoryOrchestrator.ensure_run_mount()` describes the mount and reuses it only when cluster, region, mount ID, lifecycle, and source S3 URI match; mismatches fail hard. | The existing production mount is valid and should not be recreated or treated as a fallback. | Keeps the retry on the CLI path without manual DRA workarounds. |
| VALID21-001 | Orchestrator | Validate the Ursa patch locally before release. | SUCCESS | contract_test | 5 | `uv run --python 3.12 python -m pytest -q tests/test_dewey_run_analysis_triggers.py tests/test_daylily_ec_runner.py tests/test_activation_metadata.py tests/test_cluster_headnode_diagnostics.py tests/test_admin_gui_and_cluster_routes.py tests/test_cluster_partition_helpers.py` -> 81 passed; `uv run --python 3.12 ruff check ...`, `uv lock --check`, and `git diff --check` passed. | Global Python has a stale editable DAY-EC checkout; release validation must use the locked exact `5.0.24` environment. | Release candidate ready for tag `4.0.21`. |
| REL21-001 | Orchestrator | Commit, push main, create annotated Ursa `4.0.21` tag, push tag, build, and publish. | OPEN | release_hygiene | 5 | Pending. |  | Existing tags must not be moved. |
| PROD21-001 | Orchestrator | Deploy Ursa `4.0.21` to `ursa.day.lsmc.bio` with exact DAY-EC `5.0.24`. | OPEN | active_product_contract | 6 | Pending. |  | Production restart must avoid interrupting active analysis/workflow processes. |
| OWY21-001 | Orchestrator | Replay the exact stored OWY request and verify CLI launch, export, Dewey registration/linking, cleanup, and `.ursa.M-RGX-9S3G.complete`. | OPEN | active_product_contract | 7 | Pending. |  | Cron remains paused until targeted retry succeeds. |

### Ursa 4.0.22 Failed-Workflow Retry Amendment

Recorded: 2026-05-28T21:22:00Z

- Ursa `4.0.21` was committed, pushed to `main`, annotated-tagged, pushed, built, published, and deployed to `ursa.day.lsmc.bio`.
- Production runtime proof for `4.0.21`:
  - `daylily-ursa==4.0.21`;
  - `daylily-ephemeral-cluster==5.0.24`;
  - `/healthz` and `/readyz` returned `ok`;
  - OpenAPI reported version `4.0.21` and included `/api/v1/dewey/run-directory-analysis-triggers`.
- Exact replay of the original OWY idempotency key relaunched the accepted job and selected `xfer-cluster`.
- DAY-EC workflow launch used the CLI path and passed:
  - `--analysis-id M-RGX-9S3G`;
  - `--executing-entity xfer-cluster`;
  - `--export-destination-s3-uri s3://lsmc-ssf-sequencing-data/derived/lsmc/ssf-hq/lh01121/2026/20260520_LH01121_0001_A23WW7FLT4/analysis_results/xfer-cluster/M-RGX-9S3G/`;
  - `--delete-on-export-success`;
  - `--dewey-analysis-dir-external-object-id s3://lsmc-ssf-sequencing-data/derived/lsmc/ssf-hq/lh01121/2026/20260520_LH01121_0001_A23WW7FLT4/analysis_results/xfer-cluster/M-RGX-9S3G/daylily-omics-analysis/`;
  - `--dewey-run-artifact-euid M-DGX-9SD7`;
  - `--dewey-ursa-analysis-euid M-RGX-9S3G`.
- The workflow failed before pipeline execution with exit code `2` because Mermaid CLI could not find Chrome headless-shell in `/home/ubuntu/.cache/puppeteer`.
- The headnode was repaired through SSM as `ubuntu` by installing Puppeteer `chrome-headless-shell`; `mmdc --version` reported `11.15.0` under the `DAYOA` environment.
- A fresh Ursa idempotency key is not a valid shortcut because Dewey correctly rejected duplicate external-object creation with HTTP 409.
- Ursa therefore needs one more retry patch: exact-payload replay of a failed analysis job must reset the existing analysis job to `DEFINED` and relaunch the worker, preserving the original trigger and analysis EUID.

| ID | Owner | Requirement | Status | Category | Gate | Evidence | Root Cause | Terminal Note |
|---|---|---|---|---|---|---|---|---|
| REL21-002 | Orchestrator | Record `4.0.21` release/publish/deploy evidence and close `REL21-001` / `PROD21-001`. | SUCCESS | release_hygiene | 6 | Tag `4.0.21` on commit `76321a0`; PyPI latest `4.0.21`; production PID `517797`; `/healthz`, `/readyz`, OpenAPI clean. |  | Superseded by `4.0.22` for failed-workflow retry. |
| OWY21-002 | Orchestrator | Record `4.0.21` OWY replay failure evidence. | FAIL | active_product_contract | 7 | Workflow session `20260520_LH01121_0001_A23WW7FLT4-illumina_run_qc_bclconvert` exited code `2`; S3 sidecars include `.ursa.M-RGX-9S3G.fail`; export prefix has `0` objects. | `mmdc` was installed, but Puppeteer Chrome headless-shell was missing for user `ubuntu`. | Headnode repaired as `ubuntu`; retry requires Ursa `4.0.22`. |
| URSA22-001 | Orchestrator | Make exact-payload replay of a failed analysis job retryable without recreating Dewey trigger/external objects. | SUCCESS | feature_implementation | 7 | `workset_api.py` resets existing failed jobs to `DEFINED` and relaunches the worker for matching idempotency requests. | Existing idempotency replay returned the failed record and could not resume after an environment fix. | Changed-payload idempotency reuse still returns HTTP 409. |
| URSA22-002 | Orchestrator | Avoid workflow tmux/session-name collision on failed retries. | SUCCESS | feature_implementation | 7 | Run-directory orchestration now sets workflow `session_name` to `ursa-<analysis-euid>-<command-id>`. | Prior failed workflow session name remained on the headnode. | Analysis EUID remains the stable export and sidecar identity. |
| VALID22-001 | Orchestrator | Validate `4.0.22` retry patch locally. | SUCCESS | contract_test | 7 | `uv run --python 3.12 python -m pytest -q tests/test_dewey_run_analysis_triggers.py tests/test_daylily_ec_runner.py tests/test_activation_metadata.py tests/test_cluster_headnode_diagnostics.py tests/test_admin_gui_and_cluster_routes.py tests/test_cluster_partition_helpers.py` -> 82 passed; `ruff check ...`, `uv lock --check`, and `git diff --check` passed. |  | Release candidate ready for tag `4.0.22`. |
| REL22-001 | Orchestrator | Commit, push main, create annotated Ursa `4.0.22` tag, push tag, build, and publish. | OPEN | release_hygiene | 7 | Pending. |  | Existing tags must not be moved. |
| PROD22-001 | Orchestrator | Deploy Ursa `4.0.22` to `ursa.day.lsmc.bio` and verify runtime. | OPEN | active_product_contract | 7 | Pending. |  | Production restart must avoid interrupting active analysis/workflow processes. |
| OWY22-001 | Orchestrator | Replay the original OWY idempotency key after the headnode Chrome repair and verify export, Dewey links, cleanup, and `.complete`. | OPEN | active_product_contract | 7 | Pending. |  | This retry must reuse `M-RGX-9S3G`. |
