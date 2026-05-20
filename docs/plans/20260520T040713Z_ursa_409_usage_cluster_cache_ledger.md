# Ursa 4.0.9 Cluster Cache, Jobs, and Usage Reports Ledger

Created: 2026-05-20T04:07:13Z

## Gate 0: Inventory Freeze

Controlling plan: user-provided plan in the current Codex thread for Ursa 4.0.9 cluster cache, jobs, and usage reports.

Ledger path: `docs/plans/20260520T040713Z_ursa_409_usage_cluster_cache_ledger.md`

Primary repo: `/Users/jmajor/projects/mega_dayhoff/repos_work/daylily-ursa`

Reference DayEC checkout: `/Users/jmajor/.codex/worktrees/dyec-fsx-dra-mounts/daylily-ephemeral-cluster`

Dayhoff deployment repo inspected for service pin context: `/Users/jmajor/projects/mega_dayhoff/dayhoff`

Baseline evidence:

- `git status --short --branch` in Ursa: `## main...origin/main`
- Ursa `HEAD`: `a241dee28cc7253be7318f3c4ede22601b1e65fb`
- Ursa `git describe --tags --always --dirty`: `2.0.11.31`
- Ursa tag `2.0.11.32` fetched and resolves to `a170efbcf0d39169f51ffa770a88b043f17a6987`
- DayEC checkout status: `## codex/analysis-id-export-catalog-validation...origin/codex/analysis-id-export-catalog-validation`, with untracked `tmp/`
- DayEC tag `4.0.9` resolves to `5a16d46a206b235b67e29790b0b926daed98c251`
- Dayhoff `services/pins.toml` currently pins Ursa to `2.0.11.32`
- Dayhoff repo has pre-existing dirty/untracked files outside this Ursa implementation; they will not be reverted.
- Live `lsmcok1` host inspection found Ursa `2.0.11.32-dirty` with a local auth/dry-run patch that made cluster inventory visible to authenticated users while keeping create/delete admin-only; that live policy patch was folded into the release before deployment.

Initial assumptions and live-system limits:

- No destructive AWS operations are part of this work.
- Only Ursa may be restarted without further approval.
- The existing Ursa auth policy must be preserved.
- The default cluster and job cache TTL is 900 seconds.
- Usage reporting uses current-month-to-date AWS Cost Explorer `AmortizedCost`.
- DayEC and ParallelCluster tag reports focus on DayEC/custom and ParallelCluster tags, not AWS-generated CloudFormation tags.

## Tracking Rows

| ID | Area | Requirement | Status | Category | Approval Gate | Owner | Evidence | Root Cause | Terminal Note |
|---|---|---|---|---|---|---|---|---|---|
| URSA-001 | Ledger | Record Gate 0 inventory before implementation. | SUCCESS | plan_amendment | Gate 0 | orchestrator | This ledger records repo status, tag refs, Dayhoff pin context, assumptions, and live-system limits. |  | Gate 0 completed before runtime code edits. |
| URSA-002 | Dependency | Pin Ursa to `daylily-ephemeral-cluster==4.0.9` across metadata, runtime checks, docs, and tests. | SUCCESS | feature_implementation | Gate 1 | orchestrator | Initial `python -m pip install -e .` failed because package index has no `daylily-ephemeral-cluster==4.0.9`; packaging was corrected to `Daylily-Informatics/daylily-ephemeral-cluster.git@4.0.9`; `python -m pip install -e .` succeeded; `daylily-ec --json version` returned `4.0.9`; focused tests passed. |  | Ursa now requires the DayEC 4.0.9 runtime through the published Daylily-Informatics Git tag and metadata/docs/tests match that contract. |
| URSA-003 | Cluster cache | Make cluster list/detail loads use a 900 second cache unless explicit force refresh is requested. | SUCCESS | feature_implementation | Gate 1 | orchestrator | `daylib_ursa/cluster_service.py`, `daylib_ursa/workset_api.py`, `tests/test_cluster_headnode_diagnostics.py`; focused pytest command returned `73 passed, 1 warning`. |  | Cluster region/name/detail paths share a 900 second cache and `refresh=true` bypasses or clears the relevant cache. |
| URSA-004 | Job cache | Add 900 second cached headnode job queue data and expose running job counts. | SUCCESS | feature_implementation | Gate 1 | orchestrator | `daylib_ursa/cluster_service.py`, `daylib_ursa/gui_app.py`, `daylib_ursa/gui/templates/dashboard.html`, `daylib_ursa/gui/templates/clusters.html`; focused pytest command returned `73 passed, 1 warning`. |  | Headnode job queues are cached for 900 seconds; dashboard aggregates running jobs and the cluster page renders detailed job rows. |
| URSA-005 | Usage data | Replace Usage placeholder costs with real AWS Budgets, Cost Explorer, and Resource Groups Tagging API reports. | SUCCESS | feature_implementation | Gate 1 | orchestrator | `daylib_ursa/aws_usage.py`, `daylib_ursa/gui_app.py`, `daylib_ursa/gui/templates/usage.html`, `tests/test_aws_usage_reports.py`; Python service smoke with `AWS_PROFILE=lsmc` returned 65 budgets, 1510 cost rows, and 575 inventory rows for `us-west-2`. |  | Usage reports now come from AWS Budgets, Cost Explorer current-month-to-date AmortizedCost, and Resource Groups Tagging API inventory. |
| URSA-006 | UI | Update dashboard, cluster page, and usage page to render the new cached job and cost data. | SUCCESS | feature_implementation | Gate 3 | orchestrator | `tests/test_admin_gui_and_cluster_routes.py`; focused pytest command returned `76 passed, 1 warning`; usage page fixture asserts DayEC budget, tag/service cost, tagged inventory rendering, and non-admin cluster visibility with admin-only create/delete. |  | Dashboard, cluster inventory, cluster detail, and Usage pages render the requested cached jobs and AWS-derived usage reports while preserving the live auth policy. |
| URSA-007 | Tests | Add focused tests for dependency version, cache behavior, job summaries, usage parsing, and UI rendering. | SUCCESS | contract_test | Gate 5 | orchestrator | `source ./activate unidbtst && URSA_DEPLOYMENT_CODE=unidbtst pytest -q tests/test_cluster_headnode_diagnostics.py tests/test_cluster_job_worker.py tests/test_activation_metadata.py tests/test_aws_usage_reports.py tests/test_admin_gui_and_cluster_routes.py tests/test_cli_db_tapdb.py tests/test_tapdb_backend.py` -> `76 passed, 1 warning`; `python -m ruff check ...` -> all checks passed. |  | Focused tests cover the changed DayEC dependency, cluster cache, force refresh, job cache, dashboard count, cluster job list, AWS usage parsing, usage rendering, and preserved non-admin cluster visibility. |
| URSA-008 | AWS smoke | Verify read-only Budgets, Cost Explorer, and tag inventory access with the configured AWS profile. | SUCCESS | contract_test | Gate 5 | orchestrator | `AWS_PROFILE=lsmc aws budgets describe-budgets --region us-east-1 --account-id <account> ...` found 65 DayEC/global budgets; Cost Explorer grouped `aws-parallelcluster-project` spend by service; Resource Groups Tagging API returned tagged resources; Python usage service smoke returned 65 budgets, 1510 cost rows, and 575 inventory rows. |  | Read-only AWS billing and tag APIs are available through the `lsmc` profile for the requested reports. |
| URSA-009 | Live Ursa restart | Restart only Ursa and validate deployed behavior. | SUCCESS | feature_implementation | Gate 5 | orchestrator | Active host `i-09126000eb19643b0` (`lsmcok1`, `https://ursa.dev.lsmc.life`) was updated to Ursa tag `2.0.11.34`; `ursa --json version` returned `2.0.11.34`; `daylily-ec --json version` returned `4.0.9`; only Ursa was restarted, new PID `252062`; local and public `/readyz` returned HTTP 200 with Ursa `2.0.11.34`; SSM smoke `371e0611-9b40-4f3b-9f42-6bd32789ce00` returned usage/cache/job evidence from `/home/ubuntu/.local/state/dayhoff/lsmcok1/supervisor-logs/ursa-live-smoke-20260520T044412Z.log`. |  | Live deployed Ursa is running the new release with DayEC 4.0.9, 900 second usage/cluster/job cache TTLs, real AWS billing/tag report access, cached cluster inventory, and two running jobs reported from live cluster queues. |

## Final Terminal Report

All 9 ledger rows are terminal and successful.

- Ursa implementation release: tag `2.0.11.34` at commit `a828bd7`.
- Dayhoff deployment pins: tag `4.0.4` pins `services.ursa.tag = "2.0.11.34"`; tag `4.0.5` updates the Dayhoff self pin to `4.0.4`.
- Live deployment: `lsmcok1` on EC2 `i-09126000eb19643b0` is serving `https://ursa.dev.lsmc.life` with Ursa `2.0.11.34` and `daylily-ephemeral-cluster` `4.0.9`.
- Live auth amendment: the pre-existing host-only cluster visibility and dry-run policy patch was folded into the release before deployment, preserving authenticated cluster visibility while keeping create/delete admin-only.
- AWS profile staging: no `lsmc` profile was added to the host because the deployed `daylily-service-lsmc` profile already has read-only Budgets, Cost Explorer, and Resource Groups Tagging API access.
- Verification: focused Ursa tests returned `76 passed, 1 warning`; focused ruff checks passed; Dayhoff manifest tests returned `23 passed`; local AWS smoke returned 65 budgets, 1510 cost rows, and 575 inventory rows; live SSM smoke returned 65 budgets, 1510 cost rows, 575 inventory rows, 2 clusters, and 2 running jobs.
