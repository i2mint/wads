# wads.scripts.export_ci_env

Export the pyproject-declared CI environment to `$GITHUB_ENV`.

This is the run-time half of wads’ two-layer secret model (see
[`wads.ci_secrets`](wads.ci_secrets.md#module-wads.ci_secrets)). The reusable workflow receives the caller’s secrets
either as named pass-throughs (legacy stubs) or as one double-encoded JSON
blob under `WADS_CI_SECRETS_JSON` (modern stubs); this script decides which
values actually become job environment variables, driven entirely by
`[tool.wads.ci.env]` in the consumer’s `pyproject.toml` (read via the
`read-ci-config` action):

* `defaults`  — literal `KEY=value` pairs, always written.
* `required_envvars` — must resolve non-empty, else CI **fails** with a
  precise message.
* `test_envvars` — exported if set; a **warning** is emitted if missing.
* `extra_envvars` — exported if set; silent if missing.
* `secret_aliases` — map `ENV_VAR -> SECRET_NAME` for the (rare) case where
  the env var the code reads differs from the GitHub secret name.

Each declared name resolves against **secrets first** (named ones merged with
the transport blob) and the caller’s **repository variables second** (the
`vars` context resolves to the caller’s repo in a reusable workflow) — so a
non-sensitive value like a test verbosity level can live in a repo variable
instead of being mis-classified as a secret.

Secret *values* are never printed. Values extracted from the transport blob
are not auto-masked by GitHub (only the blob as a whole is), so every
secret-sourced value is re-registered with `::add-mask::` (per line, the
documented form for multiline values) before being written to the job env.

### Functions

| [`export_ci_env`](#wads.scripts.export_ci_env.export_ci_env)(\*[, required, test, extra, ...])   | Compute the env assignments to write, plus any missing-required errors.             |
|----------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------|
| [`main`](#wads.scripts.export_ci_env.main)()                                            | Read inputs from env, write assignments to `$GITHUB_ENV`, fail if required missing. |
| [`merge_transported_secrets`](#wads.scripts.export_ci_env.merge_transported_secrets)(secrets)                | Flatten the secrets mapping, expanding the `WADS_CI_SECRETS_JSON` blob.             |

### Classes

| [`ExportPlan`](#wads.scripts.export_ci_env.ExportPlan)(assignments, exported, ...)   | What [`export_ci_env()`](#wads.scripts.export_ci_env.export_ci_env) decided, ready for [`main()`](#wads.scripts.export_ci_env.main) to apply.   |
|-------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|

### *class* wads.scripts.export_ci_env.ExportPlan(assignments, exported, missing_required, missing_test, mask_values)

Bases: [`NamedTuple`](https://docs.python.org/3/library/typing.html#typing.NamedTuple)

What [`export_ci_env()`](#wads.scripts.export_ci_env.export_ci_env) decided, ready for [`main()`](#wads.scripts.export_ci_env.main) to apply.

#### assignments *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)*

Alias for field number 0

#### exported *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)*

Alias for field number 1

#### mask_values *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)*

Alias for field number 4

#### missing_required *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)*

Alias for field number 2

#### missing_test *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)*

Alias for field number 3

### wads.scripts.export_ci_env.export_ci_env(\*, required=(), test=(), extra=(), defaults=None, aliases=None, secrets=None, vars_=None, warn=<function <lambda>>)

Compute the env assignments to write, plus any missing-required errors.

Pure function (no I/O) so it can be unit-tested without GitHub. Each
declared name resolves secrets-first, then falls back to the caller’s
repository variables (`vars_`). Secret-sourced values are collected in
`mask_values` for re-masking; variable- and default-sourced values are
not masked (they are not sensitive by definition).

```pycon
>>> plan = export_ci_env(
...     required=["OPENAI_API_KEY"],
...     test=["TAVILY_API_KEY"],
...     extra=["UNSET_THING", "COSMO_TEST_LEVEL"],
...     defaults={"LOG_LEVEL": "DEBUG"},
...     secrets={"OPENAI_API_KEY": "sk-xxx", "TAVILY_API_KEY": ""},
...     vars_={"COSMO_TEST_LEVEL": "3"},
... )
>>> plan.exported
['LOG_LEVEL', 'OPENAI_API_KEY', 'COSMO_TEST_LEVEL']
>>> plan.missing_required
[]
>>> plan.missing_test
['TAVILY_API_KEY']
>>> plan.mask_values  # only the secret-sourced value
['sk-xxx']
```

A required var with no backing secret *or* variable is reported (caller
should fail CI):

```pycon
>>> export_ci_env(required=["PYPI_PASSWORD"], secrets={}).missing_required
[('PYPI_PASSWORD', 'PYPI_PASSWORD')]
```

Aliases let an env var read a differently-named secret:

```pycon
>>> plan = export_ci_env(
...     test=["HF_TOKEN"],
...     aliases={"HF_TOKEN": "HF_WRITE_TOKEN"},
...     secrets={"HF_WRITE_TOKEN": "hf_xxx"})
>>> plan.exported
['HF_TOKEN']
>>> plan.assignments
['HF_TOKEN=hf_xxx']
```

### wads.scripts.export_ci_env.main()

Read inputs from env, write assignments to `$GITHUB_ENV`, fail if required missing.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### wads.scripts.export_ci_env.merge_transported_secrets(secrets)

Flatten the secrets mapping, expanding the `WADS_CI_SECRETS_JSON` blob.

The blob is the caller’s whole secrets context, serialized by the stub with
`toJSON(toJSON(secrets))` (double-encoded => single-line). A
single-encoded blob is also accepted. Named entries win over blob entries
(they are the same caller values anyway), and non-exportable keys (the
blob itself, `github_token`) are dropped.

```pycon
>>> merged = merge_transported_secrets({
...     "WADS_CI_SECRETS_JSON": '"{\\n  \\"MY_KEY\\": \\"v1\\",\\n  \\"github_token\\": \\"t\\"\\n}"',
...     "OPENAI_API_KEY": "sk-named",
... })
>>> sorted(merged)
['MY_KEY', 'OPENAI_API_KEY']
>>> merged["MY_KEY"]
'v1'
```

Malformed blobs are ignored rather than fatal (the named layer still
works, and required-validation reports any name that failed to resolve):

```pycon
>>> merge_transported_secrets({"WADS_CI_SECRETS_JSON": "not json", "A": "x"})
{'A': 'x'}
```
