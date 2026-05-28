# Ursa Token Plaintext Display Release Ledger

## Summary

Fix the Ursa GUI token-create flow so the one-time plaintext token returned by the API is displayed in the page that created it instead of being lost to an immediate reload. Release from the current highest Ursa tag `4.0.11`, deploy the new tag to the AWS `lsmcok1` Dayhoff-managed Ursa runtime in `us-west-2`, and verify `https://ursa.day.lsmc.bio` reports the new version.

## Gate 0 Inventory

- Local release worktree: `/Users/jmajor/projects/mega_dayhoff/repos_work/daylily-ursa-token-plaintext-20260528`
- Source base: tag `4.0.11` (`80f41c9 Include Ursa TapDB templates in container image`)
- Remote: `git@github.com:lsmc-bio/daylily-ursa.git`
- `origin/main`: `4.0.0`, older than current release tags; this fix is based on highest released tag `4.0.11`.
- Current release branch: `codex/ursa-token-plaintext-20260528`
- Local pre-change status: clean.
- AWS target: Dayhoff-managed Ursa on `lsmcok1`, `us-west-2`, public host `ursa.day.lsmc.bio`, running root expected at `/home/ubuntu/.cache/dayhoff/local/lsmcok1/repos/daylily-ursa`.
- Live database changes: none planned.
- Live service restart: Ursa only, after tag is pushed.

## Ledger Rows

Use statuses: `OPEN`, `IN_PROGRESS`, `ATTEMPTING_BUGFIX`, `SUCCESS`, `DUPLICATE`, `NO_LONGER_NEEDED`, `FAIL`, `BLOCKED`.

| ID | Area | Requirement | Status | Gate | Evidence | Terminal Note |
|---|---|---|---|---|---|---|
| LEDGER-001 | Planning | Create ledger with source, release, AWS target, and live-action limits | SUCCESS | Gate 0 | This file | Gate 0 recorded. |
| BUG-001 | GUI | Identify why token creation loses the one-time plaintext token | SUCCESS | Gate 1 | API returns `plaintext_token`; GUI reloads immediately after create | Root cause confirmed in `tokens/list.html`, `admin_tokens.html`, and `admin_client_detail.html`. |
| FIX-001 | GUI | Display the returned one-time plaintext token in-place on user, admin, and client token-create pages | SUCCESS | Gate 2 | `UrsaPortal.renderOneTimeTokenResult(...)`; token result containers in all three templates | One-time token is displayed from the API response without automatic reload. |
| TEST-001 | Tests | Add focused tests proving token pages no longer reload away the plaintext result | SUCCESS | Gate 3 | `node --check daylib_ursa/gui/static/portal.js`; `python -m pytest tests/test_user_tokens_api.py tests/test_admin_gui_and_cluster_routes.py -q` -> 26 passed; `python -m build` succeeded | Local env needed `python -m pip install -e .` and `python -m pip install build` before tests/build. |
| RELEASE-001 | Release | Commit, push branch, create annotated next semver tag, and push tag | OPEN | Gate 4 |  |  |
| AWS-001 | Deploy | Update AWS `lsmcok1` Ursa checkout to the new tag and restart only Ursa | OPEN | Gate 5 |  |  |
| AWS-002 | Validation | Verify local AWS Ursa health and public `ursa.day.lsmc.bio` report the new version | OPEN | Gate 5 |  |  |
| FINAL-001 | Acceptance | All rows terminal; report commit, tag, tests, deployment evidence, and new version | OPEN | Gate 6 |  |  |

## Test Plan

- Static syntax:
  - `node --check` is not applicable because token JS is embedded in templates.
- Focused local tests:
  - `python -m pytest tests/test_user_tokens_api.py tests/test_admin_gui_and_cluster_routes.py -q`
- Build:
  - `python -m build`
- AWS live-safe validation:
  - Verify AWS checkout is at the new tag.
  - Restart only the Ursa process/session.
  - `curl -sk https://localhost:8913/healthz`
  - `curl -sk https://ursa.day.lsmc.bio/healthz`

## Notes

- The plaintext token is not persisted by this fix. It is rendered only from the API response in the current browser page.
- Revocation flows may continue to reload after mutation because no one-time secret is involved.
