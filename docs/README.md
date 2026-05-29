# daylily-ursa Docs

Use the root [README](../README.md) as the current repo overview and operational entry point. This index separates current guides from archived background notes.

## Current Guides

- [Ursa-Atlas return contract](ursa_atlas_return_contract.md): canonical result-return contract from Ursa into Atlas.
- [Dewey run analysis trigger contract](dewey_run_analysis_triggers.md): Dewey service-token trigger, auto-launch, idempotency, and Dewey terminal result return behavior.
- [Compute cluster and cluster job lifecycle](compute_cluster_lifecycle.md): durable compute-cluster objects, cluster-job objects, CLI/API/GUI usage, queued cluster-job start, DayOA `dy-r help` smoke execution, and OWY run-directory lifecycle readback.
- [Cluster auto cleanup runbook](cluster_auto_cleanup.md): admin cleanup policy, dry-run/execute API, and export-before-delete rule.
- [Google OAuth default](GOOGLE_OAUTH_DEFAULT.md): default Cognito plus Google Hosted UI setup helper and ownership boundaries.
- [TapDB admin mount status](tapdb_mount_execplan.md): current mounted TapDB admin behavior inside the Ursa FastAPI app.
- [Conformance audit](../ursa-conformance-directive.md): current status of the Atlas/Bloom alignment work.
- [Auth E2E README](../tests/e2e/README.md): Playwright auth browser test prerequisites and scope.

## Archived Background

These files are retained for context. They describe older workset-monitor and cluster-management workflows and should not override the root README or current code:

- [IAM setup guide](IAM_SETUP_GUIDE.md)
- [Multi-region cluster discovery](MULTI_REGION.md)
- [Workset state diagram](WORKSET_STATE_DIAGRAM.md)

For current runtime operations, start from `source ./activate <deploy-name>` and use `ursa ...` first. Use `tapdb ...`, `daycog ...`, or `daylily-ec ...` only where Ursa explicitly delegates that lifecycle.
