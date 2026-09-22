# wads.secrets_cli

`wads-secrets` — manage the CI secrets/env vars of a wads-managed repo.

A secret becomes usable in CI through two layers (see [`wads.ci_secrets`](wads.ci_secrets.md#module-wads.ci_secrets)
for the model):

1. **pyproject** `[tool.wads.ci.env]` — declares the env var (and whether it
   is required), so the reusable workflow exports it into the job environment.
2. **transport** — the repo’s `ci.yml` stub passes secrets to the reusable
   workflow. Modern stubs pass the whole secrets context as one
   `WADS_CI_SECRETS_JSON` secret, so *no per-secret stub edit is needed*;
   legacy named-transport stubs list each secret explicitly (and every listed
   name must be in the frozen wads superset).

`wads-secrets add` performs the needed edits in one step, and can also set
the secret’s value on GitHub via `gh` — so a single command takes a secret
from “not configured” to “available in CI”. For values that are \*\*not
sensitive\*\* (a test verbosity level, a feature flag), use `--variable` to
store them as a GitHub repository *variable* instead of a secret — declared
env vars fall back to repo variables automatically, and committed constants
can simply live in `[tool.wads.ci.env].defaults`.

Examples:

```default
wads-secrets add OPENAI_API_KEY                 # var == secret name
wads-secrets add HF_TOKEN HF_WRITE_TOKEN         # env var <- aliased secret
wads-secrets add DB_URL --kind required          # fail CI if unset
wads-secrets add COSMO_TEST_LEVEL --variable     # non-sensitive: repo var
wads-secrets add OPENAI_API_KEY --no-github      # edit files only
wads-secrets list                                # show configured env vars
```

Names are forced to `UPPER_SNAKE` and value-looking inputs are rejected, so
you can’t accidentally commit a secret *value* as a name.

### Functions

| [`add`](#wads.secrets_cli.add)(var_name[, secret_name, repo, kind, ...])   | Configure a CI value: declare it in pyproject, transport it, set its value.   |
|--------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------|
| [`add_env_var_to_pyproject`](#wads.secrets_cli.add_env_var_to_pyproject)(pyproject_path, ...)   | Add `var_name` to `[tool.wads.ci.env]`; record alias if names differ.         |
| [`add_secret_to_stub`](#wads.secrets_cli.add_secret_to_stub)(ci_file, secret_name)        | Ensure the stub `ci.yml` passes `secret_name` to the reusable workflow.       |
| [`list_`](#wads.secrets_cli.list_)([pyproject])                              | List the env vars configured in `[tool.wads.ci.env]`.                         |
| [`main`](#wads.secrets_cli.main)([argv])                                    | `wads-secrets` CLI entry point (argparse-based).                              |
| [`set_github_secret`](#wads.secrets_cli.set_github_secret)(repo, secret_name, value, \*) | Set a secret (or, with `variable=True`, a repo variable) via `gh`.            |
| [`stub_transport_mode`](#wads.secrets_cli.stub_transport_mode)(ci_file)                    | Classify the repo's `ci.yml`: `'json'`, `'named'`, `'inline'`, or `None`.     |
| [`superset`](#wads.secrets_cli.superset)()                                      | Print the wads secret superset (names a stub may pass).                       |

### wads.secrets_cli.add(var_name, secret_name=None, , repo=None, kind='extra', value=None, github=True, variable=False, pyproject='pyproject.toml', ci_file='.github/workflows/ci.yml')

Configure a CI value: declare it in pyproject, transport it, set its value.

* **Parameters:**
  * **var_name** – env-var name your code reads (forced to UPPER_SNAKE).
  * **secret_name** – GitHub secret backing it (default: same as var_name).
  * **repo** – `org/repo` to set the secret on (default: git origin here).
  * **kind** – `extra` (default), `test`, or `required`.
  * **value** – secret value to push to GitHub (default: `$VAR_NAME` in env).
  * **github** – also set the value on GitHub via `gh` (default True).
  * **variable** – store as a repository *variable* instead of a secret —
    for non-sensitive values (a test verbosity level, a flag). Variables
    need no transport at all: the reusable workflow reads the caller’s
    `vars` context directly and declared env vars fall back to it.

### wads.secrets_cli.add_env_var_to_pyproject(pyproject_path, var_name, secret_name, , kind='extra')

Add `var_name` to `[tool.wads.ci.env]`; record alias if names differ.

Returns `(changed, existing_bucket)`. If the var is already declared,
makes no change and returns `(False, <bucket>)`.

### wads.secrets_cli.add_secret_to_stub(ci_file, secret_name)

Ensure the stub `ci.yml` passes `secret_name` to the reusable workflow.

Returns `(changed, reason)`. `reason` explains no-ops (JSON transport
passes everything already, already present, not a stub, file missing).

### wads.secrets_cli.list_(pyproject='pyproject.toml')

List the env vars configured in `[tool.wads.ci.env]`.

### wads.secrets_cli.main(argv=None)

`wads-secrets` CLI entry point (argparse-based).

### wads.secrets_cli.set_github_secret(repo, secret_name, value, , variable=False)

Set a secret (or, with `variable=True`, a repo variable) via `gh`.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### wads.secrets_cli.stub_transport_mode(ci_file)

Classify the repo’s `ci.yml`: `'json'`, `'named'`, `'inline'`, or `None`.

`'inline'` means a workflow that does not call the reusable uv-ci (it
reads repo secrets directly and has no transport layer — and no
repo-variable fallback either). `None` means no ci.yml at all.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str) | [`None`](https://docs.python.org/3/builtins/constants.html#None)

### wads.secrets_cli.superset()

Print the wads secret superset (names a stub may pass).
