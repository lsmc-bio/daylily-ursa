# Dewey Run Analysis Trigger Contract

Ursa accepts Dewey-originated run-analysis triggers through:

- `POST /api/v1/dewey/run-analysis-triggers`
- `GET /api/v1/dewey/run-analysis-triggers/{trigger_euid}`

Both endpoints require the scoped Ursa write service token in `X-API-Key`. Trigger creation also requires `Idempotency-Key`. These are service-token routes; they do not accept a browser admin session as a substitute for Dewey attribution.

## Request

`POST /api/v1/dewey/run-analysis-triggers` accepts:

- `dewey_receipt_euid`
- `run_artifact_set_euid`
- `platform`: `ILMN`, `ONT`, `ULTIMA`, or `HYBRID_ILMN_ONT`
- `command_id`
- `params`
- `sidecar_artifact_euid`
- `sidecar_version_id`
- `run_context_refs`
- `sample_read_refs`
- `sample_identifiers`
- `auto_launch`
- `execution_context` when `auto_launch=true`

`command_id` is validated through the DayEC catalog. Ursa does not accept or execute arbitrary sidecar shell strings. Unknown catalog IDs return a hard error.

When `auto_launch=true`, `execution_context` must include explicit tenant/user and execution context:

- `tenant_id`
- `owner_user_id`
- exactly one of `workset_euid` or `workset`
- exactly one of `manifest_euid` or `manifest`
- `cluster_name`
- `region`
- either `reference_s3_uri` or a completed `staging_job_euid`
- optional `destination`, `session_name`, `project`, `aws_profile`, `optional_features`, `job_name`, and `dry_run`

For manifest creation from a Dewey trigger, `manifest.metadata.analysis_samples_manifest.content` is required. Ursa will not infer a sample manifest from filesystem paths.

Terminal Dewey result registration is opt-in through `execution_context.result_registration`:

- `idempotency_key`
- `payload`

Ursa adds terminal status, analysis job EUID, run artifact-set EUID, Dewey receipt EUID, platform, command ID, sample identifiers, and Ursa lineage refs before calling Dewey `POST /api/v1/analysis-results/register`.

## Response

The response contains:

- `trigger_euid`
- `status`
- `idempotency_key`
- `command_id`
- catalog-backed `command_preview`
- original request payload
- `created_at`
- `updated_at`
- `analysis_job_euid` when an analysis job was created
- `staging_job_euid` when an existing staging job was reused
- `dewey_result` when a terminal launch registered results back to Dewey

`auto_launch=false` records a durable queued trigger. `auto_launch=true` creates a workset/manifest as requested, defines an analysis job, and launches it through the existing Ursa analysis job manager. Replay with the same idempotency key and identical payload returns the stored trigger response without creating a second analysis job. Reusing an idempotency key with a different payload returns `409`.

## Dewey Result Return

Ursa's Dewey client exposes `register_analysis_results(...)`, which posts terminal result payloads to Dewey `POST /api/v1/analysis-results/register` using bearer auth and the supplied idempotency key.

Terminal result registration happens when a launched or refreshed analysis job reaches `COMPLETED` or `FAILED` and the job request carries a Dewey result registration context. Result payloads should contain Dewey artifact refs and opaque EUID/XID identifiers, not PHI or patient-facing identifiers.

## Run-Directory Trigger

OWY uses the run-directory-specific trigger:

- `POST /api/v1/dewey/run-directory-analysis-triggers`

This route requires the scoped Ursa write service token in `X-API-Key` and
`Idempotency-Key`.

Request fields:

- `dewey_run_artifact_euid`
- `run_storage_uri`
- `run_folder_name`
- `platform`: `ILMN`, `ONT`, or `ULTIMA`
- `command_ids`: ordered DayEC `command_class=run_analysis` IDs
- `bloom_run_euid`: optional string or `null`
- `producer_system`, `producer_object_euid`, `owy_execution_id`
- `run_metadata`
- `dry_run`

Ursa resolves the Dewey artifact and requires
`artifact_type=sequencing_run_dir` plus an exact normalized S3 URI match before
creating work. Ursa validates each command ID against the DayEC catalog and
rejects non-`run_analysis` commands.

Production Ursa deployments must provide the run-directory analysis policy explicitly. The policy must include tenant UUID, owner user ID, cluster name, region, reference S3 URI, stage target, destination S3 URI, project, and AWS profile. Missing values intentionally return `503 Ursa run-directory analysis policy is incomplete`; Ursa must not infer defaults from deployment name, environment variables, or DayEC catalog content.

For the `lsmcok1` production deployment, OWY currently sends `illumina_run_qc_bclconvert` for ILMN runs. The DayEC command catalog entry must remain `command_class=run_analysis` and `input_contract=run_context` before this route can launch it.

Do not log or print Dewey, Ursa, or broker service tokens while validating this route. Smoke checks should report response codes, EUIDs, and redacted config presence only.

When `bloom_run_euid` is supplied, Ursa creates an Ursa-local external-object
child under the run-directory trigger and creates a Dewey external-object
relation from the Dewey run-dir artifact to the Bloom sequencing run. When
`bloom_run_euid` is `null`, Ursa skips those Bloom links and still creates the
trigger, workset, manifest, and analysis jobs.

The response includes `trigger_euid`, `workset_euid`, `manifest_euid`,
`analysis_job_euids`, `analysis_jobs`, `ursa_external_objects`,
`dewey_external_relations`, and the optional `bloom_run_euid`.

## Persistence

Ursa stores trigger/idempotency records in the ResourceStore/TapDB template:

- `RGX/dewey/run-analysis-trigger/1.0/`
- `RGX/external/object/1.0/` for local external-object children

The stored record includes the idempotency key, canonical request fingerprint, status, original request, response, analysis job EUID, staging job EUID, and error field. This is append-style trigger evidence; replay is handled from the persisted fingerprint and response.

## Cross-Service Boundaries

- Dewey owns canonical sequencer-run and analysis-result artifact registration.
- Ursa owns staging, launch, monitor, export orchestration, and terminal Dewey result return.
- DayEC owns command catalog validation and execution argument construction.
- DayOA owns workflow recipes.
- QEO consumes Dewey evidence; Ursa does not interpret QC meaning.
- Atlas receives Dewey links through the approved result-return path.
- Bloom ULTIMA/hybrid wet-lab queue support is intentionally out of scope for this work.
