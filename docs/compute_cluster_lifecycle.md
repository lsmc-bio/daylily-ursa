# Compute Cluster And Cluster Job Lifecycle

Ursa models compute placement as explicit evidence. A compute cluster is not an
implicit deployment default, and a cluster job is not inferred from a scheduler
row. Both are persisted objects with EUIDs so OWY, Dewey, Bloom, DayEC, and the
Ursa GUI/CLI can all refer to the same lifecycle.

## Objects

`ComputeClusterRecord` has:

- `cluster_euid`
- `cluster_name`
- `cluster_type`: `generic`, `vanilla_slurm`, or `aws_parallelcluster_slurm`
- `region`
- `tenant_id`
- `owner_user_id`
- `state`
- `metadata`

`ClusterJobRecord` has:

- `cluster_job_euid` and `job_euid`
- `job_type`: `generic` or `slurm`
- `cluster_euid`
- optional `analysis_job_euid`
- optional `scheduler_job_id`
- request, cluster payload, status timestamps, return code, error, and events

Analysis jobs may carry `analysis_experiment_euid`. Ursa generates this
deterministically for analysis rows derived from `analysis_samples_manifest` and
for run-directory command rows derived from `config/runs.tsv`.

## API

Compute clusters:

- `GET /api/v1/compute-clusters`
- `POST /api/v1/compute-clusters`
- `GET /api/v1/compute-clusters/{cluster_euid}`
- `POST /api/v1/compute-clusters/{cluster_euid}/state`

Cluster jobs:

- `GET /api/v1/cluster-jobs`
- `POST /api/v1/cluster-jobs`
- `GET /api/v1/cluster-jobs/{cluster_job_euid}`

Existing cluster inspection and create/delete-plan routes remain under
`/api/v1/clusters`. The new top-level object routes are the durable placement
records used to link a cluster and scheduler job back to an Ursa analysis job.

## CLI

The CLI requires explicit URL and credentials. It does not read tokens from
ambient environment variables.

```bash
ursa --json compute-clusters create \
  --api-base-url https://ursa.day.lsmc.bio \
  --token "$URSA_BEARER_TOKEN" \
  --cluster-name majors-cluster \
  --cluster-type aws_parallelcluster_slurm \
  --region us-west-2 \
  --metadata-json '{"region_az":"us-west-2a"}'
```

```bash
ursa --json cluster-jobs create \
  --api-base-url https://ursa.day.lsmc.bio \
  --token "$URSA_BEARER_TOKEN" \
  --cluster-euid M-RGX-CLUSTER \
  --job-name "dy-r help smoke" \
  --job-type slurm \
  --analysis-job-euid M-RGX-ANALYSIS \
  --scheduler-job-id 12345 \
  --request-json '{"command":"dy-r help"}'
```

OWY run-directory trigger readback uses the scoped write service token in
`X-API-Key`:

```bash
ursa --json run-directory-triggers get URDT-EXAMPLE \
  --api-base-url https://ursa.day.lsmc.bio \
  --token "$URSA_WRITE_SERVICE_TOKEN"
```

The generic API wrapper is also available for GUI parity:

```bash
ursa --json api request \
  --api-base-url https://ursa.day.lsmc.bio \
  --token "$URSA_BEARER_TOKEN" \
  --method GET \
  --path /api/v1/compute-clusters
```

## GUI

The Clusters page includes a compute-cluster section for listing and registering
durable cluster objects. The global CLI Viz toggle shows a floating command box
for GUI actions with CLI analogs and includes a copy button. The displayed
command uses the generic `ursa --json api request ...` form with a `<TOKEN>`
placeholder, so secrets are not rendered into the page.

## OWY `dy-r help` Lifecycle

OWY registers a sequencing run with Bloom, registers the run directory with
Dewey, links the Dewey run-dir artifact to the Bloom sequence-run EUID, then
posts to Ursa:

- `POST /api/v1/dewey/run-directory-analysis-triggers`

Ursa creates a workset, a run-context manifest, ordered analysis jobs, Dewey
external-object relations, and an OWY-visible trigger response. Each analysis
job has a deterministic `analysis_experiment_euid` derived from the run-context
row and command order.

Readback is available through both:

- `GET /api/v1/dewey/run-directory-analysis-triggers/{trigger_euid}`
- `GET /api/v1/dewey/run-analysis-triggers/{trigger_euid}` for `URDT-*`
  trigger EUIDs

Readback refreshes the returned analysis-job rows from current persisted job
state. This fixes OWY lifecycle completion polling for run-directory triggers.

## DRA And Destructive Gates

Ursa may verify staging, launch, export, Dewey external-object linking, and
sidecars as part of the run-directory worker. Cluster deletion, staged-data
deletion, and other destructive cleanup remain separate approval-gated actions.
No GUI, CLI, or API route should silently delete DRA mounts, S3 prefixes, FSx
paths, or clusters merely because an analysis job completed.
