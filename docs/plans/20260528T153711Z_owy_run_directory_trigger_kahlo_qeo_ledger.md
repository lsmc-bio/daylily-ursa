# OWY Run-Directory Trigger Production Fix And Kahlo QEO Visibility Ledger

## Summary

This ledger tracks the Ursa `4.0.13` production fix for OWY run-directory triggers and the live Kahlo QEO visibility update on AWS `lsmcok1` in `us-west-2`.

The live OWY blocker was:

```text
POST https://ursa.day.lsmc.bio/api/v1/dewey/run-directory-analysis-triggers
503 Ursa run-directory analysis policy is incomplete: cluster_name, destination_s3_uri, owner_user_id, reference_s3_uri, region, stage_target, tenant_id
```

No OWY, Bloom, Dewey, Dayhoff generator/pin, token rotation, database reset, or AWS network changes are in scope.

## Gate 0 Inventory

- Host: EC2 `i-09126000eb19643b0`, `ip-10-0-0-77.us-west-2.compute.internal`.
- Ursa live root: `/home/ubuntu/.cache/dayhoff/local/lsmcok1/repos/daylily-ursa`.
- Ursa baseline: tag `4.0.12`, commit `d3eadc75743c8f1ee1f79244d694c63533d56e52`.
- Ursa dirty state before edits: detached HEAD with untracked `*.bak-*` files only.
- Kahlo live root: `/home/ubuntu/.cache/dayhoff/local/lsmcok1/repos/kahlo`.
- Kahlo baseline: tag `2.0.5`, commit `0a613a0`.
- Kahlo live config lacked `qeo` in `fleet.targets` and the directory snapshot did not contain `qeo`.
- DayEC in Ursa runtime: `5.0.20`; `pcluster` available in the Ursa conda env.
- ParallelCluster `goodole3` exists in `us-west-2` and is `CREATE_COMPLETE`.
- DayEC catalog contains `illumina_run_qc_bclconvert`, `ont_run_qc`, and `ultima_run_qc` as `run_analysis` / `run_context`.
- Ursa live config had Dewey enabled and a redacted Dewey API token set, but no `ursa_run_directory_analysis_*` policy keys.

## Production Policy Values

```yaml
ursa_run_directory_analysis_tenant_id: "28ce303b-0712-402b-927e-b770c5979fcf"
ursa_run_directory_analysis_owner_user_id: "johnm@lsmc.com"
ursa_run_directory_analysis_cluster_name: "goodole3"
ursa_run_directory_analysis_region: "us-west-2"
ursa_run_directory_analysis_reference_s3_uri: "s3://lsmc-dayoa-references-usw2/"
ursa_run_directory_analysis_stage_target: "/staging/staged_external_sequencing_data"
ursa_run_directory_analysis_destination_s3_uri: "s3://lsmc-dayoa-analysis-results-usw2/owy-run-directory-analysis/"
ursa_run_directory_analysis_project: "daylily"
ursa_run_directory_analysis_aws_profile: "lsmc"
```

## Ledger Rows

| ID | Agent | Area | Requirement | Status | Category | Gate | Evidence | Root Cause | Terminal Note |
|---|---:|---|---|---|---|---|---|---|---|
| LEDGER-001 | 1 | Planning | Create ledger with Ursa/Kahlo live state, current tags, dirty files, and OWY failure text | SUCCESS | plan_amendment | Gate 0 | This file |  | Ledger created with Gate 0 inventory and scoped failure text. |
| INV-001 | 1 | Inventory | Record live Ursa `4.0.12`, Kahlo `2.0.5`, listeners, tmux sessions, and config backup paths | SUCCESS | config_or_startup_contract | Gate 0 | `git status --short --branch`; live config inspection; listeners on 8913/8911 checked |  | Baseline recorded; backup paths will be added after live config edits. |
| DEP-001 | 2 | Ursa Deps | Verify DayEC `>=5.0.19`, `goodole3` exists, AWS profile `lsmc` works, and Dewey client config is active | SUCCESS | config_or_startup_contract | Gate 1 | DayEC `5.0.20`; `goodole3` `CREATE_COMPLETE`; `aws sts get-caller-identity --profile lsmc`; Dewey enabled with redacted token |  | Runtime dependencies are present. |
| DEP-002 | 2 | Command Catalog | Verify `illumina_run_qc_bclconvert`, `ont_run_qc`, and `ultima_run_qc` are `run_analysis` / `run_context` | SUCCESS | contract_test | Gate 1 | Installed DayEC catalog inspection prints all three as `run_analysis run_context` |  | OWY command catalog prerequisite is satisfied. |
| SRC-001 | 3 | Ursa Source | Add release notes/docs/tests for OWY run-directory production policy and no-secret logging | SUCCESS | feature_implementation | Gate 2 | `docs/dewey_run_analysis_triggers.md`; `tests/test_dewey_run_analysis_triggers.py` |  | Added production policy documentation and focused BCL Convert command acceptance test. |
| TEST-001 | 4 | Ursa Tests | Run focused Ursa tests and build before release | SUCCESS | contract_test | Gate 3 | `python -m pytest tests/test_dewey_run_analysis_triggers.py tests/test_daylily_ec_runner.py -q` -> 17 passed; `python -m build` succeeded; `git diff --check` passed |  | Focused tests and package build passed. |
| RELEASE-001 | 5 | Ursa Release | Commit, push, tag annotated `4.0.13`, push tag, and create release notes describing the config/runtime work | OPEN | feature_implementation | Gate 4 |  |  |  |
| CFG-001 | 6 | Ursa Config | Backup live Ursa config and add explicit `ursa_run_directory_analysis_*` values without printing tokens | OPEN | config_or_startup_contract | Gate 5 |  |  |  |
| URSA-LIVE-001 | 7 | Ursa Runtime | Deploy/restart only Ursa, verify `https://ursa.day.lsmc.bio/healthz`, and prove policy-incomplete `503` is gone | OPEN | config_or_startup_contract | Gate 6 |  |  |  |
| KAHLO-001 | 8 | Kahlo Config | Backup live Kahlo config and directory snapshot, then add QEO directory/binding/fleet target entries | OPEN | config_or_startup_contract | Gate 7 |  |  |  |
| KAHLO-002 | 8 | Kahlo Runtime | Sync/poll Kahlo projections or restart only Kahlo if required; verify QEO appears in directory/fleet views | OPEN | config_or_startup_contract | Gate 7 |  |  |  |
| OWY-001 | 9 | Acceptance | Ask OWY operator to rerun xfer1 smoke on next completed ILMN run and record returned trigger/workset/manifest/job EUIDs | OPEN | contract_test | Gate 8 |  |  |  |
| FINAL-001 | 1 | Final | Record release URL, tag SHA, live evidence, config backups, restarts, and remaining OWY-side validation status | OPEN | contract_test | Gate 9 |  |  |  |

## Notes

- Missing run-directory policy remains a loud `503`; no fallback/default inference is added.
- Kahlo QEO visibility is live config/projection work only unless source inspection proves a Kahlo code release is required.
- Dayhoff generator durability is intentionally out of scope for this ledger.
