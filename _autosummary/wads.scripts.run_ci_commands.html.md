# wads.scripts.run_ci_commands

Run the `[tool.wads.ci.commands]` `pre_test` / `post_test` lists in CI.

`read_ci_config` hands each list over as a JSON array (a GitHub Actions output); the
`run-tests-uv` action puts it in an environment variable and calls this script with
the variable’s name. Each command runs under `bash -c` (as `wads ci-local` runs it; Git Bash on Windows runners), in order, in the current
directory and environment (the venv is already activated), and the first failure stops
the run with its exit status. An empty or unset list does nothing. Stdlib only.

```pycon
>>> run_commands(["echo hi"], run=lambda cmd, **kw: 0)
+ echo hi
0
>>> run_commands('["false", "echo unreachable"]', run=lambda cmd, **kw: 1 if cmd == "false" else 0)
+ false
1
```

### Module Attributes

| [`BASH_ENV_VAR`](#wads.scripts.run_ci_commands.BASH_ENV_VAR)   | The environment variable naming the bash to use.   |
|-----------------------------------------------------------------|----------------------------------------------------|

### Functions

| [`main`](#wads.scripts.run_ci_commands.main)([argv])                      | `run_ci_commands.py ENV_VAR`: run the JSON list held in that variable.                             |
|------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------|
| [`run_commands`](#wads.scripts.run_ci_commands.run_commands)(commands, \*[, run]) | Run `commands` (a list, or its JSON text) in order; return the first non-zero exit status, else 0. |

### wads.scripts.run_ci_commands.BASH_ENV_VAR *= 'WADS_BASH'*

The environment variable naming the bash to use. The action sets it from `$BASH`:
on Windows runners a bare `bash` resolves to System32’s WSL launcher, not Git Bash.

### wads.scripts.run_ci_commands.main(argv=None)

`run_ci_commands.py ENV_VAR`: run the JSON list held in that variable.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### wads.scripts.run_ci_commands.run_commands(commands, \*, run=<function \_default_run>)

Run `commands` (a list, or its JSON text) in order; return the first non-zero
exit status, else 0.

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)
