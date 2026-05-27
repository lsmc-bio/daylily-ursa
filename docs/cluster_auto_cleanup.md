# Cluster Auto Cleanup Runbook

Ursa exposes an admin-only cluster auto-cleanup control for idle Ursa-owned analysis clusters:

- `GET /api/v1/admin/cluster-cleanup-policy`
- `PUT /api/v1/admin/cluster-cleanup-policy`
- `POST /api/v1/admin/cluster-cleanup/run`
- GUI: `/admin/config`

The policy is disabled by default. Enabling it requires:

- `idle_minutes`, default `45`
- `export_source_path` under `/fsx/analysis_results/`
- `export_destination_s3_uri` as an `s3://` URI
- `export_output_dir` for local export receipts

Cleanup execution considers only clusters with:

- `cluster_status=CREATE_COMPLETE`
- zero active or queued scheduler jobs
- idle age greater than or equal to the policy threshold
- available cluster name, region, and job queue status

## Export Before Delete

Execution must export FSx analysis output before delete:

1. Run the DayEC export path through `ClusterService.export_analysis_results(...)`.
2. Require a successful export command result.
3. Create the existing Ursa delete plan.
4. Submit delete with the returned confirmation token and matching cluster name.

If export fails, delete is blocked for that candidate. The run response records the blocked reason and does not call delete for that cluster.

The GUI only exposes dry-run cleanup. Live cleanup execution requires the API request body:

```json
{
  "execute": true,
  "destructive_confirmation": "export-fsx-to-s3-then-delete-idle-clusters"
}
```

Live AWS delete remains a destructive action. Do not call the live execute path without the workspace's separate explicit destructive-action approval.

## Local Configuration

The corresponding settings are:

- `ursa_cluster_auto_cleanup_enabled`
- `ursa_cluster_auto_cleanup_idle_minutes`
- `ursa_cluster_auto_cleanup_export_source_path`
- `ursa_cluster_auto_cleanup_export_destination_s3_uri`
- `ursa_cluster_auto_cleanup_export_output_dir`

Runtime policy changes are stored in process state for the running Ursa app. Deployment config should carry the desired startup default.
