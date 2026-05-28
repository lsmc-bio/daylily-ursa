# Shell Session Defaults

- Default to an interactive shell for shell work. On this Mac, use the user's default shell unless the user explicitly asks for another shell.
- For AWS EC2, ParallelCluster, and other remote Linux hosts, default to an interactive `bash` login shell as `ubuntu`. Do not use `root` unless the user explicitly grants permission for that specific work; use targeted `sudo` from `ubuntu` when escalation is required.
- For Daylily/DayOA/DAY-EC headnode workflow work, use an interactive `ubuntu` tmux/login-shell pane for controllers and workflow commands. Run setup as separate commands in that pane (`source dyoainit`, then `dy-a ...`, then `dy-r ...`) so aliases/functions are defined before use.
- SSM Run Command is for simple inspection or for writing helper scripts through the supported helpers. Do not launch workflow controllers or rely on `dy-*` aliases from non-interactive SSM scripts.

# WHEN INITIALIZING A NEW TERMINAL SESSION

## ALWAYS DO THIS FIRST FROM THIS REPO ROOT
source ./activate <deploy-name>

## CLI Policy

- Use `ursa ...` as the primary interface for normal Ursa work.
- Use `tapdb ...` only when Ursa explicitly delegates low-level DB/runtime lifecycle to TapDB.
- Use `daycog ...` only when Ursa explicitly delegates shared Cognito lifecycle to Daycog.

## Activation Contract

- `source ./activate <deploy-name>` must only create the conda env if missing, activate it, and run exactly one `python -m pip install -e .` on first create.
- Do not add any other pip installs, conda installs, config copying, runtime env exports, pre-commit installs, Playwright installs, or tool checks to `activate`.
- The only allowed PATH adjustment in `activate` is a minimal `${CONDA_PREFIX}/bin` prepend after `conda activate` so the repo's declared console scripts win over conflicting global installs.
- If Ursa needs Python dependencies, put them in `pyproject.toml`.
- If Ursa needs system/bootstrap packages, put them in `environment.yaml`.
- If an Ursa CLI is missing from PATH after activation, fix the packaging entrypoint or the minimal conda-env bin precedence rule, not by adding broader shell hacks.
- The declared console scripts `ursa` and `daylily-workset-api` must remain available from the activated conda env.

## Packaging Boundary

- `environment.yaml` is for Python itself, `pip`, `setuptools`, and non-Python/system packages only.
- `environment.yaml` must not contain a `pip:` block or Python library dependencies.
- `pyproject.toml` owns all Python dependencies needed by the repo in `project.dependencies`.
- `pyproject.toml` must not use `project.optional-dependencies` for repo Python installs.
- Do not add any secondary install set such as `.[dev]`, `.[test]`, or `requirements-dev.txt`.

## No Circumvention Policy

- Do not bypass `ursa`, `tapdb`, or `daycog` with raw tools just because something is missing or broken.
- Do not treat direct `python -m ...`, raw `postgres`, raw AWS CLI mutations, or direct config-file edits as automatic substitutes.
- If the intended CLI path is broken or incomplete, stop, diagnose, and ask for permission before circumventing it.
- Prefer patience and repair of the intended CLI workflow over inventing a shortcut.

## Ursa Examples

- Start with `source ./activate <deploy-name>`
- Use `ursa server start --port 8913`
- Use `ursa config ...` and `ursa env ...` for Ursa-owned runtime operations
- Use `daycog ...` for Cognito lifecycle and `tapdb ...` for DB/runtime lifecycle where Ursa docs explicitly delegate to them

## CHANGE POLICY

- Build only the current interface unless the user directly asks for support for prior interfaces.
- Treat prior-interface support as an explicit requirement, not a safe default.
- Do not assume existing data needs transformation unless the user directly says it does.
- Do not add transition code, alternate read/write paths, or prior-field support unless explicitly requested.
- Fallback behavior is an antipattern in this workspace. Do not add, preserve, or rely on inferred config paths, environment-derived deployment identity, compatibility shims, alternate TapDB namespaces, generated substitute values, or silent analysis/service state. Missing config, credentials, TapDB namespace, workset metadata, or malformed input must fail hard with a clear error.

## DAYHOFF SERVICE EXPOSURE SECURITY

- Ursa is an approved-network customer/collaborator Dayhoff service, not a globally public internet service.
- Do not add global service ingress, wildcard/fallback vhosts, old callback aliases, inferred return URLs, or service-side host discovery.
- Ursa must consume explicit broker claims and registered-service credentials; do not infer customer/network access locally.
- `kahlo`, `bloom`, and `zebra_day` are LSMC-internal only; `login`, `atlas`, `dewey`, and `ursa` are approved-network customer/collaborator services.
- Service-host certs use DNS-01 renewal; do not depend on HTTP-01 public reachability for Ursa service hosts.
- Future dev, test, and stage deployments must use their own approved-source lists, credentials, certificates, cluster policies, and tenant data, separate from production.

## Version Tags

- Use non-v semver tags for package releases, e.g. `2.0.19` or `5.0.21`, not `v2.0.19`.
- Commit first, then tag the exact clean release commit.
- Use annotated tags for release provenance: `git tag -a 2.0.19 -m "Release 2.0.19"`.
- Lightweight tags are acceptable only for scratch/internal marks, not package releases.
- Do not move or overwrite pushed version tags. If a pushed tag is wrong, cut the next patch version.
- If signing is configured and expected, use signed annotated tags: `git tag -s 2.0.19 -m "Release 2.0.19"`.
- Verify tag type with `git cat-file -t 2.0.18`; `tag` means annotated and `commit` means lightweight.
