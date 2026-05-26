# Dewey Run Analysis Trigger Contract

Ursa accepts Dewey-originated run-analysis triggers through:

- `POST /api/v1/dewey/run-analysis-triggers`
- `GET /api/v1/dewey/run-analysis-triggers/{trigger_euid}`

Both endpoints require the scoped Ursa write service token in `X-API-Key`. Trigger creation also requires `Idempotency-Key`.

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

`command_id` is validated through the DayEC catalog. Ursa does not accept or execute arbitrary sidecar shell strings.

## Response

The current private implementation records a queued trigger:

- `trigger_euid`
- `status=QUEUED`
- `idempotency_key`
- `command_id`
- catalog-backed `command_preview`
- original request payload
- `created_at`
- `updated_at`

Live cluster launch, export monitoring, Dewey terminal result registration, and idle cleanup are still owned by Ursa execution code paths and deployment gates. Destructive idle cluster deletion remains config-gated and requires the workspace approval boundary before live action.

## Dewey Result Return

Ursa's Dewey client exposes `register_analysis_results(...)`, which posts terminal result payloads to Dewey `POST /api/v1/analysis-results/register` using bearer auth and the supplied idempotency key.
