# Ursa External Object Analysis Trigger Ledger

Created: 2026-05-28T09:05:49Z

## Gate 0: Inventory Freeze

- Controlling request: make Ursa accept optional `bloom_run_euid` from OWY, remove the mandatory Ursa-to-Bloom create call, and create a Ursa-local external-object child plus Dewey external-object relation when Bloom EUID is supplied.
- Ledger path: `docs/plans/20260528T090549Z_ursa_external_object_analysis_trigger_ledger.md`.
- Repo path: `/Users/jmajor/projects/mega_dayhoff/repos_work/daylily-ursa-4.0.3-owy-run-triggers`.
- Branch/status: `git status --short --branch` -> `## codex/owy-run-directory-analysis-20260528...origin/codex/owy-run-directory-analysis-20260528`.
- Version baseline: `git describe --tags --dirty --always` -> `4.0.4`; `git rev-parse HEAD` -> `b38554f108e54a4a5f4c0e2b567669fc5073a70f`.
- Remote: `git@github.com:lsmc-bio/daylily-ursa.git`.
- Instructions read: `/Users/jmajor/.codex/docs/plan-ledger-workflow.md` and repo `AGENTS.md`.
- Current code evidence: `DeweyRunDirectoryAnalysisTriggerRequest` requires Dewey artifact, run URI/name, platform, command IDs, and metadata; response currently requires `bloom_run_euid: str`; endpoint currently calls `app.state.bloom_client.create_or_reuse_run_directory_run()` and Bloom client calls `/api/v1/external/ursa/run-directories`.
- Production service evidence: `https://ursa.day.lsmc.bio/openapi.json` version `2.0.11.34` does not expose `/api/v1/dewey/run-directory-analysis-triggers`; Bloom production `5.0.35` exposes `/api/v1/object-creation/create` and reports healthy; Dewey production exposes external-object relation routes.
- DayEC catalog evidence: `/Users/jmajor/.codex/worktrees/dyec-fsx-dra-mounts/daylily-ephemeral-cluster`, tag `5.0.18`, commit `783eb842888d3869d2a51aa2a38964db4e637d8e`; run-analysis command IDs include `ont_run_qc`, `ultima_run_qc`, and `illumina_run_qc_bclconvert`.

## Rows

| ID | Area | Requirement | Status | Category | Gate | Owner | Evidence | Root Cause | Terminal Note |
|---|---|---|---|---|---|---|---|---|---|
| G0-001 | Baseline | Record repo state, route/version evidence, current Bloom dependency, and catalog IDs before implementation. | SUCCESS | plan_amendment | Gate 0 | Agent 1 | Gate 0 section above. |  | Inventory recorded before runtime edits for this plan. |
| URSA-001 | API contract | Add nullable `bloom_run_euid` to run-directory trigger request and response. | SUCCESS | feature_implementation | Gate 1 | Agent 3 | `DeweyRunDirectoryAnalysisTriggerRequest` and response now allow `str | None`. |  | Empty strings normalize to `None`. |
| URSA-002 | Bloom boundary | Remove mandatory Bloom service call from run-directory trigger endpoint while leaving other Bloom resolver behavior intact. | SUCCESS | feature_implementation | Gate 1 | Agent 3 | Endpoint no longer calls `app.state.bloom_client.create_or_reuse_run_directory_run()`. |  | Existing Bloom resolver client remains for other code paths. |
| URSA-003 | Local external object | Add Ursa-local external-object template/store support and child lineage from run-directory trigger to Bloom external object when EUID is present. | SUCCESS | feature_implementation | Gate 1 | Agent 4 | Added `RGX/external/object/1.0/`, `ExternalObjectRecord`, and `create_external_object_child()`. |  | Local external object is child-linked to the trigger record. |
| URSA-004 | Dewey relations | Create Dewey Bloom relation only when `bloom_run_euid` is present; always create Ursa trigger/job relations. | SUCCESS | feature_implementation | Gate 1 | Agent 4 | Endpoint guards Bloom Dewey relation with `if bloom_run_euid is not None`. |  | Ursa trigger/job relations are always created. |
| URSA-005 | Null behavior | Null or missing Bloom EUID must not call Bloom, must not create Bloom relations, and must still create trigger/workset/manifest/jobs. | SUCCESS | contract_test | Gate 1 | Agent 4 | `test_run_directory_trigger_accepts_null_bloom_run` passes in focused harness. |  | Null Bloom creates no local Bloom external object and no Dewey Bloom relation. |
| URSA-006 | Idempotency | Idempotency replay must return the same trigger/external-object state; mismatched payload must return `409`. | SUCCESS | contract_test | Gate 5 | Agent 4 | Updated run-directory trigger test replays same idempotency key and receives same trigger/external-object response; existing mismatch coverage remains. |  | Mismatched payload behavior is unchanged through fingerprint check. |
| URSA-007 | Command validation | Preserve DayEC `run_analysis` validation for `ont_run_qc`, `ultima_run_qc`, and `illumina_run_qc_bclconvert`, now requiring `daylily-ephemeral-cluster>=5.0.19`. | SUCCESS | contract_test | Gate 5 | Agent 3 | Test command catalog fixture now includes these IDs; route still rejects non-`run_analysis`. Runtime guard and package metadata now require `>=5.0.19` instead of exact `5.0.14`. |  | Local rebuilt checkout reports `5.0.19.dev1+gba81e9cef`, which is still lower than final `5.0.19` under Python packaging semantics. Production Ursa should install a final `5.0.19` or newer DAY-EC build. |
| REL-001 | Release | Cut next semver after current GitHub max `4.0.4` only after tests pass; do not move `4.0.4`. | BLOCKED | active_product_contract | Gate 5 | Agent 5 | Current local tag is `4.0.4`; production route missing. | Requires PR/check/release/deploy approval after local implementation. | Local implementation can proceed; production release remains gated. |

## Status Summary

- SUCCESS: 8
- OPEN: 0
- BLOCKED: 1
- FAIL: 0
