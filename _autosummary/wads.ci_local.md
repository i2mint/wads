# wads.ci_local

Do locally what the wads CI would have done: the same `[tool.wads.ci]`, no Actions minutes.

`wads ci-local` reads the repo’s `pyproject.toml` through [`wads.ci_config.CIConfig`](wads.ci_config.md#wads.ci_config.CIConfig),
the object the reusable workflow’s setup job reads, and runs in order:

1. **lint**: `ruff format --check` (reported, never fatal: CI reformats in place and moves
   on), then `ruff check <project>`, both through `uvx` so the repo’s own `[tool.ruff]`
   applies exactly as in CI. Black and mypy too, when enabled.
2. **tests**: for each `python_versions` entry, a fresh `uv` venv in a temporary
   directory, `uv pip install -e .[extras]`, then pytest with the arguments
   `actions/run-tests-uv` builds (coverage, `--doctest-modules` and its option flags,
   one `--ignore` per excluded path, then `pytest_args`).
3. **build**: `uv build` into the temporary directory, never the repo’s `dist/`, so a
   stale artifact can never be uploaded.

With `publish=True` it does what the publish job does in place of the plain build:
format in place, bump the version with `isee` (as CI does), build, `uv publish`,
commit, tag and push. Before any of that it refuses on a dirty tree, a branch other than
the default, a branch behind its remote, or missing PyPI credentials.

Known differences from CI: the developer’s environment passes through to the commands
(minus PyPI credentials, which only the upload step sees), where CI exports only the
variables `[tool.wads.ci.env]` declares; `[tool.wads.ops.*]` system packages are not
installed; and lint runs on the tree as it is, where CI formats first.

Every command goes through one `runner` seam. The default runs subprocesses; tests pass
a fake. The default also refuses upload and push steps while pytest is running, so no test
can ever spend or publish.

```pycon
>>> steps = plan_ci_local(".", config=CIConfig({"project": {"name": "pkg"}}))
>>> [s.name for s in steps][:3]
['format check (ruff)', 'lint (ruff)', 'python 3.10: venv']
```

### Functions

| [`ci_local`](#wads.ci_local.ci_local)([repo, publish, dry_run])               | Do locally what wads CI would have done, from the repo's [tool.wads.ci] config.                                               |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------------------|
| [`plan_ci_local`](#wads.ci_local.plan_ci_local)([repo, publish, config, platform]) | Everything `wads ci-local` would run for `repo`, in order, without running it.                                                |
| [`pytest_argv`](#wads.ci_local.pytest_argv)(config)                              | The pytest arguments `actions/run-tests-uv` builds, in its order.                                                             |
| [`render_plan`](#wads.ci_local.render_plan)(steps)                               | The plan as numbered lines, flagging non-blocking and side-effecting steps.                                                   |
| [`resolve_pypi_token`](#wads.ci_local.resolve_pypi_token)(\*[, environ, pypirc])        | Find a PyPI API token, most specific source first.                                                                            |
| [`run_ci_local`](#wads.ci_local.run_ci_local)([repo, publish, config, ...])       | Run [`plan_ci_local()`](#wads.ci_local.plan_ci_local)'s steps, stop at the first blocking failure, and report. |
| [`subprocess_runner`](#wads.ci_local.subprocess_runner)(argv, \*, cwd, env[, ...])     | The default runner: really run `argv`, streaming its output.                                                                  |
| [`uv_build_args`](#wads.ci_local.uv_build_args)(\*[, sdist, wheel])                | `uv build` selection flags for `[tool.wads.ci.build]`.                                                                        |
| [`venv_python`](#wads.ci_local.venv_python)(venv, \*[, platform])                | Path of the interpreter inside a venv directory.                                                                              |

### Classes

| [`CILocalReport`](#wads.ci_local.CILocalReport)(project, publish, ...[, ...])   | The outcome of a `wads ci-local` run, rendered the way CI would summarise it.   |
|------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| [`RunResult`](#wads.ci_local.RunResult)(returncode[, stdout])               | What a runner reports back: the exit code, and stdout when it was captured.     |
| [`Step`](#wads.ci_local.Step)(name[, argv, check, description, ...])   | One thing CI would do: a command (`argv`) or an in-process `check`.             |

### *class* wads.ci_local.CILocalReport(project, publish, trigger_mode, python_versions, outcomes=<factory>, notes=<factory>, values=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

The outcome of a `wads ci-local` run, rendered the way CI would summarise it.

#### *property* failure *: [Step](#wads.ci_local.Step) | [None](https://docs.python.org/3/builtins/constants.html#None)*

The blocking step that failed, if any.

### *class* wads.ci_local.RunResult(returncode, stdout='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a runner reports back: the exit code, and stdout when it was captured.

### *class* wads.ci_local.Step(name, argv=(), check=None, description='', blocking=True, side_effect='', capture='', env=())

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One thing CI would do: a command (`argv`) or an in-process `check`.

`argv` and `env` values may hold `<<workdir>>`, `<<version>>`,
`<<default_branch>>` or `<<pypi_token>>`, filled in at run time. A non-`blocking`
failure is reported without stopping the run. `capture` names the context value that
receives the command’s last stdout line. A `check` takes the run context and returns
an error message, or `None` when it passes.

### wads.ci_local.ci_local(repo='.', , publish=False, dry_run=False)

Do locally what wads CI would have done, from the repo’s [tool.wads.ci] config.

Lint, tests (a fresh uv venv per configured Python) and build. With –publish, the
publish job instead: format, bump version, build, upload to PyPI, commit, tag and push,
refusing on a dirty tree, off the default branch, or without PyPI credentials. With
–dry-run, print the plan and run nothing.

### wads.ci_local.plan_ci_local(repo='.', , publish=False, config=None, platform='posix')

Everything `wads ci-local` would run for `repo`, in order, without running it.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Step`](#wads.ci_local.Step)]

### wads.ci_local.pytest_argv(config)

The pytest arguments `actions/run-tests-uv` builds, in its order.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> pytest_argv(CIConfig({"project": {"name": "pkg"}}))
['--cov=pkg', '--cov-report=term-missing', '--doctest-modules',
 '-o', 'doctest_optionflags=ELLIPSIS IGNORE_EXCEPTION_DETAIL',
 '--ignore=examples', '--ignore=scrap', '-v', '--tb=short']
```

### wads.ci_local.render_plan(steps)

The plan as numbered lines, flagging non-blocking and side-effecting steps.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### wads.ci_local.resolve_pypi_token(, environ=None, pypirc=None)

Find a PyPI API token, most specific source first. Returns `(token, source)`.

1. `$PYPI_PASSWORD`, the secret name CI reads;
2. `$UV_PUBLISH_TOKEN`, what `uv publish` itself reads;
3. `~/.pypirc`, section `[pypi]`: `password`, when `username` is `__token__`
   (or absent) or the password is a `pypi-` token.

Token-only, like CI. The token itself is never printed.

```pycon
>>> resolve_pypi_token(environ={"PYPI_PASSWORD": "pypi-x", "UV_PUBLISH_TOKEN": "pypi-y"})
('pypi-x', '$PYPI_PASSWORD')
>>> resolve_pypi_token(environ={}, pypirc="/nonexistent/.pypirc")
(None, '')
```

* **Return type:**
  [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)], [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### wads.ci_local.run_ci_local(repo='.', \*, publish=False, config=None, runner=<function subprocess_runner>, environ=None, out=None, keep_workdir=False)

Run [`plan_ci_local()`](#wads.ci_local.plan_ci_local)’s steps, stop at the first blocking failure, and report.

* **Return type:**
  [`CILocalReport`](#wads.ci_local.CILocalReport)

### wads.ci_local.subprocess_runner(argv, , cwd, env, capture=False, side_effect='')

The default runner: really run `argv`, streaming its output.

Refuses outward side effects (upload, push) while pytest is running.

* **Return type:**
  [`RunResult`](#wads.ci_local.RunResult)

### wads.ci_local.uv_build_args(, sdist=True, wheel=True)

`uv build` selection flags for `[tool.wads.ci.build]`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

```pycon
>>> uv_build_args()
[]
>>> uv_build_args(sdist=False)
['--wheel']
>>> uv_build_args(wheel=False)
['--sdist']
```

### wads.ci_local.venv_python(venv, , platform='posix')

Path of the interpreter inside a venv directory.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

```pycon
>>> venv_python("v", platform="posix")
'v/bin/python'
>>> venv_python("v", platform="nt")
'v/Scripts/python.exe'
```
