# wads.fleet_migrate

Batch migration helpers across the user’s local Python ecosystem.

Single entry point: `fleet_stub` (also exposed as `wads-migrate fleet-stub`)
which converts a batch of repos to the SSOT stub CI workflow in one call.

Reads the candidate list from the wads-ci-sweep state file
(`~/Downloads/wads_ci_diagnosis.json`), selects by category, orders by
last-commit recency, and applies `migrate_ci_to_stub` to each. Per-repo
failures are isolated — the batch never aborts midway.

See: wads-ci-sweep skill at `~/.claude/skills/wads-ci-sweep/` for the
ecosystem inventory + state-tracking it relies on.

### Functions

| [`fleet_stub`](#wads.fleet_migrate.fleet_stub)(\*[, limit, select_category, ...])   | Stub-migrate up to `limit` repos, picked from the sweep state file.   |
|--------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| [`migrate_one_to_stub`](#wads.fleet_migrate.migrate_one_to_stub)(repo_path, \*[, pin, ...])  | Stub-migrate one repo end-to-end: sync, rewrite, commit, push.        |
| [`read_sweep_state`](#wads.fleet_migrate.read_sweep_state)([path])                        | Load the wads-ci-sweep state file.                                    |
| [`select_candidates`](#wads.fleet_migrate.select_candidates)(state, \*[, category, ...])   | Pick which packages to migrate, in priority order.                    |

### Classes

| [`RepoResult`](#wads.fleet_migrate.RepoResult)(name, path, status[, detail])   | Outcome of attempting to stub-migrate one repo.   |
|---------------------------------------------------------------------------------------------|---------------------------------------------------|

### *class* wads.fleet_migrate.RepoResult(name, path, status, detail='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Outcome of attempting to stub-migrate one repo.

### wads.fleet_migrate.fleet_stub(, limit=20, select_category='uv_current', state_file=PosixPath('/home/runner/Downloads/wads_ci_diagnosis.json'), dry_run=False, pin='@master', commit_message='ci: switch to wads reusable workflow stub', order_by='git_recency')

Stub-migrate up to `limit` repos, picked from the sweep state file.

* **Parameters:**
  * **limit** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Max repos to migrate this run.
  * **select_category** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Only consider packages with this `category` in the
    sweep state file (default `"uv_current"`).
  * **state_file** ([`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Path to the wads-ci-sweep JSON. Default
    `~/Downloads/wads_ci_diagnosis.json`.
  * **dry_run** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – If True, print candidates and exit without touching anything.
  * **pin** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Wads ref the stub points at (passed to `migrate_ci_to_stub`).
  * **commit_message** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Commit message for the per-repo stub-conversion commit.
  * **order_by** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Candidate ordering — `"git_recency"` or `"name"`.
* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`RepoResult`](#wads.fleet_migrate.RepoResult)]
* **Returns:**
  List of [`RepoResult`](#wads.fleet_migrate.RepoResult), one per attempted repo (empty for dry-run).

### wads.fleet_migrate.migrate_one_to_stub(repo_path, , pin='@master', commit_message='ci: switch to wads reusable workflow stub', workflow_path='.github/workflows/ci.yml')

Stub-migrate one repo end-to-end: sync, rewrite, commit, push.

Idempotent: if the workflow is already on the latest stub template, returns
`status="noop"`.

* **Return type:**
  [`RepoResult`](#wads.fleet_migrate.RepoResult)

### wads.fleet_migrate.read_sweep_state(path=PosixPath('/home/runner/Downloads/wads_ci_diagnosis.json'))

Load the wads-ci-sweep state file.

* **Raises:**
  [**FileNotFoundError**](https://docs.python.org/3/builtins/exceptions.html#FileNotFoundError) – if the state file does not exist (the caller likely
      needs to run `python ~/.claude/skills/wads-ci-sweep/sweep.py
      diagnose` to create it).
* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### wads.fleet_migrate.select_candidates(state, , category='uv_current', limit=20, order_by='git_recency')

Pick which packages to migrate, in priority order.

* **Parameters:**
  * **state** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)) – Sweep state dict (from [`read_sweep_state()`](#wads.fleet_migrate.read_sweep_state)).
  * **category** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – Only consider packages with this `category`. Default
    `"uv_current"` — repos already on inline uv-CI that can safely
    move to the stub. Other useful values: `"uv_stub"` (already
    done; useful for refresh sweeps after a stub-template change).
  * **limit** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – Max number of repos to return.
  * **order_by** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – `"git_recency"` (default) sorts most-recently-committed
    first. `"name"` sorts alphabetically.
* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)]
* **Returns:**
  List of package records (subset of `state['packages']`), in the
  chosen order.
